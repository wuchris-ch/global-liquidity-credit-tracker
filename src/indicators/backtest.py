"""Track Record / Backtest of the GLCI regime classifier.

Validates whether GLCI regime classification predicts forward returns using
an expanding-window z-score that avoids look-ahead bias. Compares against
NFCI-alone as a baseline and unconditional buy-and-hold as the base rate.

Outputs:
  data/curated/backtest/track_record.parquet (long-format table)
  data/curated/backtest/track_record.json    (full structured payload)
  data/curated/backtest/track_record_meta.json
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from ..config import CURATED_DATA_PATH
from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage
from .risk_metrics import ASSET_CONFIG
from .transforms import resample_to_frequency


HORIZONS = [4, 13, 26]
REGIME_LABELS = {-1: "tight", 0: "neutral", 1: "loose"}
BURN_IN_PERIODS = 52
REGIME_THRESHOLDS = (-1.0, 1.0)
MIN_OBS_PER_REGIME = 20
BOOTSTRAP_ITERATIONS = 5000
RNG_SEED = 42


@dataclass
class AssetBacktestResult:
    asset_id: str
    name: str
    category: str
    base_rates: dict[int, dict]
    results: dict[str, dict[str, dict[int, dict]]]

    def to_dict(self) -> dict:
        return {
            "id": self.asset_id,
            "name": self.name,
            "category": self.category,
            "base_rates": {str(h): v for h, v in self.base_rates.items()},
            "results": {
                clf: {
                    regime: {str(h): stats for h, stats in by_h.items()}
                    for regime, by_h in by_r.items()
                }
                for clf, by_r in self.results.items()
            },
        }


@dataclass
class BacktestResult:
    computed_at: str
    date_range: tuple[str, str]
    horizons: list[int]
    classifiers: dict[str, dict]
    assets: list[AssetBacktestResult]

    def to_dict(self) -> dict:
        return {
            "computed_at": self.computed_at,
            "date_range": {"start": self.date_range[0], "end": self.date_range[1]},
            "horizons": self.horizons,
            "classifiers": self.classifiers,
            "assets": [a.to_dict() for a in self.assets],
        }


def expanding_zscore_regime(
    values: pd.Series,
    burn_in: int = BURN_IN_PERIODS,
    thresholds: tuple[float, float] = REGIME_THRESHOLDS,
) -> pd.DataFrame:
    """Expanding-window z-score + regime classification without look-ahead.

    At each date t, z_t uses mean/std of all data up to and including t;
    the first `burn_in` observations are left NaN so the backtest never
    relies on a z-score computed from <1 year of history.
    """
    expanding_mean = values.expanding(min_periods=burn_in).mean()
    expanding_std = values.expanding(min_periods=burn_in).std()
    zscore = (values - expanding_mean) / expanding_std

    regime = pd.Series(np.nan, index=values.index)
    mask = zscore.notna()
    low, high = thresholds
    regime.loc[mask & (zscore < low)] = -1
    regime.loc[mask & (zscore >= low) & (zscore <= high)] = 0
    regime.loc[mask & (zscore > high)] = 1

    return pd.DataFrame({"zscore": zscore, "regime": regime})


def compute_forward_returns(prices: pd.Series, horizons: list[int] = HORIZONS) -> pd.DataFrame:
    """Compute r_{t,h} = prices_{t+h} / prices_t - 1 for each horizon in weeks."""
    out = pd.DataFrame(index=prices.index)
    for h in horizons:
        out[f"fwd_{h}w"] = prices.shift(-h) / prices - 1
    return out


def block_bootstrap_ci(
    values: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    block_size: int,
    n_iter: int = BOOTSTRAP_ITERATIONS,
    ci_level: float = 0.95,
    rng: np.random.Generator | None = None,
) -> tuple[float, float]:
    """Moving block bootstrap confidence interval for autocorrelated data."""
    if rng is None:
        rng = np.random.default_rng(RNG_SEED)

    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < block_size * 2:
        return (float("nan"), float("nan"))

    n_blocks = max(1, (n + block_size - 1) // block_size)
    alpha = (1 - ci_level) / 2
    max_start = n - block_size + 1

    boot_stats = np.empty(n_iter)
    for i in range(n_iter):
        starts = rng.integers(0, max_start, size=n_blocks)
        sample = np.concatenate([values[s:s + block_size] for s in starts])[:n]
        boot_stats[i] = statistic(sample)

    return (
        float(np.quantile(boot_stats, alpha)),
        float(np.quantile(boot_stats, 1 - alpha)),
    )


def _clean(value: float) -> float | None:
    """Replace NaN/Inf with None so the payload is valid JSON downstream."""
    if value is None:
        return None
    if not np.isfinite(value):
        return None
    return float(value)


def _sanitize_json(obj):
    """Recursively replace NaN/Inf floats with None; leaves other types alone."""
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize_json(v) for v in obj)
    return obj


def _group_stats(
    returns: np.ndarray,
    block_size: int,
    rng: np.random.Generator,
) -> dict:
    """Median, IQR, hit rate + block-bootstrap 95% CIs for a return series."""
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    if n < MIN_OBS_PER_REGIME:
        return {
            "median": None,
            "p25": None,
            "p75": None,
            "hit_rate": None,
            "n": int(n),
            "ci_median_low": None,
            "ci_median_high": None,
            "ci_hit_rate_low": None,
            "ci_hit_rate_high": None,
        }

    median = _clean(float(np.median(clean)))
    p25 = _clean(float(np.quantile(clean, 0.25)))
    p75 = _clean(float(np.quantile(clean, 0.75)))
    hit_rate = _clean(float(np.mean(clean > 0)))

    ci_med_low, ci_med_high = block_bootstrap_ci(clean, np.median, block_size, rng=rng)
    ci_hr_low, ci_hr_high = block_bootstrap_ci(
        (clean > 0).astype(float), np.mean, block_size, rng=rng
    )

    return {
        "median": round(median, 6) if median is not None else None,
        "p25": round(p25, 6) if p25 is not None else None,
        "p75": round(p75, 6) if p75 is not None else None,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "n": int(n),
        "ci_median_low": round(v, 6) if (v := _clean(ci_med_low)) is not None else None,
        "ci_median_high": round(v, 6) if (v := _clean(ci_med_high)) is not None else None,
        "ci_hit_rate_low": round(v, 4) if (v := _clean(ci_hr_low)) is not None else None,
        "ci_hit_rate_high": round(v, 4) if (v := _clean(ci_hr_high)) is not None else None,
    }


class BacktestComputer:
    """Compute expanding-window backtest of regime classifier vs asset returns."""

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        storage: DataStorage | None = None,
    ) -> None:
        self.fetcher = fetcher or DataFetcher()
        self.storage = storage or DataStorage()

    def compute(self, save_output: bool = False, verbose: bool = True) -> BacktestResult:
        if verbose:
            print("Computing backtest / track record...")

        glci_df = self.storage.load_curated("indices", "glci")
        if glci_df is None or glci_df.empty:
            raise ValueError("GLCI data not found. Run GLCI computation first.")

        glci_df["date"] = pd.to_datetime(glci_df["date"])
        glci_df = glci_df.sort_values("date").reset_index(drop=True)
        glci_series = glci_df.set_index("date")["value"]

        if verbose:
            print(
                f"  GLCI: {len(glci_series)} weekly obs "
                f"({glci_series.index.min().date()} to {glci_series.index.max().date()})"
            )

        glci_regime = expanding_zscore_regime(glci_series)
        if verbose:
            counts = glci_regime["regime"].value_counts().sort_index()
            print(f"  GLCI classified: {int(glci_regime['regime'].notna().sum())} obs")
            for r, c in counts.items():
                print(f"    {REGIME_LABELS[int(r)]}: {int(c)}")

        nfci_series = self._load_and_prep_nfci(glci_series.index, verbose)
        nfci_regime: pd.DataFrame | None = None
        if nfci_series is not None:
            nfci_regime = expanding_zscore_regime(nfci_series)
            if verbose:
                print(f"  NFCI classified: {int(nfci_regime['regime'].notna().sum())} obs")

        rng = np.random.default_rng(RNG_SEED)
        asset_results: list[AssetBacktestResult] = []

        for asset_id, cfg in ASSET_CONFIG.items():
            if verbose:
                print(f"  Processing {cfg['name']}...")
            try:
                result = self._compute_asset_backtest(
                    asset_id, cfg, glci_series.index,
                    glci_regime, nfci_regime, rng, verbose,
                )
                if result is not None:
                    asset_results.append(result)
            except Exception as e:
                if verbose:
                    print(f"    Warning: could not compute backtest for {asset_id}: {e}")

        classifiers = {"glci": self._classifier_meta("glci", glci_regime, glci_series)}
        if nfci_regime is not None and nfci_series is not None:
            classifiers["nfci"] = self._classifier_meta("nfci", nfci_regime, nfci_series)

        first_classified = glci_regime["regime"].first_valid_index()
        last_obs = glci_series.index.max()

        result = BacktestResult(
            computed_at=datetime.utcnow().isoformat(),
            date_range=(
                first_classified.strftime("%Y-%m-%d") if first_classified is not None else "",
                last_obs.strftime("%Y-%m-%d"),
            ),
            horizons=HORIZONS,
            classifiers=classifiers,
            assets=asset_results,
        )

        if save_output:
            self._save(result)

        if verbose:
            print(f"  Completed: {len(asset_results)} assets")

        return result

    def _load_and_prep_nfci(
        self, target_index: pd.DatetimeIndex, verbose: bool
    ) -> pd.Series | None:
        try:
            nfci_df = self.fetcher.fetch_series("nfci")
        except Exception as e:
            if verbose:
                print(f"  NFCI unavailable: {e}")
            return None

        if nfci_df is None or nfci_df.empty:
            return None

        nfci_df = nfci_df[["date", "value"]].copy()
        nfci_df["date"] = pd.to_datetime(nfci_df["date"])
        if nfci_df["date"].dt.tz is not None:
            nfci_df["date"] = nfci_df["date"].dt.tz_localize(None)
        nfci_df = nfci_df.sort_values("date")
        nfci_df = resample_to_frequency(nfci_df, "W", agg_method="last")

        series = nfci_df.set_index("date")["value"]
        # FRED NFCI convention: higher = tighter. Invert so higher z → "loose"
        # bucket (same orientation as GLCI).
        series = -series
        series = series.reindex(target_index, method="ffill")
        return series

    def _compute_asset_backtest(
        self,
        asset_id: str,
        cfg: dict,
        target_index: pd.DatetimeIndex,
        glci_regime: pd.DataFrame,
        nfci_regime: pd.DataFrame | None,
        rng: np.random.Generator,
        verbose: bool,
    ) -> AssetBacktestResult | None:
        price_df = self.fetcher.fetch_series(asset_id)
        if price_df is None or price_df.empty:
            return None

        price_df = price_df[["date", "value"]].copy()
        price_df["date"] = pd.to_datetime(price_df["date"])
        if price_df["date"].dt.tz is not None:
            price_df["date"] = price_df["date"].dt.tz_localize(None)
        price_df = price_df.sort_values("date")
        price_df = resample_to_frequency(price_df, "W", agg_method="last")

        prices = price_df.set_index("date")["value"]
        prices = prices.reindex(target_index, method="ffill").dropna()

        fwd = compute_forward_returns(prices, HORIZONS)
        merged = fwd.join(
            glci_regime.rename(columns={"regime": "glci_regime"})[["glci_regime"]],
            how="inner",
        )
        if nfci_regime is not None:
            merged = merged.join(
                nfci_regime.rename(columns={"regime": "nfci_regime"})[["nfci_regime"]],
                how="left",
            )

        base_rates: dict[int, dict] = {}
        for h in HORIZONS:
            data = merged[f"fwd_{h}w"].dropna().values
            if len(data) < MIN_OBS_PER_REGIME:
                base_rates[h] = {
                    "median": None,
                    "hit_rate": None,
                    "n": int(len(data)),
                }
            else:
                base_rates[h] = {
                    "median": round(float(np.median(data)), 6),
                    "hit_rate": round(float(np.mean(data > 0)), 4),
                    "n": int(len(data)),
                }

        results: dict[str, dict[str, dict[int, dict]]] = {}
        classifier_cols = [("glci", "glci_regime")]
        if nfci_regime is not None:
            classifier_cols.append(("nfci", "nfci_regime"))

        for clf_name, regime_col in classifier_cols:
            if regime_col not in merged.columns:
                continue
            results[clf_name] = {}
            for regime_code, regime_label in REGIME_LABELS.items():
                subset = merged[merged[regime_col] == regime_code]
                results[clf_name][regime_label] = {}
                for h in HORIZONS:
                    data = subset[f"fwd_{h}w"].dropna().values
                    stats = _group_stats(data, block_size=h, rng=rng)
                    base_hr = base_rates[h].get("hit_rate")
                    if stats["hit_rate"] is not None and base_hr is not None:
                        stats["edge"] = round(stats["hit_rate"] - base_hr, 4)
                    else:
                        stats["edge"] = None
                    results[clf_name][regime_label][h] = stats

        return AssetBacktestResult(
            asset_id=asset_id,
            name=cfg["name"],
            category=cfg["category"],
            base_rates=base_rates,
            results=results,
        )

    def _classifier_meta(
        self,
        name: str,
        regime_df: pd.DataFrame,
        values: pd.Series,
    ) -> dict:
        valid = regime_df.dropna(subset=["regime"])
        counts_labeled = {
            REGIME_LABELS[int(k)]: int(v)
            for k, v in valid["regime"].value_counts().to_dict().items()
        }
        current_regime = (
            REGIME_LABELS[int(valid["regime"].iloc[-1])] if not valid.empty else None
        )

        timeline = []
        for date, row in regime_df.iterrows():
            if pd.notna(row["regime"]):
                raw = values.loc[date] if date in values.index else None
                timeline.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "regime": REGIME_LABELS[int(row["regime"])],
                    "zscore": round(float(row["zscore"]), 3) if pd.notna(row["zscore"]) else None,
                    "value": round(float(raw), 4) if raw is not None and pd.notna(raw) else None,
                })

        return {
            "name": name,
            "n_per_regime": counts_labeled,
            "current_regime": current_regime,
            "timeline": timeline,
        }

    def _save(self, result: BacktestResult) -> None:
        rows = []
        for asset in result.assets:
            for clf, by_regime in asset.results.items():
                for regime, by_horizon in by_regime.items():
                    for horizon, stats in by_horizon.items():
                        rows.append({
                            "asset_id": asset.asset_id,
                            "name": asset.name,
                            "category": asset.category,
                            "classifier": clf,
                            "regime": regime,
                            "horizon": int(horizon),
                            **stats,
                        })
        df = pd.DataFrame(rows)

        self.storage.save_curated(
            df, "backtest", "track_record",
            metadata={
                "computed_at": result.computed_at,
                "date_range_start": result.date_range[0],
                "date_range_end": result.date_range[1],
                "horizons": result.horizons,
                "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
                "burn_in_periods": BURN_IN_PERIODS,
                "min_obs_per_regime": MIN_OBS_PER_REGIME,
            },
        )

        payload_path = CURATED_DATA_PATH / "backtest" / "track_record.json"
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        with open(payload_path, "w") as f:
            json.dump(
                _sanitize_json(result.to_dict()),
                f,
                indent=2,
                default=str,
                allow_nan=False,
            )


def compute_backtest(save: bool = False, verbose: bool = True) -> BacktestResult:
    return BacktestComputer().compute(save_output=save, verbose=verbose)

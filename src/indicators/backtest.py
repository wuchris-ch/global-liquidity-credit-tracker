"""Track Record / Backtest of the GLCI regime classifier.

Evaluates whether reconstructed GLCI regime classifications predict forward
returns. Regime thresholds use only expanding history, but the upstream GLCI
series is built from the current data vintage and is not point-in-time history.
Compares against NFCI-alone and unconditional buy-and-hold base rates.

Outputs:
  data/curated/backtest/track_record.parquet (long-format table)
  data/curated/backtest/track_record.json    (full structured payload)
  data/curated/backtest/track_record_meta.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from ..config import CURATED_DATA_PATH
from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage
from .risk_metrics import ASSET_CONFIG


HORIZONS = [4, 13, 26]
REGIME_LABELS = {-1: "tight", 0: "neutral", 1: "loose"}
BURN_IN_PERIODS = 52
REGIME_THRESHOLDS = (-1.0, 1.0)
MIN_OBS_PER_REGIME = 20
BOOTSTRAP_ITERATIONS = 5000
BOOTSTRAP_METHOD = "paired_full_calendar_moving_block"
MIN_FINITE_BOOTSTRAP_DRAWS = 100
MIN_FINITE_BOOTSTRAP_FRACTION = 0.80
RNG_SEED = 42
FREQUENCY = "W-FRI"
ENTRY_LAG_WEEKS = 1
HISTORICAL_MODE = "reconstructed_current_vintage"
POINT_IN_TIME_HISTORY = False
GLCI_CARRY_FORWARD_WEEKS = 0
MARKET_CARRY_FORWARD_WEEKS = 1


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
    frequency: str = FREQUENCY
    entry_lag_weeks: int = ENTRY_LAG_WEEKS
    historical_mode: str = HISTORICAL_MODE
    point_in_time: bool = POINT_IN_TIME_HISTORY
    bootstrap_method: str = BOOTSTRAP_METHOD
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS
    min_obs_per_regime: int = MIN_OBS_PER_REGIME

    def to_dict(self) -> dict:
        return {
            "computed_at": self.computed_at,
            "date_range": {"start": self.date_range[0], "end": self.date_range[1]},
            "horizons": self.horizons,
            "frequency": self.frequency,
            "entry_lag_weeks": self.entry_lag_weeks,
            "historical_mode": self.historical_mode,
            "point_in_time": self.point_in_time,
            "regime_threshold_method": "expanding_zscore",
            "bootstrap_method": self.bootstrap_method,
            "bootstrap_iterations": self.bootstrap_iterations,
            "min_obs_per_regime": self.min_obs_per_regime,
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


def _validate_weekly_grid(index: pd.Index, name: str = "series") -> None:
    """Reject row-based horizons unless dates form a complete W-FRI grid."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{name} must use a DatetimeIndex")
    if index.empty:
        return
    if index.tz is not None:
        raise ValueError(f"{name} dates must be timezone-naive")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError(f"{name} dates must be ordered and unique")
    expected = pd.date_range(index[0], index[-1], freq=FREQUENCY)
    if not index.equals(expected):
        raise ValueError(f"{name} must use a complete {FREQUENCY} grid")


def _to_weekly_grid(
    values: pd.Series,
    *,
    name: str,
    carry_forward_weeks: int = 0,
) -> pd.Series:
    """Place observations on W-FRI without filling before the first release."""
    if not isinstance(values.index, pd.DatetimeIndex):
        raise ValueError(f"{name} must use a DatetimeIndex")
    if values.index.has_duplicates:
        raise ValueError(f"{name} contains duplicate dates")
    if carry_forward_weeks < 0:
        raise ValueError("carry_forward_weeks cannot be negative")
    if values.empty:
        return values.copy()

    series = values.copy().sort_index()
    if series.index.tz is not None:
        series.index = series.index.tz_localize(None)

    max_observation_date = series.index.max().normalize()
    weekly = series.resample(FREQUENCY).last()
    last_completed_friday = pd.offsets.Week(weekday=4).rollback(max_observation_date)
    weekly = weekly.loc[weekly.index <= last_completed_friday]
    if weekly.empty:
        weekly.index.name = values.index.name
        return weekly

    grid = pd.date_range(weekly.index.min(), weekly.index.max(), freq=FREQUENCY)
    weekly = weekly.reindex(grid)
    if carry_forward_weeks:
        weekly = weekly.ffill(limit=carry_forward_weeks)
    weekly.index.name = values.index.name
    _validate_weekly_grid(weekly.index, name)
    return weekly


def compute_forward_returns(
    prices: pd.Series,
    horizons: list[int] = HORIZONS,
    entry_lag_weeks: int = ENTRY_LAG_WEEKS,
) -> pd.DataFrame:
    """Compute calendar-week returns from the next actionable weekly bar.

    A signal observed at week t enters at t + ``entry_lag_weeks`` and exits
    exactly ``h`` W-FRI bars after entry. Irregular indexes are rejected so a
    requested 13-week horizon cannot silently mean 13 arbitrary source rows.
    """
    _validate_weekly_grid(prices.index, "prices")
    if entry_lag_weeks < 0:
        raise ValueError("entry_lag_weeks cannot be negative")
    if any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive week counts")

    out = pd.DataFrame(index=prices.index)
    for h in horizons:
        entry = prices.shift(-entry_lag_weeks)
        exit_price = prices.shift(-(entry_lag_weeks + h))
        out[f"fwd_{h}w"] = exit_price / entry - 1
    return out


def _moving_block_indices(
    n_observations: int,
    block_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample contiguous blocks of positions, then trim to the original length."""
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if n_observations < block_size:
        raise ValueError("block_size cannot exceed the observation count")

    n_blocks = max(1, (n_observations + block_size - 1) // block_size)
    max_start = n_observations - block_size + 1
    starts = rng.integers(0, max_start, size=n_blocks)
    offsets = np.arange(block_size)
    return (starts[:, None] + offsets).reshape(-1)[:n_observations]


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


def _empty_regime_stats(n: int) -> dict:
    """Return the stable payload shape for an unreportable regime cell."""
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
        "edge": None,
        "ci_edge_low": None,
        "ci_edge_high": None,
    }


def _required_finite_draws(n_iter: int) -> int:
    """Require broad bootstrap support while allowing reduced test iterations."""
    return min(
        n_iter,
        max(
            MIN_FINITE_BOOTSTRAP_DRAWS,
            int(np.ceil(n_iter * MIN_FINITE_BOOTSTRAP_FRACTION)),
        ),
    )


def _paired_regime_stats(
    returns: np.ndarray,
    regimes: np.ndarray,
    block_size: int,
    rng: np.random.Generator,
    *,
    base_hit_rate: float | None = None,
    n_iter: int = BOOTSTRAP_ITERATIONS,
    ci_level: float = 0.95,
    min_subgroup_obs: int = MIN_OBS_PER_REGIME,
    min_finite_draws: int | None = None,
) -> dict[int, dict]:
    """Compute regime statistics with a paired full-calendar block bootstrap.

    Blocks are sampled from the weekly row sequence before any regime filter is
    applied. Each accepted draw computes both the regime subgroup hit rate and
    the unconditional hit rate, so the edge interval is paired within draw.
    """
    returns = np.asarray(returns, dtype=float)
    regimes = np.asarray(regimes, dtype=float)
    if returns.ndim != 1 or regimes.ndim != 1:
        raise ValueError("returns and regimes must be one-dimensional")
    if len(returns) != len(regimes):
        raise ValueError("returns and regimes must have the same length")
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if n_iter <= 0:
        raise ValueError("n_iter must be positive")
    if min_subgroup_obs <= 0:
        raise ValueError("min_subgroup_obs must be positive")
    if not 0 < ci_level < 1:
        raise ValueError("ci_level must be between zero and one")

    # Leading/trailing weeks without an asset return carry no information.
    # Internal missing-return or unclassified weeks remain in place so blocks
    # preserve calendar adjacency rather than compressing the subgroup.
    finite_positions = np.flatnonzero(np.isfinite(returns))
    if finite_positions.size:
        first, last = int(finite_positions[0]), int(finite_positions[-1]) + 1
        returns = returns[first:last]
        regimes = regimes[first:last]

    valid_returns = np.isfinite(returns)
    classified_returns = valid_returns & np.isfinite(regimes)
    all_clean = returns[classified_returns]
    if base_hit_rate is None and len(all_clean) >= min_subgroup_obs:
        base_hit_rate = round(float(np.mean(all_clean > 0)), 4)

    stats_by_regime: dict[int, dict] = {}
    eligible_codes: list[int] = []
    for regime_code in REGIME_LABELS:
        group_mask = classified_returns & (regimes == regime_code)
        clean = returns[group_mask]
        n = len(clean)
        stats = _empty_regime_stats(n)
        if n >= min_subgroup_obs:
            median = float(np.median(clean))
            hit_rate = round(float(np.mean(clean > 0)), 4)
            stats.update(
                {
                    "median": round(median, 6),
                    "p25": round(float(np.quantile(clean, 0.25)), 6),
                    "p75": round(float(np.quantile(clean, 0.75)), 6),
                    "hit_rate": hit_rate,
                    "edge": (
                        round(hit_rate - base_hit_rate, 4)
                        if base_hit_rate is not None
                        else None
                    ),
                }
            )
            eligible_codes.append(regime_code)
        stats_by_regime[regime_code] = stats

    if (
        not eligible_codes
        or len(returns) < block_size * 2
        or len(all_clean) < min_subgroup_obs
    ):
        return stats_by_regime

    required_draws = (
        _required_finite_draws(n_iter) if min_finite_draws is None else min_finite_draws
    )
    if required_draws <= 0 or required_draws > n_iter:
        raise ValueError("min_finite_draws must be between one and n_iter")

    boot: dict[int, dict[str, list[float]]] = {
        code: {"median": [], "hit_rate": [], "edge": []} for code in eligible_codes
    }
    for _ in range(n_iter):
        sample_idx = _moving_block_indices(len(returns), block_size, rng)
        sample_returns = returns[sample_idx]
        sample_regimes = regimes[sample_idx]
        sample_valid = np.isfinite(sample_returns) & np.isfinite(sample_regimes)
        unconditional = sample_returns[sample_valid]
        if len(unconditional) < min_subgroup_obs:
            continue
        unconditional_hit_rate = float(np.mean(unconditional > 0))

        for regime_code in eligible_codes:
            subgroup = sample_returns[sample_valid & (sample_regimes == regime_code)]
            if len(subgroup) < min_subgroup_obs:
                continue
            subgroup_hit_rate = float(np.mean(subgroup > 0))
            boot[regime_code]["median"].append(float(np.median(subgroup)))
            boot[regime_code]["hit_rate"].append(subgroup_hit_rate)
            boot[regime_code]["edge"].append(subgroup_hit_rate - unconditional_hit_rate)

    alpha = (1 - ci_level) / 2
    for regime_code in eligible_codes:
        draws = boot[regime_code]
        if len(draws["edge"]) < required_draws:
            continue

        def interval(name: str, decimals: int) -> tuple[float, float]:
            values = np.asarray(draws[name], dtype=float)
            low, high = np.quantile(values, [alpha, 1 - alpha])
            return round(float(low), decimals), round(float(high), decimals)

        median_low, median_high = interval("median", 6)
        hit_low, hit_high = interval("hit_rate", 4)
        edge_low, edge_high = interval("edge", 4)
        stats_by_regime[regime_code].update(
            {
                "ci_median_low": median_low,
                "ci_median_high": median_high,
                "ci_hit_rate_low": hit_low,
                "ci_hit_rate_high": hit_high,
                "ci_edge_low": edge_low,
                "ci_edge_high": edge_high,
            }
        )

    return stats_by_regime


class BacktestComputer:
    """Compute expanding-window backtest of regime classifier vs asset returns."""

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        storage: DataStorage | None = None,
    ) -> None:
        self.fetcher = fetcher or DataFetcher()
        self.storage = storage or DataStorage()

    def compute(
        self, save_output: bool = False, verbose: bool = True
    ) -> BacktestResult:
        if verbose:
            print("Computing backtest / track record...")

        glci_df = self.storage.load_curated("indices", "glci")
        if glci_df is None or glci_df.empty:
            raise ValueError("GLCI data not found. Run GLCI computation first.")

        glci_df["date"] = pd.to_datetime(glci_df["date"])
        glci_df = glci_df.sort_values("date").reset_index(drop=True)
        glci_series = _to_weekly_grid(
            glci_df.set_index("date")["value"],
            name="GLCI",
            carry_forward_weeks=GLCI_CARRY_FORWARD_WEEKS,
        )
        if glci_series.isna().any():
            missing_weeks = int(glci_series.isna().sum())
            raise ValueError(
                "GLCI history contains "
                f"{missing_weeks} missing W-FRI observations; recompute it "
                "instead of carrying synthetic values into the backtest"
            )

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
                print(
                    f"  NFCI classified: {int(nfci_regime['regime'].notna().sum())} obs"
                )

        rng = np.random.default_rng(RNG_SEED)
        asset_results: list[AssetBacktestResult] = []

        for asset_id, cfg in ASSET_CONFIG.items():
            if verbose:
                print(f"  Processing {cfg['name']}...")
            try:
                result = self._compute_asset_backtest(
                    asset_id,
                    cfg,
                    glci_series.index,
                    glci_regime,
                    nfci_regime,
                    rng,
                    verbose,
                )
                if result is not None:
                    asset_results.append(result)
            except Exception as e:
                if verbose:
                    print(
                        f"    Warning: could not compute backtest for {asset_id}: {e}"
                    )

        classifiers = {"glci": self._classifier_meta("glci", glci_regime, glci_series)}
        if nfci_regime is not None and nfci_series is not None:
            classifiers["nfci"] = self._classifier_meta(
                "nfci", nfci_regime, nfci_series
            )

        first_classified = glci_regime["regime"].first_valid_index()
        last_obs = glci_series.index.max()

        result = BacktestResult(
            computed_at=datetime.utcnow().isoformat(),
            date_range=(
                first_classified.strftime("%Y-%m-%d")
                if first_classified is not None
                else "",
                last_obs.strftime("%Y-%m-%d"),
            ),
            horizons=HORIZONS,
            classifiers=classifiers,
            assets=asset_results,
            frequency=FREQUENCY,
            entry_lag_weeks=ENTRY_LAG_WEEKS,
            historical_mode=HISTORICAL_MODE,
            point_in_time=POINT_IN_TIME_HISTORY,
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
        series = _to_weekly_grid(
            nfci_df.set_index("date")["value"],
            name="NFCI",
            carry_forward_weeks=MARKET_CARRY_FORWARD_WEEKS,
        )
        # FRED NFCI convention: higher = tighter. Invert so higher z → "loose"
        # bucket (same orientation as GLCI).
        series = -series
        series = series.reindex(target_index).ffill(limit=MARKET_CARRY_FORWARD_WEEKS)
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
        prices = _to_weekly_grid(
            price_df.set_index("date")["value"],
            name=f"{asset_id} prices",
            carry_forward_weeks=MARKET_CARRY_FORWARD_WEEKS,
        )
        prices = prices.reindex(target_index).ffill(limit=MARKET_CARRY_FORWARD_WEEKS)
        _validate_weekly_grid(prices.index, f"{asset_id} prices")

        fwd = compute_forward_returns(
            prices,
            HORIZONS,
            entry_lag_weeks=ENTRY_LAG_WEEKS,
        )
        merged = fwd.join(
            glci_regime.rename(columns={"regime": "glci_regime"})[["glci_regime"]],
            how="inner",
        )
        if nfci_regime is not None:
            merged = merged.join(
                nfci_regime.rename(columns={"regime": "nfci_regime"})[["nfci_regime"]],
                how="left",
            )
        _validate_weekly_grid(merged.index, f"{asset_id} backtest rows")

        base_rates: dict[int, dict] = {}
        for h in HORIZONS:
            eligible = merged[f"fwd_{h}w"].notna() & merged["glci_regime"].notna()
            data = merged.loc[eligible, f"fwd_{h}w"].values
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
            results[clf_name] = {
                regime_label: {} for regime_label in REGIME_LABELS.values()
            }
            regimes = merged[regime_col].to_numpy(dtype=float)
            for h in HORIZONS:
                stats_by_code = _paired_regime_stats(
                    merged[f"fwd_{h}w"].to_numpy(dtype=float),
                    regimes,
                    block_size=h,
                    rng=rng,
                    base_hit_rate=(
                        base_rates[h].get("hit_rate")
                        if clf_name == "glci"
                        else None
                    ),
                )
                for regime_code, regime_label in REGIME_LABELS.items():
                    results[clf_name][regime_label][h] = stats_by_code[regime_code]

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
                timeline.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "regime": REGIME_LABELS[int(row["regime"])],
                        "zscore": round(float(row["zscore"]), 3)
                        if pd.notna(row["zscore"])
                        else None,
                        "value": round(float(raw), 4)
                        if raw is not None and pd.notna(raw)
                        else None,
                    }
                )

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
                        rows.append(
                            {
                                "asset_id": asset.asset_id,
                                "name": asset.name,
                                "category": asset.category,
                                "classifier": clf,
                                "regime": regime,
                                "horizon": int(horizon),
                                **stats,
                            }
                        )
        df = pd.DataFrame(rows)

        self.storage.save_curated(
            df,
            "backtest",
            "track_record",
            metadata={
                "computed_at": result.computed_at,
                "date_range_start": result.date_range[0],
                "date_range_end": result.date_range[1],
                "horizons": result.horizons,
                "frequency": result.frequency,
                "entry_lag_weeks": result.entry_lag_weeks,
                "historical_mode": result.historical_mode,
                "point_in_time": result.point_in_time,
                "regime_threshold_method": "expanding_zscore",
                "bootstrap_iterations": result.bootstrap_iterations,
                "bootstrap_method": result.bootstrap_method,
                "bootstrap_min_finite_draw_fraction": MIN_FINITE_BOOTSTRAP_FRACTION,
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

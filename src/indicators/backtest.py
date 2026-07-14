"""Track Record / Backtest of the GLCI regime classifier.

Evaluates whether reconstructed GLCI regime classifications predict forward
returns. The GLCI uses the production 104-week rolling classifier; NFCI uses
an expanding-history benchmark. The upstream GLCI series is built from the
current data vintage and is not point-in-time history. Compares both classifiers
against unconditional buy-and-hold base rates.

Outputs:
  data/curated/backtest/track_record.parquet (long-format table)
  data/curated/backtest/track_record.json    (full structured payload)
  data/curated/backtest/track_record_meta.json
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from ..config import CURATED_DATA_PATH
from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage
from .live_evaluation import compute_live_evaluation
from .risk_metrics import ASSET_CONFIG


HORIZONS = [4, 13, 26]
REGIME_LABELS = {-1: "tight", 0: "neutral", 1: "loose"}
BURN_IN_PERIODS = 52
GLCI_REGIME_WINDOW = 104
GLCI_REGIME_MIN_PERIODS = 20
REGIME_THRESHOLDS = (-1.0, 1.0)
MIN_OBS_PER_REGIME = 20
BOOTSTRAP_ITERATIONS = 5000
BOOTSTRAP_METHOD = "paired_full_calendar_moving_block"
MIN_FINITE_BOOTSTRAP_DRAWS = 100
MIN_FINITE_BOOTSTRAP_FRACTION = 0.80
EDGE_STANDARD_ERROR_METHOD = (
    "sample_standard_deviation_of_paired_moving_block_bootstrap_edge_draws"
)
EDGE_P_VALUE_METHOD = "two_sided_normal_approximation_from_bootstrap_standard_error"
MULTIPLE_TESTING_METHOD = "benjamini_yekutieli"
MULTIPLE_TESTING_ALPHA = 0.10
MULTIPLE_TESTING_FAMILY = (
    "all_classifier_asset_regime_horizon_edge_tests_with_finite_p_values"
)
EVIDENCE_READINESS_POLICY = "point_in_time_minimum_history_and_all_regimes"
MIN_CLASSIFIED_WEEKS_FOR_SUPPORT = 260
RNG_SEED = 42
FREQUENCY = "W-FRI"
ENTRY_LAG_WEEKS = 1
HISTORICAL_MODE = "reconstructed_current_vintage"
POINT_IN_TIME_HISTORY = False
GLCI_REGIME_METHOD = "rolling_104_period_zscore"
NFCI_REGIME_METHOD = "expanding_zscore"
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
    regime_threshold_method: str = GLCI_REGIME_METHOD
    inference_test_count: int = 0
    live_evaluation: dict | None = None

    def to_dict(self) -> dict:
        payload = {
            "computed_at": self.computed_at,
            "date_range": {"start": self.date_range[0], "end": self.date_range[1]},
            "horizons": self.horizons,
            "frequency": self.frequency,
            "entry_lag_weeks": self.entry_lag_weeks,
            "historical_mode": self.historical_mode,
            "point_in_time": self.point_in_time,
            "regime_threshold_method": self.regime_threshold_method,
            "bootstrap_method": self.bootstrap_method,
            "bootstrap_iterations": self.bootstrap_iterations,
            "min_obs_per_regime": self.min_obs_per_regime,
            "inference": {
                "edge_standard_error_method": EDGE_STANDARD_ERROR_METHOD,
                "p_value_method": EDGE_P_VALUE_METHOD,
                "multiple_testing_method": MULTIPLE_TESTING_METHOD,
                "multiple_testing_alpha": MULTIPLE_TESTING_ALPHA,
                "multiple_testing_family": MULTIPLE_TESTING_FAMILY,
                "tests_in_family": self.inference_test_count,
                "readiness": _inference_readiness(
                    self.classifiers,
                    point_in_time=self.point_in_time,
                ),
            },
            "classifiers": self.classifiers,
            "assets": [a.to_dict() for a in self.assets],
        }
        if self.live_evaluation is not None:
            payload["live_evaluation"] = self.live_evaluation
        return payload


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


def rolling_zscore_regime(
    values: pd.Series,
    window: int = GLCI_REGIME_WINDOW,
    min_periods: int = GLCI_REGIME_MIN_PERIODS,
    thresholds: tuple[float, float] = REGIME_THRESHOLDS,
) -> pd.DataFrame:
    """Reproduce the production GLCI rolling regime classifier.

    The live GLCI uses a 104-week rolling mean and sample standard deviation,
    emitting its first classification after 20 observations. Keeping this
    logic here makes the Playbook evaluate the same signal shown elsewhere in
    the product instead of a different expanding-window classifier.
    """
    rolling_mean = values.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = values.rolling(window=window, min_periods=min_periods).std()
    zscore = (values - rolling_mean) / rolling_std

    regime = pd.Series(np.nan, index=values.index)
    finite = zscore.notna() & np.isfinite(zscore)
    low, high = thresholds
    regime.loc[finite & (zscore < low)] = -1
    regime.loc[finite & (zscore >= low) & (zscore <= high)] = 0
    regime.loc[finite & (zscore > high)] = 1
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


def _benjamini_yekutieli_qvalues(
    p_values: list[float | None],
) -> list[float | None]:
    """Return dependence-robust adjusted p-values in the original order.

    ``None`` entries represent hypotheses that could not be tested and are not
    included in the multiplicity family. All finite p-values supplied in one
    call are corrected together.
    """
    finite: list[tuple[int, float]] = []
    adjusted: list[float | None] = [None] * len(p_values)
    for index, raw_value in enumerate(p_values):
        if raw_value is None:
            continue
        value = float(raw_value)
        if not np.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("p-values must be finite and between zero and one")
        finite.append((index, value))

    m = len(finite)
    if m == 0:
        return adjusted

    finite.sort(key=lambda item: item[1])
    harmonic_m = sum(1.0 / rank for rank in range(1, m + 1))
    running_min = 1.0
    for position in range(m - 1, -1, -1):
        original_index, p_value = finite[position]
        rank = position + 1
        candidate = p_value * m * harmonic_m / rank
        running_min = min(running_min, candidate)
        adjusted[original_index] = min(1.0, max(0.0, running_min))

    return adjusted


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
        "edge_standard_error": None,
        "p_value": None,
        "q_value": None,
        "fdr_significant": None,
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
        base_hit_rate = float(np.mean(all_clean > 0))

    stats_by_regime: dict[int, dict] = {}
    point_edges: dict[int, float] = {}
    eligible_codes: list[int] = []
    for regime_code in REGIME_LABELS:
        group_mask = classified_returns & (regimes == regime_code)
        clean = returns[group_mask]
        n = len(clean)
        stats = _empty_regime_stats(n)
        if n >= min_subgroup_obs:
            median = float(np.median(clean))
            raw_hit_rate = float(np.mean(clean > 0))
            hit_rate = round(raw_hit_rate, 4)
            if base_hit_rate is not None:
                point_edges[regime_code] = raw_hit_rate - base_hit_rate
            stats.update(
                {
                    "median": round(median, 6),
                    "p25": round(float(np.quantile(clean, 0.25)), 6),
                    "p75": round(float(np.quantile(clean, 0.75)), 6),
                    "hit_rate": hit_rate,
                    "edge": (
                        round(point_edges[regime_code], 4)
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
        edge_draws = np.asarray(draws["edge"], dtype=float)
        edge_standard_error = float(np.std(edge_draws, ddof=1))
        point_edge = point_edges.get(regime_code)
        if point_edge is None or not np.isfinite(edge_standard_error):
            p_value = None
        elif edge_standard_error == 0:
            p_value = 1.0 if point_edge == 0 else 0.0
        else:
            z_score = abs(point_edge) / edge_standard_error
            p_value = math.erfc(z_score / math.sqrt(2.0))
        stats_by_regime[regime_code].update(
            {
                "ci_median_low": median_low,
                "ci_median_high": median_high,
                "ci_hit_rate_low": hit_low,
                "ci_hit_rate_high": hit_high,
                "ci_edge_low": edge_low,
                "ci_edge_high": edge_high,
                "edge_standard_error": round(edge_standard_error, 6),
                "p_value": round(float(p_value), 10)
                if p_value is not None
                else None,
            }
        )

    return stats_by_regime


def _apply_multiple_testing(
    assets: list[AssetBacktestResult],
    *,
    alpha: float = MULTIPLE_TESTING_ALPHA,
) -> int:
    """Apply one BY correction across every reportable edge in the payload."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")

    tested_cells: list[dict] = []
    p_values: list[float] = []
    for asset in assets:
        for by_regime in asset.results.values():
            for by_horizon in by_regime.values():
                for stats in by_horizon.values():
                    stats["q_value"] = None
                    stats["fdr_significant"] = None
                    p_value = stats.get("p_value")
                    if p_value is None:
                        continue
                    tested_cells.append(stats)
                    p_values.append(float(p_value))

    q_values = _benjamini_yekutieli_qvalues(p_values)
    for stats, q_value in zip(tested_cells, q_values, strict=True):
        if q_value is None:
            continue
        stats["q_value"] = round(q_value, 10)
        stats["fdr_significant"] = bool(q_value <= alpha)

    return len(tested_cells)


def _inference_readiness(
    classifiers: dict[str, dict],
    *,
    point_in_time: bool = POINT_IN_TIME_HISTORY,
) -> dict:
    """Apply an explicit product gate before calling a backtest edge supported.

    A q-value is a property of the tested family, not proof that the historical
    inputs were available in real time or that the primary classifier has seen
    enough history and every state it is meant to compare.
    The weekly floor is a disclosed model-governance policy, not a claim that
    five calendar years guarantee a complete liquidity cycle.
    """
    glci = classifiers.get("glci", {}) if isinstance(classifiers, dict) else {}
    raw_counts = glci.get("n_per_regime", {}) if isinstance(glci, dict) else {}
    counts = {
        label: int(raw_counts.get(label, 0) or 0)
        for label in REGIME_LABELS.values()
    }
    observed = int(sum(counts.values()))
    reasons = []
    if not point_in_time:
        reasons.append("point_in_time_history_unavailable")
    if observed < MIN_CLASSIFIED_WEEKS_FOR_SUPPORT:
        reasons.append(
            f"classified_history_below_{MIN_CLASSIFIED_WEEKS_FOR_SUPPORT}_weeks"
        )
    for label, count in counts.items():
        if count < MIN_OBS_PER_REGIME:
            reasons.append(f"{label}_regime_below_{MIN_OBS_PER_REGIME}_observations")

    return {
        "ready": not reasons,
        "policy": EVIDENCE_READINESS_POLICY,
        "classifier": "glci",
        "point_in_time_history_required": True,
        "point_in_time_history": bool(point_in_time),
        "minimum_classified_weeks": MIN_CLASSIFIED_WEEKS_FOR_SUPPORT,
        "observed_classified_weeks": observed,
        "minimum_observations_per_regime": MIN_OBS_PER_REGIME,
        "regime_observations": counts,
        "reasons": reasons,
    }


class BacktestComputer:
    """Backtest production GLCI and benchmark NFCI regime classifiers."""

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

        # Evaluate the same rolling classifier that produces the live GLCI
        # regime. The expanding classifier remains useful for the NFCI
        # benchmark, but it is not a substitute for the production signal.
        glci_regime = rolling_zscore_regime(glci_series)
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

        classifiers = {
            "glci": self._classifier_meta(
                "glci",
                glci_regime,
                glci_series,
                threshold_method=GLCI_REGIME_METHOD,
                window_periods=GLCI_REGIME_WINDOW,
                min_periods=GLCI_REGIME_MIN_PERIODS,
            )
        }
        if nfci_regime is not None and nfci_series is not None:
            classifiers["nfci"] = self._classifier_meta(
                "nfci",
                nfci_regime,
                nfci_series,
                threshold_method=NFCI_REGIME_METHOD,
                window_periods=None,
                min_periods=BURN_IN_PERIODS,
            )

        inference_test_count = _apply_multiple_testing(asset_results)
        live_evaluation = compute_live_evaluation(
            self.storage,
            ASSET_CONFIG,
            horizons=HORIZONS,
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
            inference_test_count=inference_test_count,
            live_evaluation=live_evaluation,
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
                    # Compute the comparison rate from this classifier's exact
                    # eligible rows. The separately displayed base rate is
                    # rounded for presentation and must not enter inference.
                    base_hit_rate=None,
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
        *,
        threshold_method: str,
        window_periods: int | None,
        min_periods: int,
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
            "threshold_method": threshold_method,
            "window_periods": window_periods,
            "min_periods": min_periods,
            "n_per_regime": counts_labeled,
            "current_regime": current_regime,
            "timeline": timeline,
        }

    def _save(self, result: BacktestResult) -> None:
        readiness = _inference_readiness(
            result.classifiers,
            point_in_time=result.point_in_time,
        )
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
                "regime_threshold_method": result.regime_threshold_method,
                "bootstrap_iterations": result.bootstrap_iterations,
                "bootstrap_method": result.bootstrap_method,
                "bootstrap_min_finite_draw_fraction": MIN_FINITE_BOOTSTRAP_FRACTION,
                "edge_standard_error_method": EDGE_STANDARD_ERROR_METHOD,
                "p_value_method": EDGE_P_VALUE_METHOD,
                "multiple_testing_method": MULTIPLE_TESTING_METHOD,
                "multiple_testing_alpha": MULTIPLE_TESTING_ALPHA,
                "multiple_testing_family": MULTIPLE_TESTING_FAMILY,
                "multiple_testing_tests_in_family": result.inference_test_count,
                "inference_evidence_ready": readiness["ready"],
                "inference_readiness_policy": readiness["policy"],
                "inference_minimum_classified_weeks": readiness[
                    "minimum_classified_weeks"
                ],
                "inference_observed_classified_weeks": readiness[
                    "observed_classified_weeks"
                ],
                "live_evaluation_status": (
                    result.live_evaluation.get("status")
                    if result.live_evaluation is not None
                    else None
                ),
                "live_unique_signal_dates": (
                    result.live_evaluation.get("ledger", {}).get(
                        "unique_signal_dates"
                    )
                    if result.live_evaluation is not None
                    else 0
                ),
                # Legacy key describes the primary GLCI classifier.
                "burn_in_periods": GLCI_REGIME_MIN_PERIODS,
                "regime_window_periods": GLCI_REGIME_WINDOW,
                "nfci_burn_in_periods": BURN_IN_PERIODS,
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

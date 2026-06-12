"""Tests for the Track Record backtest (src/indicators/backtest.py).

The most important property tested here: the expanding-window regime
classifier must be free of look-ahead bias.
"""
import numpy as np
import pandas as pd
import pytest

from src.indicators.backtest import (
    BURN_IN_PERIODS,
    MIN_OBS_PER_REGIME,
    _group_stats,
    _sanitize_json,
    block_bootstrap_ci,
    compute_forward_returns,
    expanding_zscore_regime,
)


def weekly_series(values, start="2018-01-05"):
    idx = pd.date_range(start, periods=len(values), freq="W-FRI")
    return pd.Series(np.asarray(values, dtype=float), index=idx)


class TestExpandingZscoreRegime:
    def test_burn_in_period_is_unclassified(self):
        s = weekly_series(np.random.default_rng(0).normal(size=120))
        out = expanding_zscore_regime(s)
        assert out["zscore"].iloc[: BURN_IN_PERIODS - 1].isna().all()
        assert out["regime"].iloc[: BURN_IN_PERIODS - 1].isna().all()
        assert pd.notna(out["zscore"].iloc[BURN_IN_PERIODS - 1])

    def test_no_lookahead_bias(self):
        """Changing future observations must not change past classifications."""
        rng = np.random.default_rng(1)
        base = rng.normal(size=150)
        shocked = base.copy()
        shocked[120:] += 50  # massive future shock

        a = expanding_zscore_regime(weekly_series(base))
        b = expanding_zscore_regime(weekly_series(shocked))

        pd.testing.assert_frame_equal(a.iloc[:120], b.iloc[:120])

    def test_zscore_matches_manual_expanding_calculation(self):
        s = weekly_series(np.arange(1, 80, dtype=float))
        out = expanding_zscore_regime(s)
        t = 60  # arbitrary point past burn-in
        history = s.iloc[: t + 1]
        expected = (s.iloc[t] - history.mean()) / history.std()
        assert out["zscore"].iloc[t] == pytest.approx(expected)

    def test_regime_thresholds(self):
        # Flat history then a huge spike -> spike classified loose (z > 1)
        values = list(np.random.default_rng(2).normal(0, 1, 100)) + [25.0]
        out = expanding_zscore_regime(weekly_series(values))
        assert out["regime"].iloc[-1] == 1
        # Symmetric: huge negative spike -> tight
        values[-1] = -25.0
        out = expanding_zscore_regime(weekly_series(values))
        assert out["regime"].iloc[-1] == -1


class TestForwardReturns:
    def test_forward_return_formula(self):
        prices = weekly_series([100, 110, 121, 133.1, 146.41])
        out = compute_forward_returns(prices, horizons=[1, 2])
        # fwd_1w at t0 = 110/100 - 1
        assert out["fwd_1w"].iloc[0] == pytest.approx(0.10)
        # fwd_2w at t0 = 121/100 - 1
        assert out["fwd_2w"].iloc[0] == pytest.approx(0.21)

    def test_tail_has_no_future_data(self):
        prices = weekly_series(np.linspace(100, 200, 30))
        out = compute_forward_returns(prices, horizons=[4])
        assert out["fwd_4w"].iloc[-4:].isna().all()
        assert out["fwd_4w"].iloc[:-4].notna().all()


class TestBlockBootstrap:
    def test_constant_series_yields_degenerate_ci(self):
        values = np.full(100, 0.05)
        low, high = block_bootstrap_ci(values, np.mean, block_size=4, n_iter=200)
        assert low == pytest.approx(0.05)
        assert high == pytest.approx(0.05)

    def test_too_few_observations_returns_nan(self):
        low, high = block_bootstrap_ci(np.ones(5), np.mean, block_size=4)
        assert np.isnan(low) and np.isnan(high)

    def test_ci_brackets_the_sample_statistic(self):
        rng = np.random.default_rng(3)
        values = rng.normal(0.01, 0.02, 300)
        low, high = block_bootstrap_ci(values, np.mean, block_size=13, n_iter=500)
        assert low < np.mean(values) < high

    def test_deterministic_with_seeded_rng(self):
        values = np.random.default_rng(4).normal(size=200)
        a = block_bootstrap_ci(values, np.median, block_size=4, n_iter=100,
                               rng=np.random.default_rng(42))
        b = block_bootstrap_ci(values, np.median, block_size=4, n_iter=100,
                               rng=np.random.default_rng(42))
        assert a == b


class TestGroupStats:
    def test_all_positive_returns_have_perfect_hit_rate(self):
        rng = np.random.default_rng(5)
        returns = np.abs(rng.normal(0.02, 0.01, 100)) + 1e-9
        stats = _group_stats(returns, block_size=4, rng=rng)
        assert stats["hit_rate"] == pytest.approx(1.0)
        assert stats["n"] == 100
        assert stats["median"] > 0

    def test_below_minimum_observations_returns_nones(self):
        rng = np.random.default_rng(6)
        stats = _group_stats(np.ones(MIN_OBS_PER_REGIME - 1), block_size=4, rng=rng)
        assert stats["median"] is None
        assert stats["hit_rate"] is None
        assert stats["n"] == MIN_OBS_PER_REGIME - 1

    def test_nan_values_are_excluded(self):
        rng = np.random.default_rng(7)
        values = np.concatenate([np.full(50, 0.01), np.full(10, np.nan)])
        stats = _group_stats(values, block_size=4, rng=rng)
        assert stats["n"] == 50


class TestSanitizeJson:
    def test_replaces_non_finite_floats(self):
        payload = {
            "a": float("nan"),
            "b": [1.0, float("inf"), {"c": float("-inf")}],
            "d": "text",
            "e": 3,
        }
        out = _sanitize_json(payload)
        assert out["a"] is None
        assert out["b"][1] is None
        assert out["b"][2]["c"] is None
        assert out["d"] == "text" and out["e"] == 3

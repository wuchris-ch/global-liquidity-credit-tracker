"""Tests for the Track Record backtest (src/indicators/backtest.py).

The expanding regime threshold must not use future observations. Separate
tests assert that the reconstructed upstream history is disclosed as such.
"""

import numpy as np
import pandas as pd
import pytest

import src.indicators.backtest as backtest_module
from src.indicators.backtest import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_METHOD,
    BURN_IN_PERIODS,
    ENTRY_LAG_WEEKS,
    MIN_OBS_PER_REGIME,
    BacktestComputer,
    BacktestResult,
    _moving_block_indices,
    _paired_regime_stats,
    _sanitize_json,
    _to_weekly_grid,
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
    def test_backtest_rejects_missing_glci_weeks_instead_of_carrying_them(self):
        class GappedStorage:
            @staticmethod
            def load_curated(_category, _name):
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2024-01-05", "2024-01-19"]),
                        "value": [100.0, 101.0],
                    }
                )

        with pytest.raises(ValueError, match="missing W-FRI observations"):
            BacktestComputer(
                fetcher=object(),
                storage=GappedStorage(),
            ).compute(verbose=False)

    def test_forward_return_formula(self):
        prices = weekly_series([100, 105, 126, 138.6, 180])
        out = compute_forward_returns(prices, horizons=[1, 2])
        # The t0 signal enters at t1, then exits one or two calendar weeks later.
        assert out["fwd_1w"].iloc[0] == pytest.approx(126 / 105 - 1)
        assert out["fwd_2w"].iloc[0] == pytest.approx(138.6 / 105 - 1)

    def test_tail_has_no_future_data(self):
        prices = weekly_series(np.linspace(100, 200, 30))
        out = compute_forward_returns(prices, horizons=[4])
        assert out["fwd_4w"].iloc[-(4 + ENTRY_LAG_WEEKS) :].isna().all()
        assert out["fwd_4w"].iloc[: -(4 + ENTRY_LAG_WEEKS)].notna().all()

    def test_zero_lag_can_be_requested_explicitly(self):
        prices = weekly_series([100, 105, 126])
        out = compute_forward_returns(prices, horizons=[1], entry_lag_weeks=0)
        assert out["fwd_1w"].iloc[0] == pytest.approx(0.05)

    def test_irregular_rows_are_rejected(self):
        prices = pd.Series(
            [100.0, 101.0, 103.0],
            index=pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-26"]),
        )
        with pytest.raises(ValueError, match="complete W-FRI grid"):
            compute_forward_returns(prices, horizons=[1])

    def test_raw_observations_are_placed_on_explicit_weekly_grid(self):
        raw = pd.Series(
            [100.0, 110.0],
            index=pd.to_datetime(["2024-01-05", "2024-01-26"]),
        )
        weekly = _to_weekly_grid(
            raw,
            name="test prices",
            carry_forward_weeks=1,
        )
        assert weekly.index.equals(
            pd.date_range("2024-01-05", "2024-01-26", freq="W-FRI")
        )
        assert weekly.iloc[0] == pytest.approx(100.0)
        assert weekly.iloc[1] == pytest.approx(100.0)
        assert pd.isna(weekly.iloc[2])
        assert weekly.iloc[3] == pytest.approx(110.0)

    def test_incomplete_week_does_not_get_future_friday_label(self):
        raw = pd.Series(
            [100.0, 103.0],
            index=pd.to_datetime(["2024-01-05", "2024-01-10"]),
        )
        weekly = _to_weekly_grid(raw, name="test prices")

        assert weekly.index.max() == pd.Timestamp("2024-01-05")
        assert pd.Timestamp("2024-01-12") not in weekly.index


class TestPairedCalendarBootstrap:
    def test_unconditional_edge_uses_only_classifier_eligible_weeks(self):
        returns = np.concatenate([np.full(60, -0.01), np.full(90, 0.01)])
        regimes = np.concatenate([np.full(60, np.nan), np.ones(90)])

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(42),
            n_iter=300,
        )[1]

        assert stats["hit_rate"] == pytest.approx(1.0)
        assert stats["edge"] == pytest.approx(0.0)
        assert stats["ci_edge_low"] == pytest.approx(0.0)
        assert stats["ci_edge_high"] == pytest.approx(0.0)

    def test_moving_blocks_preserve_adjacency(self):
        block_size = 4
        sampled = _moving_block_indices(
            23,
            block_size,
            np.random.default_rng(42),
        )

        assert len(sampled) == 23
        for start in range(0, len(sampled), block_size):
            block = sampled[start : start + block_size]
            assert np.diff(block).tolist() == [1] * (len(block) - 1)

    def test_deterministic_paired_intervals_with_seeded_rng(self):
        data_rng = np.random.default_rng(4)
        returns = data_rng.normal(size=450)
        regimes = np.tile(np.array([-1.0, 0.0, 1.0]), 150)

        a = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(42),
            n_iter=300,
        )
        b = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(42),
            n_iter=300,
        )

        assert a == b

    def test_null_edge_interval_crosses_zero(self):
        data_rng = np.random.default_rng(123)
        returns = data_rng.normal(size=600)
        regimes = np.tile(np.array([-1.0, 0.0, 1.0]), 200)

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(42),
            n_iter=600,
        )[1]

        assert stats["ci_edge_low"] < 0 < stats["ci_edge_high"]

    def test_strong_effect_edge_interval_excludes_zero(self):
        regimes = np.tile(np.array([-1.0, 0.0, 1.0]), 200)
        returns = np.where(regimes == 1, 0.02, -0.01)

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(42),
            n_iter=400,
        )[1]

        assert stats["hit_rate"] == pytest.approx(1.0)
        assert stats["edge"] == pytest.approx(0.6667)
        assert stats["ci_edge_low"] > 0
        assert stats["ci_edge_high"] > stats["ci_edge_low"]

    def test_calendar_gap_rows_are_not_compressed_before_sampling(self, monkeypatch):
        returns = np.resize(np.array([0.01, -0.01]), 120)
        regimes = np.full(120, np.nan)
        regimes[::4] = 1
        observed_lengths = []
        original = backtest_module._moving_block_indices

        def recording_sampler(n_observations, block_size, rng):
            observed_lengths.append(n_observations)
            return original(n_observations, block_size, rng)

        monkeypatch.setattr(
            backtest_module,
            "_moving_block_indices",
            recording_sampler,
        )
        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=4,
            rng=np.random.default_rng(9),
            n_iter=40,
            min_subgroup_obs=5,
            min_finite_draws=20,
        )[1]

        assert observed_lengths == [len(returns)] * 40
        assert stats["ci_hit_rate_low"] is not None
        assert stats["ci_edge_low"] is not None

    def test_too_few_subgroup_observations_returns_nones(self):
        returns = np.ones(80)
        regimes = np.zeros(80)
        regimes[: MIN_OBS_PER_REGIME - 1] = 1

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=4,
            rng=np.random.default_rng(6),
            n_iter=40,
        )[1]

        assert stats["median"] is None
        assert stats["hit_rate"] is None
        assert stats["edge"] is None
        assert stats["ci_edge_low"] is None
        assert stats["n"] == MIN_OBS_PER_REGIME - 1

    def test_nan_values_are_excluded_without_removing_internal_weeks(self):
        regimes = np.tile(np.array([-1.0, 0.0, 1.0]), 40)
        returns = np.full(120, 0.01)
        returns[[2, 5, 8, 11, 14]] = np.nan

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=4,
            rng=np.random.default_rng(7),
            n_iter=100,
        )[1]

        assert stats["n"] == 35
        assert stats["hit_rate"] == pytest.approx(1.0)

    def test_insufficient_finite_draws_suppresses_intervals(self):
        returns = np.resize(np.array([0.01, -0.01]), 200)
        regimes = np.zeros(200)
        regimes[:MIN_OBS_PER_REGIME] = 1

        stats = _paired_regime_stats(
            returns,
            regimes,
            block_size=13,
            rng=np.random.default_rng(7),
            n_iter=200,
        )[1]

        assert stats["edge"] is not None
        assert stats["ci_hit_rate_low"] is None
        assert stats["ci_edge_low"] is None


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


class TestBacktestMetadata:
    def test_payload_discloses_reconstructed_history_and_execution_clock(self):
        payload = BacktestResult(
            computed_at="2026-01-01T00:00:00",
            date_range=("2020-01-03", "2025-12-26"),
            horizons=[4, 13, 26],
            classifiers={},
            assets=[],
        ).to_dict()

        assert payload["frequency"] == "W-FRI"
        assert payload["entry_lag_weeks"] == 1
        assert payload["historical_mode"] == "reconstructed_current_vintage"
        assert payload["point_in_time"] is False
        assert payload["regime_threshold_method"] == "expanding_zscore"
        assert payload["bootstrap_method"] == BOOTSTRAP_METHOD
        assert payload["bootstrap_iterations"] == BOOTSTRAP_ITERATIONS

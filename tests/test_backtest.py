"""Tests for the Track Record backtest (src/indicators/backtest.py).

The GLCI backtest must reproduce the live rolling classifier. The expanding
classifier remains covered separately for the NFCI benchmark.
"""

import numpy as np
import pandas as pd
import pytest

import src.indicators.backtest as backtest_module
from src.indicators.backtest import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_METHOD,
    BURN_IN_PERIODS,
    EDGE_P_VALUE_METHOD,
    EDGE_STANDARD_ERROR_METHOD,
    ENTRY_LAG_WEEKS,
    GLCI_REGIME_METHOD,
    GLCI_REGIME_MIN_PERIODS,
    GLCI_REGIME_WINDOW,
    MIN_OBS_PER_REGIME,
    MIN_CLASSIFIED_WEEKS_FOR_SUPPORT,
    MULTIPLE_TESTING_ALPHA,
    MULTIPLE_TESTING_FAMILY,
    MULTIPLE_TESTING_METHOD,
    AssetBacktestResult,
    BacktestComputer,
    BacktestResult,
    _apply_multiple_testing,
    _benjamini_yekutieli_qvalues,
    _inference_readiness,
    _moving_block_indices,
    _paired_regime_stats,
    _sanitize_json,
    _to_weekly_grid,
    compute_forward_returns,
    expanding_zscore_regime,
    rolling_zscore_regime,
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


class TestRollingZscoreRegime:
    def test_matches_production_rolling_calculation(self):
        s = weekly_series(np.arange(1, 140, dtype=float))
        out = rolling_zscore_regime(s)
        t = 120
        history = s.iloc[t - GLCI_REGIME_WINDOW + 1 : t + 1]
        expected = (s.iloc[t] - history.mean()) / history.std()

        assert out["zscore"].iloc[t] == pytest.approx(expected)

    def test_warmup_is_unclassified(self):
        s = weekly_series(np.arange(1, 60, dtype=float))
        out = rolling_zscore_regime(s)

        assert out["zscore"].iloc[: GLCI_REGIME_MIN_PERIODS - 1].isna().all()
        assert out["regime"].iloc[: GLCI_REGIME_MIN_PERIODS - 1].isna().all()
        assert pd.notna(out["regime"].iloc[GLCI_REGIME_MIN_PERIODS - 1])

    def test_future_values_do_not_change_past_labels(self):
        rng = np.random.default_rng(8)
        base = rng.normal(size=180)
        shocked = base.copy()
        shocked[150:] += 25

        a = rolling_zscore_regime(weekly_series(base))
        b = rolling_zscore_regime(weekly_series(shocked))

        pd.testing.assert_frame_equal(a.iloc[:150], b.iloc[:150])


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
        assert stats["edge_standard_error"] == pytest.approx(0.0)
        assert stats["p_value"] == pytest.approx(1.0)

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
        assert stats["edge_standard_error"] > 0
        assert stats["p_value"] < 0.001

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
        assert stats["edge_standard_error"] is None
        assert stats["p_value"] is None


class TestMultipleTesting:
    def test_by_qvalues_match_hand_calculation_and_preserve_missing_cells(self):
        adjusted = _benjamini_yekutieli_qvalues(
            [0.01, 0.04, 0.03, 0.002, None]
        )

        assert adjusted[0] == pytest.approx(0.0416666667)
        assert adjusted[1] == pytest.approx(0.0833333333)
        assert adjusted[2] == pytest.approx(0.0833333333)
        assert adjusted[3] == pytest.approx(0.0166666667)
        assert adjusted[4] is None

    @pytest.mark.parametrize("p_value", [-0.01, 1.01, float("nan")])
    def test_by_rejects_invalid_p_values(self, p_value):
        with pytest.raises(ValueError, match="between zero and one"):
            _benjamini_yekutieli_qvalues([p_value])

    def test_one_family_spans_assets_and_classifiers(self):
        glci_cell = {"p_value": 0.01}
        nfci_cell = {"p_value": 0.04}
        second_asset_cell = {"p_value": 0.20}
        untested_cell = {"p_value": None}
        assets = [
            AssetBacktestResult(
                asset_id="asset_a",
                name="Asset A",
                category="risk",
                base_rates={},
                results={
                    "glci": {"loose": {4: glci_cell}},
                    "nfci": {"loose": {4: nfci_cell}},
                },
            ),
            AssetBacktestResult(
                asset_id="asset_b",
                name="Asset B",
                category="risk",
                base_rates={},
                results={
                    "glci": {
                        "tight": {13: second_asset_cell},
                        "neutral": {13: untested_cell},
                    }
                },
            ),
        ]

        test_count = _apply_multiple_testing(assets, alpha=0.10)

        assert test_count == 3
        assert glci_cell["q_value"] == pytest.approx(0.055)
        assert glci_cell["fdr_significant"] is True
        assert nfci_cell["q_value"] == pytest.approx(0.11)
        assert nfci_cell["fdr_significant"] is False
        assert second_asset_cell["q_value"] == pytest.approx(0.3666666667)
        assert second_asset_cell["fdr_significant"] is False
        assert untested_cell["q_value"] is None
        assert untested_cell["fdr_significant"] is None

    def test_support_readiness_requires_history_and_every_regime(self):
        not_ready = _inference_readiness(
            {
                "glci": {
                    "n_per_regime": {"tight": 1, "neutral": 65, "loose": 53}
                }
            }
        )

        assert not_ready["ready"] is False
        assert not_ready["observed_classified_weeks"] == 119
        assert not_ready["minimum_classified_weeks"] == MIN_CLASSIFIED_WEEKS_FOR_SUPPORT
        assert not_ready["reasons"] == [
            "point_in_time_history_unavailable",
            "classified_history_below_260_weeks",
            "tight_regime_below_20_observations",
        ]

        ready = _inference_readiness(
            {
                "glci": {
                    "n_per_regime": {"tight": 80, "neutral": 120, "loose": 80}
                }
            },
            point_in_time=True,
        )
        assert ready["ready"] is True
        assert ready["reasons"] == []


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
        assert payload["regime_threshold_method"] == GLCI_REGIME_METHOD
        assert payload["bootstrap_method"] == BOOTSTRAP_METHOD
        assert payload["bootstrap_iterations"] == BOOTSTRAP_ITERATIONS
        assert payload["min_obs_per_regime"] == MIN_OBS_PER_REGIME
        assert payload["inference"] == {
            "edge_standard_error_method": EDGE_STANDARD_ERROR_METHOD,
            "p_value_method": EDGE_P_VALUE_METHOD,
            "multiple_testing_method": MULTIPLE_TESTING_METHOD,
            "multiple_testing_alpha": MULTIPLE_TESTING_ALPHA,
            "multiple_testing_family": MULTIPLE_TESTING_FAMILY,
            "tests_in_family": 0,
            "readiness": {
                "ready": False,
                "policy": "point_in_time_minimum_history_and_all_regimes",
                "classifier": "glci",
                "point_in_time_history_required": True,
                "point_in_time_history": False,
                "minimum_classified_weeks": 260,
                "observed_classified_weeks": 0,
                "minimum_observations_per_regime": 20,
                "regime_observations": {
                    "tight": 0,
                    "neutral": 0,
                    "loose": 0,
                },
                "reasons": [
                    "point_in_time_history_unavailable",
                    "classified_history_below_260_weeks",
                    "tight_regime_below_20_observations",
                    "neutral_regime_below_20_observations",
                    "loose_regime_below_20_observations",
                ],
            },
        }
        assert "live_evaluation" not in payload

    def test_payload_includes_observed_live_evaluation_when_computed(self):
        live_evaluation = {
            "status": "collecting",
            "methodology": {"signal_recorded_before_outcome": True},
            "ledger": {"unique_signal_dates": 1},
            "assets": [],
        }
        payload = BacktestResult(
            computed_at="2026-07-14T00:00:00",
            date_range=("2026-07-10", "2026-07-10"),
            horizons=[4, 13, 26],
            classifiers={},
            assets=[],
            live_evaluation=live_evaluation,
        ).to_dict()

        assert payload["live_evaluation"] == live_evaluation

    def test_classifier_metadata_discloses_distinct_clocks(self):
        computer = BacktestComputer(fetcher=object(), storage=object())
        values = weekly_series(np.arange(1, 130, dtype=float))

        glci_meta = computer._classifier_meta(
            "glci",
            rolling_zscore_regime(values),
            values,
            threshold_method=GLCI_REGIME_METHOD,
            window_periods=GLCI_REGIME_WINDOW,
            min_periods=GLCI_REGIME_MIN_PERIODS,
        )
        nfci_meta = computer._classifier_meta(
            "nfci",
            expanding_zscore_regime(values),
            values,
            threshold_method="expanding_zscore",
            window_periods=None,
            min_periods=BURN_IN_PERIODS,
        )

        assert glci_meta["window_periods"] == 104
        assert glci_meta["min_periods"] == 20
        assert nfci_meta["window_periods"] is None
        assert nfci_meta["min_periods"] == 52

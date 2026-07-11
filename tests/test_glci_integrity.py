"""Regression tests for GLCI sign ownership and observation alignment."""

import numpy as np
import pandas as pd
import pytest
from src.indicators.factors import (
    DataQualityReport,
    FeatureMetadata,
    FeatureMatrixBuilder,
    get_component_signs,
    get_pillar_signs,
)
from src.indicators.glci import (
    GLCIComputer,
    GLCIPillarResult,
    _standardize_pillar_factors,
    _validate_factor_coverage,
)
from src.indicators.transforms import compute_growth_rate


class _StaticFetcher:
    def __init__(self, data: pd.DataFrame):
        self.data = data

    def fetch_series(self, *_args, **_kwargs) -> pd.DataFrame:
        return self.data.copy()


def _build_single_component_feature(
    monkeypatch,
    raw: pd.DataFrame,
    transform: str,
    sign: int,
    *,
    target_freq: str,
    source_frequency: str,
) -> tuple[pd.Series, list[FeatureMetadata]]:
    monkeypatch.setattr(
        "src.indicators.factors.get_index_config",
        lambda _index_id: {
            "pillars": {
                "test": {
                    "components": [
                        {
                            "series": "test_series",
                            "sign": sign,
                            "transform": transform,
                        }
                    ]
                }
            }
        },
    )
    monkeypatch.setattr(
        "src.indicators.factors.get_series_config",
        lambda _series_id: {
            "unit": "index",
            "frequency": source_frequency,
        },
    )
    matrix, metadata = FeatureMatrixBuilder(
        fetcher=_StaticFetcher(raw)
    ).build_feature_matrix("test_index", target_freq=target_freq)
    return matrix[f"test_series_{transform}"], metadata


class TestFactorCoverageGates:
    def test_rejects_two_transforms_from_only_one_active_series(self):
        loadings = pd.Series(
            {
                "source_a_zscore": 0.7,
                "source_a_growth": 0.6,
                "source_b_zscore": 0.0,
                "source_c_zscore": 0.0,
            }
        )
        mapping = {
            "source_a_zscore": "source_a",
            "source_a_growth": "source_a",
            "source_b_zscore": "source_b",
            "source_c_zscore": "source_c",
        }

        with pytest.raises(ValueError, match="distinct active source series"):
            _validate_factor_coverage(
                loadings,
                {feature: 1 for feature in loadings.index},
                mapping,
            )

    def test_rejects_majority_constraint_exclusion(self):
        loadings = pd.Series(
            {
                "source_a_zscore": 0.7,
                "source_b_zscore": 0.6,
                "source_c_zscore": 0.0,
                "source_d_zscore": 0.0,
                "source_e_zscore": 0.0,
            }
        )
        mapping = {
            feature: feature.removesuffix("_zscore")
            for feature in loadings.index
        }

        with pytest.raises(ValueError, match="excluded 60%"):
            _validate_factor_coverage(
                loadings,
                {feature: 1 for feature in loadings.index},
                mapping,
            )

    def test_rejects_single_series_loading_dominance(self):
        loadings = pd.Series(
            {
                "source_a_zscore": 0.90,
                "source_b_zscore": 0.08,
                "source_c_zscore": 0.02,
            }
        )
        mapping = {
            feature: feature.removesuffix("_zscore")
            for feature in loadings.index
        }

        with pytest.raises(ValueError, match="loading concentration is 90%"):
            _validate_factor_coverage(
                loadings,
                {feature: 1 for feature in loadings.index},
                mapping,
            )


class TestWeightPolicy:
    def test_unsupported_weight_optimization_is_rejected(self):
        computer = GLCIComputer(fetcher=object(), storage=object())

        with pytest.raises(NotImplementedError, match="fixed configured policy weights"):
            computer.compute(
                optimize_weights=True,
                verbose=False,
            )


class TestFactorAlignment:
    def test_zero_denominator_growth_is_sanitized_before_standardizing(self, monkeypatch):
        values = np.concatenate(
            [
                np.zeros(60),
                np.linspace(1.0, 120.0, 120),
            ]
        )
        raw = pd.DataFrame(
            {
                "date": pd.date_range(
                    "2021-01-01",
                    periods=len(values),
                    freq="W-FRI",
                ),
                "value": values,
            }
        )

        growth, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "growth",
            1,
            target_freq="W",
            source_frequency="weekly",
        )

        assert growth.notna().any()
        assert np.isfinite(growth.dropna()).all()

    def test_zero_observation_transform_is_excluded_before_factor_fit(self, monkeypatch):
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-05", periods=30, freq="W-FRI"),
                "value": np.linspace(100.0, 130.0, 30),
            }
        )
        monkeypatch.setattr(
            "src.indicators.factors.get_index_config",
            lambda _index_id: {
                "pillars": {
                    "test": {
                        "components": [
                            {
                                "series": "test_series",
                                "sign": 1,
                                "transform": ["growth", "level"],
                            }
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(
            "src.indicators.factors.get_series_config",
            lambda _series_id: {"unit": "index", "frequency": "weekly"},
        )

        matrix, metadata = FeatureMatrixBuilder(
            fetcher=_StaticFetcher(raw)
        ).build_feature_matrix("test_index", target_freq="W")

        assert "test_series_growth" not in matrix
        assert "test_series_level" in matrix
        assert [item.transform for item in metadata] == ["level"]

    def test_alignment_keeps_leading_history_missing_and_uses_weekly_clock(self):
        features = {
            "early": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-05"]),
                    "early": [1.0],
                }
            ),
            "late": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-26"]),
                    "late": [2.0],
                }
            ),
        }

        aligned = FeatureMatrixBuilder()._align_features(
            features,
            target_freq="W",
        )

        expected_dates = pd.date_range("2024-01-05", "2024-01-26", freq="W-FRI")
        assert pd.DatetimeIndex(aligned["date"]).equals(expected_dates)
        assert aligned["late"].iloc[:3].isna().all()
        assert aligned["late"].iloc[3] == 2.0
        assert aligned["early"].iloc[1:].isna().all()

    def test_monthly_input_is_regularized_before_52_week_growth(self):
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-31", periods=36, freq="ME"),
                "value": np.arange(100.0, 136.0),
            }
        )
        builder = FeatureMatrixBuilder()
        weekly = builder._regularize_series(raw, "monthly", "W")
        growth = compute_growth_rate(weekly, periods=52)

        last_valid = growth["growth_rate"].last_valid_index()
        assert last_valid is not None
        assert (
            growth.loc[last_valid, "date"] - growth.loc[last_valid - 52, "date"]
        ).days == 364
        # One unit per monthly release means a 52-week comparison should span
        # about 12 releases, not 52 monthly rows.
        level_change = (
            growth.loc[last_valid, "value"] - growth.loc[last_valid - 52, "value"]
        )
        assert 11 <= level_change <= 13

    def test_incomplete_week_does_not_create_future_friday(self):
        raw = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05", "2024-01-10"]),
                "value": [100.0, 110.0],
            }
        )
        weekly = FeatureMatrixBuilder()._regularize_series(raw, "daily", "W")

        assert weekly["date"].max() == pd.Timestamp("2024-01-05")
        assert pd.Timestamp("2024-01-12") not in set(weekly["date"])

    def test_staleness_allowance_respects_source_frequency(self):
        now = pd.Timestamp.now().normalize()
        metadata = [
            FeatureMetadata(
                series_id="us_bank_credit_total",
                pillar="credit",
                country="US",
                transform="zscore",
                unit="index",
                sign=1,
                source_frequency="daily",
                data_quality=1.0,
                last_updated=str((now - pd.Timedelta(days=11)).date()),
            ),
            FeatureMetadata(
                series_id="bis_credit_us",
                pillar="credit",
                country="US",
                transform="zscore",
                unit="percent",
                sign=1,
                source_frequency="quarterly",
                data_quality=1.0,
                last_updated=str((now - pd.Timedelta(days=100)).date()),
            ),
        ]

        report = FeatureMatrixBuilder().validate_pillar_data(
            "global_liquidity_credit_index",
            "credit",
            pd.DataFrame(),
            metadata,
        )
        stale_ids = {series_id for series_id, _days in report.stale_series}

        assert "us_bank_credit_total" in stale_ids
        assert "bis_credit_us" not in stale_ids


class TestComponentOrientation:
    def test_negative_sign_is_applied_after_percentage_growth(self, monkeypatch):
        periods = 120
        step = np.arange(periods, dtype=float)
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2021-01-01", periods=periods, freq="W-FRI"),
                "value": 100 * np.exp(0.002 * step + 0.00005 * step**2),
            }
        )

        positive, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "growth",
            1,
            target_freq="W",
            source_frequency="weekly",
        )
        negative, metadata = _build_single_component_feature(
            monkeypatch,
            raw,
            "growth",
            -1,
            target_freq="W",
            source_frequency="weekly",
        )

        valid = positive.notna() & negative.notna()
        assert valid.any()
        np.testing.assert_allclose(negative[valid], -positive[valid])
        assert positive[valid].iloc[-1] > 0
        assert negative[valid].iloc[-1] < 0
        assert metadata[0].sign == 1

    def test_growth_feature_is_not_a_standardized_raw_level(self, monkeypatch):
        periods = 140
        step = np.arange(periods, dtype=float)
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2021-01-01", periods=periods, freq="W-FRI"),
                "value": 100 * np.exp(0.001 * step + 0.00008 * step**2),
            }
        )

        growth, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "growth",
            1,
            target_freq="W",
            source_frequency="weekly",
        )
        level, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "level",
            1,
            target_freq="W",
            source_frequency="weekly",
        )

        valid = growth.notna() & level.notna()
        assert valid.any()
        assert not np.allclose(growth[valid], level[valid])

    def test_negative_sign_still_orients_differenced_impulse(self, monkeypatch):
        periods = 60
        step = np.arange(periods, dtype=float)
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2011-03-31", periods=periods, freq="QE"),
                "value": 100 + 0.02 * step**3,
            }
        )

        positive, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "impulse",
            1,
            target_freq="Q",
            source_frequency="quarterly",
        )
        negative, _ = _build_single_component_feature(
            monkeypatch,
            raw,
            "impulse",
            -1,
            target_freq="Q",
            source_frequency="quarterly",
        )

        valid = positive.notna() & negative.notna()
        assert valid.any()
        np.testing.assert_allclose(negative[valid], -positive[valid])
        assert positive[valid].iloc[-1] > 0
        assert negative[valid].iloc[-1] < 0


class TestStressDirection:
    def test_pillar_estimators_are_scaled_before_fixed_weights(self):
        dates = pd.date_range("2022-01-07", periods=80, freq="W-FRI")
        base = pd.Series(np.linspace(-2.0, 3.0, len(dates)), index=dates)

        standardized = _standardize_pillar_factors(
            {
                "large_scale": base * 100.0,
                "small_scale": base * 0.01,
            }
        )

        for factor in standardized.values():
            assert factor.mean() == pytest.approx(0.0, abs=1e-12)
            assert factor.std() == pytest.approx(1.0, abs=1e-12)
        pd.testing.assert_series_equal(
            standardized["large_scale"],
            standardized["small_scale"],
            check_names=False,
        )

    def test_component_and_pillar_signs_have_separate_ownership(self):
        components = get_component_signs(
            "global_liquidity_credit_index",
            "stress",
        )
        pillars = get_pillar_signs("global_liquidity_credit_index")

        assert components["ice_bofa_us_high_yield_spread"] == 1
        assert pillars["stress"] == -1

    def test_positive_stress_shock_reduces_final_glci(self, monkeypatch):
        dates = pd.date_range("2023-01-06", periods=120, freq="W-FRI")
        common = pd.Series(np.linspace(-2.0, 2.0, len(dates)), index=dates)
        raw_stress = common.iloc[20:]
        factors = {
            "liquidity": -common,
            "credit": -common.iloc[10:],
            "stress": raw_stress,
        }

        computer = GLCIComputer(fetcher=object(), storage=object())

        def fake_pillar_result(pillar_name, *_args, **_kwargs):
            return GLCIPillarResult(
                name=pillar_name,
                factor=factors[pillar_name],
                loadings=pd.DataFrame({"factor_1": [1.0]}, index=[pillar_name]),
                explained_variance=1.0,
                method="test",
                data_quality=None,
                metadata={
                    "n_variables": 1,
                    "used_series": [pillar_name],
                    "excluded_series": [],
                },
            )

        monkeypatch.setattr(computer, "_compute_pillar_factor", fake_pillar_result)
        result = computer.compute(target_freq="W", factor_method="pca", verbose=False)

        assert result.glci["date"].min() == dates[20]
        assert (result.glci["value"].diff().dropna() < 0).all()
        expected_stress = -raw_stress
        expected_stress = (
            expected_stress - expected_stress.mean()
        ) / expected_stress.std()
        pd.testing.assert_series_equal(
            result.pillars.set_index("date")["stress"],
            expected_stress,
            check_names=False,
            check_freq=False,
        )
        assert result.metadata["frequency"] == "W-FRI"
        assert result.metadata["historical_mode"] == "reconstructed_current_vintage"
        assert result.metadata["point_in_time"] is False
        assert result.metadata["pillar_weight_policy"] == "fixed_configured"
        stress_quality = result.metadata["pillar_stats"]["stress"]["data_quality"]
        assert stress_quality["loaded_series"] == 1
        assert stress_quality["used_series"] == ["stress"]
        assert stress_quality["excluded_series"] == []

    def test_failed_pillar_aborts_without_saving_partial_composite(self, monkeypatch):
        computer = GLCIComputer(fetcher=object(), storage=object())
        dates = pd.date_range("2024-01-05", periods=120, freq="W-FRI")
        computed_pillars = []
        saved_results = []

        def fake_pillar_result(pillar_name, *_args, **_kwargs):
            computed_pillars.append(pillar_name)
            if pillar_name == "credit":
                raise ValueError("credit input unavailable")
            return GLCIPillarResult(
                name=pillar_name,
                factor=pd.Series(0.0, index=dates),
                loadings=pd.DataFrame({"factor_1": [1.0]}, index=[pillar_name]),
                explained_variance=1.0,
                method="test",
                data_quality=None,
                metadata={"n_variables": 1, "used_series": [pillar_name]},
            )

        monkeypatch.setattr(computer, "_compute_pillar_factor", fake_pillar_result)
        monkeypatch.setattr(computer, "_save_results", saved_results.append)

        with pytest.raises(
            RuntimeError,
            match="configured pillar 'credit' failed",
        ):
            computer.compute(
                target_freq="W",
                factor_method="pca",
                save_output=True,
                verbose=False,
            )

        assert computed_pillars == ["liquidity", "credit"]
        assert saved_results == []

    def test_pillar_factor_keeps_trimmed_model_dates(self, monkeypatch):
        dates = pd.date_range("2020-01-03", periods=120, freq="W-FRI")
        rng = np.random.default_rng(12)
        common = np.cumsum(rng.normal(size=len(dates)))
        matrix = pd.DataFrame(
            {
                "date": dates,
                "early_zscore": common + rng.normal(0, 0.1, len(dates)),
                "late_zscore": common + rng.normal(0, 0.1, len(dates)),
            }
        )
        matrix.loc[:39, "late_zscore"] = np.nan

        computer = GLCIComputer(fetcher=object(), storage=object())
        quality = DataQualityReport(
            pillar="stress",
            total_series=2,
            loaded_series=2,
            missing_series=[],
            low_coverage_series=[],
            stale_series=[],
            sign_violations=[],
        )
        metadata = [
            FeatureMetadata(
                series_id=series_id,
                pillar="stress",
                country="US",
                transform="zscore",
                unit="index",
                sign=1,
                source_frequency="weekly",
                data_quality=1.0,
                last_updated="2026-07-03",
            )
            for series_id in ("early", "late")
        ]
        monkeypatch.setattr(
            computer.feature_builder,
            "build_pillar_matrix",
            lambda *_args, **_kwargs: (matrix, metadata),
        )
        monkeypatch.setattr(
            computer.feature_builder,
            "validate_pillar_data",
            lambda *_args, **_kwargs: quality,
        )

        result = computer._compute_pillar_factor(
            "stress",
            start_date=None,
            end_date=None,
            target_freq="W",
            method="pca",
            verbose=False,
        )

        assert result.factor.index.min() == dates[40]
        assert len(result.factor) == len(dates) - 40

    def test_near_constant_component_is_excluded_from_model_coverage(self, monkeypatch):
        dates = pd.date_range("2020-01-03", periods=120, freq="W-FRI")
        rng = np.random.default_rng(24)
        common = np.cumsum(rng.normal(size=len(dates)))
        matrix = pd.DataFrame(
            {
                "date": dates,
                "used_a_zscore": common + rng.normal(0, 0.1, len(dates)),
                "used_b_zscore": common + rng.normal(0, 0.1, len(dates)),
                "constant_zscore": np.ones(len(dates)),
            }
        )
        metadata = [
            FeatureMetadata(
                series_id=series_id,
                pillar="stress",
                country="US",
                transform="zscore",
                unit="index",
                sign=1,
                source_frequency="weekly",
                data_quality=1.0,
                last_updated="2026-07-03",
            )
            for series_id in ("used_a", "used_b", "constant")
        ]
        quality = DataQualityReport(
            pillar="stress",
            total_series=3,
            loaded_series=3,
            missing_series=[],
            low_coverage_series=[],
            stale_series=[],
            sign_violations=[],
        )
        computer = GLCIComputer(fetcher=object(), storage=object())
        monkeypatch.setattr(
            computer.feature_builder,
            "build_pillar_matrix",
            lambda *_args, **_kwargs: (matrix, metadata),
        )
        monkeypatch.setattr(
            computer.feature_builder,
            "validate_pillar_data",
            lambda *_args, **_kwargs: quality,
        )

        pillar_result = computer._compute_pillar_factor(
            "stress",
            start_date=None,
            end_date=None,
            target_freq="W",
            method="pca",
            verbose=False,
        )

        assert pillar_result.metadata["n_variables"] == 2
        assert set(pillar_result.metadata["used_series"]) == {"used_a", "used_b"}
        assert pillar_result.metadata["excluded_series"] == ["constant"]
        assert "constant_zscore" not in pillar_result.loadings.index

        monkeypatch.setattr(
            computer,
            "_compute_pillar_factor",
            lambda *_args, **_kwargs: pillar_result,
        )
        composite = computer.compute(
            target_freq="W", factor_method="pca", verbose=False
        )
        serialized = composite.metadata["pillar_stats"]["stress"]["data_quality"]
        assert serialized["available_series"] == 3
        assert serialized["loaded_series"] == 2
        assert set(serialized["used_series"]) == {"used_a", "used_b"}
        assert serialized["excluded_series"] == ["constant"]

    def test_pillar_constraint_excludes_opposite_feature(self, monkeypatch):
        dates = pd.date_range("2020-01-03", periods=160, freq="W-FRI")
        rng = np.random.default_rng(47)
        common = np.cumsum(rng.normal(size=len(dates)))
        matrix = pd.DataFrame(
            {
                "date": dates,
                "support_a_zscore": common + rng.normal(0, 0.1, len(dates)),
                "support_b_zscore": 0.8 * common + rng.normal(0, 0.1, len(dates)),
                "opposite_zscore": -common + rng.normal(0, 0.1, len(dates)),
            }
        )
        metadata = [
            FeatureMetadata(
                series_id=series_id,
                pillar="stress",
                country="US",
                transform="zscore",
                unit="index",
                sign=1,
                source_frequency="weekly",
                data_quality=1.0,
                last_updated="2026-07-03",
            )
            for series_id in ("support_a", "support_b", "opposite")
        ]
        quality = DataQualityReport(
            pillar="stress",
            total_series=3,
            loaded_series=3,
            missing_series=[],
            low_coverage_series=[],
            stale_series=[],
            sign_violations=[],
        )
        computer = GLCIComputer(fetcher=object(), storage=object())
        monkeypatch.setattr(
            computer.feature_builder,
            "build_pillar_matrix",
            lambda *_args, **_kwargs: (matrix, metadata),
        )
        monkeypatch.setattr(
            computer.feature_builder,
            "validate_pillar_data",
            lambda *_args, **_kwargs: quality,
        )

        result = computer._compute_pillar_factor(
            "stress",
            start_date=None,
            end_date=None,
            target_freq="W",
            method="pca_shrunk",
            verbose=False,
        )

        assert result.loadings.loc["opposite_zscore", "factor_1"] == pytest.approx(
            0.0,
            abs=1e-8,
        )
        assert "opposite_zscore" not in result.metadata["used_features"]
        assert "opposite_zscore" in result.metadata["excluded_features"]
        assert result.metadata["constraint_excluded_features"] == [
            "opposite_zscore"
        ]
        assert result.metadata["constraint_exclusion_share"] == pytest.approx(1 / 3)
        assert result.metadata["max_series_loading_share"] <= 0.60
        assert "opposite" in result.metadata["excluded_series"]
        assert quality.sign_violations == []

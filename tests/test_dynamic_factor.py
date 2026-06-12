"""Tests for factor extraction and combination (src/indicators/dynamic_factor.py)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.dynamic_factor import (
    DynamicFactorModel,
    combine_factors,
)


def make_factor_data(n=200, n_vars=5, seed=0):
    """Variables driven by one common factor plus idiosyncratic noise."""
    rng = np.random.default_rng(seed)
    factor = np.cumsum(rng.normal(0, 1, n))  # persistent latent factor
    data = {}
    for i in range(n_vars):
        loading = 0.5 + 0.5 * rng.random()
        noise = rng.normal(0, 0.5, n)
        data[f"x{i}"] = loading * factor + noise
    dates = pd.date_range("2018-01-05", periods=n, freq="W-FRI")
    return pd.DataFrame(data, index=dates), pd.Series(factor, index=dates)


class TestFactorExtraction:
    @pytest.mark.parametrize("method", ["pca", "pca_shrunk"])
    def test_recovers_common_factor(self, method):
        X, true_factor = make_factor_data()
        model = DynamicFactorModel(n_factors=1, method=method)
        model.fit(X)
        extracted = model.transform().iloc[:, 0]

        corr = abs(np.corrcoef(extracted.values, true_factor.values)[0, 1])
        assert corr > 0.95

    def test_positive_average_loading_orientation(self):
        # Series are pre-flipped upstream, so the factor must be oriented
        # with positive average loading: factor up = components up.
        X, _ = make_factor_data(seed=3)
        model = DynamicFactorModel(n_factors=1, method="pca")
        model.fit(X)
        assert model.get_loadings()["factor_1"].mean() > 0

    def test_explained_variance_is_high_for_one_factor_world(self):
        X, _ = make_factor_data(seed=4)
        model = DynamicFactorModel(n_factors=1, method="pca")
        model.fit(X)
        assert model.get_explained_variance() > 0.6

    def test_rejects_insufficient_data(self):
        X = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
        model = DynamicFactorModel(n_factors=1, min_observations=30)
        with pytest.raises(ValueError, match="validation failed"):
            model.fit(X)

    def test_near_constant_columns_are_dropped(self):
        X, _ = make_factor_data(seed=5)
        X["constant"] = 1.0
        model = DynamicFactorModel(n_factors=1, method="pca")
        model.fit(X)
        assert "constant" not in model.get_loadings().index

    def test_handles_missing_data(self):
        X, true_factor = make_factor_data(seed=6)
        X.iloc[10:20, 0] = np.nan  # punch holes in one variable
        model = DynamicFactorModel(n_factors=1, method="pca")
        model.fit(X)
        extracted = model.transform().iloc[:, 0]
        corr = abs(np.corrcoef(extracted.values, true_factor.values)[0, 1])
        assert corr > 0.9


class TestCombineFactors:
    def test_normalizes_to_mean_100_std_10(self):
        idx = pd.date_range("2020-01-03", periods=100, freq="W-FRI")
        rng = np.random.default_rng(7)
        factors = {
            "liquidity": pd.Series(rng.normal(size=100), index=idx),
            "credit": pd.Series(rng.normal(size=100), index=idx),
        }
        combined = combine_factors(factors, weights={"liquidity": 0.6, "credit": 0.4})
        assert combined.mean() == pytest.approx(100, abs=0.1)
        assert combined.std() == pytest.approx(10, abs=0.1)

    def test_weights_are_renormalized(self):
        idx = pd.date_range("2020-01-03", periods=50, freq="W-FRI")
        s = pd.Series(np.arange(50, dtype=float), index=idx)
        # Weights 2 and 2 should behave identically to 0.5 and 0.5
        a = combine_factors({"x": s, "y": -s}, weights={"x": 2.0, "y": 2.0}, normalize=False)
        b = combine_factors({"x": s, "y": -s}, weights={"x": 0.5, "y": 0.5}, normalize=False)
        pd.testing.assert_series_equal(a, b)

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError):
            combine_factors({})

    def test_dominant_weight_dominates(self):
        idx = pd.date_range("2020-01-03", periods=100, freq="W-FRI")
        rng = np.random.default_rng(8)
        up = pd.Series(np.linspace(0, 10, 100) + rng.normal(0, 0.1, 100), index=idx)
        down = pd.Series(np.linspace(10, 0, 100) + rng.normal(0, 0.1, 100), index=idx)
        combined = combine_factors(
            {"up": up, "down": down}, weights={"up": 0.95, "down": 0.05}
        )
        # Composite should trend up like the dominant component
        assert combined.iloc[-10:].mean() > combined.iloc[:10].mean()

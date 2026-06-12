"""Tests for risk metrics (src/indicators/risk_metrics.py).

Covers the Sharpe ratio, max drawdown, and the full regime-conditioned
pipeline using stub data sources (no network).
"""
import numpy as np
import pandas as pd
import pytest

from src.indicators.risk_metrics import RiskMetricsComputer, ASSET_CONFIG
from conftest import StubFetcher, StubStorage, make_series


@pytest.fixture
def computer():
    return RiskMetricsComputer(fetcher=StubFetcher({}), storage=StubStorage())


class TestSharpe:
    def test_matches_textbook_formula(self, computer):
        rng = np.random.default_rng(0)
        excess = pd.Series(rng.normal(0.0005, 0.01, 500))
        expected = excess.mean() / excess.std() * np.sqrt(252)
        assert computer._compute_sharpe(excess) == pytest.approx(expected)

    def test_zero_volatility_returns_zero(self, computer):
        assert computer._compute_sharpe(pd.Series([0.01] * 100)) == 0.0

    def test_too_few_observations_returns_zero(self, computer):
        assert computer._compute_sharpe(pd.Series([0.01, 0.02, -0.01])) == 0.0


class TestMaxDrawdown:
    def test_known_drawdown(self, computer):
        # Peak 120 -> trough 60 = -50%
        prices = pd.Series([100, 120, 90, 60, 80, 110])
        assert computer._compute_max_drawdown(prices) == pytest.approx(-50.0)

    def test_monotonic_increase_has_zero_drawdown(self, computer):
        prices = pd.Series(np.linspace(100, 200, 50))
        assert computer._compute_max_drawdown(prices) == pytest.approx(0.0)

    def test_single_price_returns_zero(self, computer):
        assert computer._compute_max_drawdown(pd.Series([100.0])) == 0.0


def build_regime_world():
    """Synthetic world: 3 years of daily prices whose drift depends on regime.

    Year 1: tight (negative drift), year 2: neutral (flat),
    year 3: loose (positive drift).
    """
    daily = pd.date_range("2020-01-01", periods=756, freq="B")
    n = len(daily)
    third = n // 3

    rng = np.random.default_rng(11)
    drift = np.concatenate([
        np.full(third, -0.002),          # tight
        np.full(third, 0.0002),          # neutral
        np.full(n - 2 * third, 0.003),   # loose
    ])
    returns = drift + rng.normal(0, 0.005, n)
    prices = 100 * np.cumprod(1 + returns)

    # Weekly GLCI with matching regimes
    weekly = pd.date_range(daily.min(), daily.max(), freq="W-FRI")
    regimes = []
    for d in weekly:
        pos = np.searchsorted(daily, d)
        if pos < third:
            regimes.append(-1)
        elif pos < 2 * third:
            regimes.append(0)
        else:
            regimes.append(1)

    glci = pd.DataFrame({
        "date": weekly,
        "value": np.linspace(90, 110, len(weekly)),
        "zscore": 0.0,
        "regime": regimes,
    })

    price_df = make_series(daily, prices)
    rf_df = make_series(daily, np.full(n, 2.0))  # constant 2% annual T-bill
    return glci, price_df, rf_df


class TestRegimeConditionedPipeline:
    def test_returns_by_regime_reflect_construction(self):
        glci, price_df, rf_df = build_regime_world()

        fetcher = StubFetcher({"sp500_price": price_df, "treasury_3m": rf_df})
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=fetcher, storage=storage)

        glci_loaded = computer._load_glci_regimes()
        metrics = computer._compute_asset_metrics(
            "sp500_price", ASSET_CONFIG["sp500_price"], glci_loaded, None, None, None
        )

        # Drift was tight < neutral < loose by construction
        assert metrics.return_by_regime["tight"] < metrics.return_by_regime["neutral"]
        assert metrics.return_by_regime["neutral"] < metrics.return_by_regime["loose"]
        assert metrics.sharpe_by_regime["loose"] > 0
        assert metrics.sharpe_by_regime["tight"] < 0

    def test_full_compute_saves_results(self):
        glci, price_df, rf_df = build_regime_world()
        frames = {asset_id: price_df for asset_id in ASSET_CONFIG}
        frames["treasury_3m"] = rf_df

        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=StubFetcher(frames), storage=storage)

        result = computer.compute(save_output=True, verbose=False)

        assert len(result.assets) == len(ASSET_CONFIG)
        assert result.current_regime == "loose"
        assert ("risk", "risk_metrics") in storage.curated
        saved = storage.curated[("risk", "risk_metrics")]
        assert set(saved["asset_id"]) == set(ASSET_CONFIG)

    def test_rolling_sharpe_dates_align_with_input(self):
        glci, price_df, rf_df = build_regime_world()
        fetcher = StubFetcher({"sp500_price": price_df, "treasury_3m": rf_df})
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=fetcher, storage=storage)

        glci_loaded = computer._load_glci_regimes()
        metrics = computer._compute_asset_metrics(
            "sp500_price", ASSET_CONFIG["sp500_price"], glci_loaded, None, None, None
        )

        # Rolling window is 252 -> first ~252 observations produce no value
        n_returns = len(price_df) - 1  # first return is NaN
        assert 0 < len(metrics.rolling_sharpe_data) <= n_returns - 251
        first_date = pd.Timestamp(metrics.rolling_sharpe_data[0]["date"])
        assert first_date >= price_df["date"].iloc[251]

    def test_mixed_datetime_resolutions_still_merge(self):
        """Regression: pandas >= 3 refuses merge_asof across datetime units.

        In CI, the GLCI parquet roundtrip yields datetime64[us] dates while
        yfinance yields datetime64[s]; this killed every non-FRED asset on
        the published risk dashboard.
        """
        glci, price_df, rf_df = build_regime_world()
        glci = glci.copy()
        glci["date"] = glci["date"].astype("datetime64[us]")
        price_df = price_df.copy()
        price_df["date"] = price_df["date"].astype("datetime64[s]")
        rf_df = rf_df.copy()
        rf_df["date"] = rf_df["date"].astype("datetime64[s]")

        fetcher = StubFetcher({"sp500_price": price_df, "treasury_3m": rf_df})
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=fetcher, storage=storage)

        glci_loaded = computer._load_glci_regimes()
        rf_loaded = computer._load_risk_free_rate()
        metrics = computer._compute_asset_metrics(
            "sp500_price", ASSET_CONFIG["sp500_price"], glci_loaded, rf_loaded, None, None
        )
        assert metrics.return_by_regime["loose"] is not None

    def test_regime_matrix_shape(self):
        glci, price_df, rf_df = build_regime_world()
        frames = {asset_id: price_df for asset_id in ASSET_CONFIG}
        frames["treasury_3m"] = rf_df
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=StubFetcher(frames), storage=storage)

        result = computer.compute(save_output=False, verbose=False)
        matrix = result.regime_performance_matrix
        assert matrix["regimes"] == ["tight", "neutral", "loose"]
        assert len(matrix["assets"]) == len(ASSET_CONFIG)
        assert all(len(row) == 3 for row in matrix["sharpe_data"])

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


class MetadataStorage(StubStorage):
    """Stub storage that also exposes metadata passed to each save."""

    def __init__(self, curated=None):
        super().__init__(curated)
        self.saved_metadata = {}

    def save_curated(self, df, category, name, metadata=None):
        super().save_curated(df, category, name, metadata)
        self.saved_metadata[(category, name)] = metadata


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


class TestAssetSpecificAnnualization:
    def test_calendar_crypto_and_weekday_asset_use_different_clocks(self):
        n_returns = 399
        returns = 0.0007 + 0.004 * np.sin(np.arange(n_returns) / 9)
        prices = np.concatenate([[100.0], 100 * np.cumprod(1 + returns)])
        crypto_dates = pd.date_range("2020-01-01", periods=len(prices), freq="D")
        equity_dates = pd.date_range("2020-01-01", periods=len(prices), freq="B")

        first_date = min(crypto_dates.min(), equity_dates.min())
        last_date = max(crypto_dates.max(), equity_dates.max())
        weekly_dates = pd.date_range(
            first_date - pd.Timedelta(days=7), last_date, freq="W-FRI"
        )
        glci = pd.DataFrame({
            "date": weekly_dates,
            "value": 100 + np.linspace(0, 2, len(weekly_dates)),
            "regime": np.zeros(len(weekly_dates), dtype=int),
        })
        rf_dates = pd.date_range(first_date, last_date, freq="D")
        rf_df = make_series(rf_dates, np.full(len(rf_dates), 5.0))

        fetcher = StubFetcher({
            "bitcoin_price": make_series(crypto_dates, prices, source="yahoo"),
            "sp500_price": make_series(equity_dates, prices, source="yahoo"),
            "treasury_3m": rf_df,
        })
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=fetcher, storage=storage)
        glci_loaded = computer._load_glci_regimes()
        rf_loaded = computer._load_risk_free_rate()

        crypto = computer._compute_asset_metrics(
            "bitcoin_price", ASSET_CONFIG["bitcoin_price"],
            glci_loaded, rf_loaded, None, None,
        )
        equity = computer._compute_asset_metrics(
            "sp500_price", ASSET_CONFIG["sp500_price"],
            glci_loaded, rf_loaded, None, None,
        )

        realized = pd.Series(prices).pct_change().dropna()
        expected_crypto_excess = realized - 0.05 / 365
        expected_equity_excess = realized - 0.05 / 252

        assert crypto.annualized_return == pytest.approx(realized.mean() * 365 * 100)
        assert equity.annualized_return == pytest.approx(realized.mean() * 252 * 100)
        assert crypto.annualized_volatility == pytest.approx(
            realized.std() * np.sqrt(365) * 100
        )
        assert equity.annualized_volatility == pytest.approx(
            realized.std() * np.sqrt(252) * 100
        )
        assert crypto.current_sharpe == pytest.approx(
            expected_crypto_excess.mean()
            / expected_crypto_excess.std()
            * np.sqrt(365)
        )
        assert equity.current_sharpe == pytest.approx(
            expected_equity_excess.mean()
            / expected_equity_excess.std()
            * np.sqrt(252)
        )

        crypto_window = expected_crypto_excess.iloc[-365:]
        equity_window = expected_equity_excess.iloc[-252:]
        expected_crypto_rolling = round(
            float(crypto_window.mean() / crypto_window.std() * np.sqrt(365)), 3
        )
        expected_equity_rolling = round(
            float(equity_window.mean() / equity_window.std() * np.sqrt(252)), 3
        )
        assert crypto.rolling_sharpe_data[-1]["value"] == expected_crypto_rolling
        assert equity.rolling_sharpe_data[-1]["value"] == expected_equity_rolling
        assert crypto.rolling_window == 365
        assert equity.rolling_window == 252
        assert len(crypto.rolling_sharpe_data) == len(realized) - 365 + 1
        assert len(equity.rolling_sharpe_data) == len(realized) - 252 + 1

    def test_explicit_rolling_window_overrides_both_asset_clocks(self):
        computer = RiskMetricsComputer(
            fetcher=StubFetcher({}), storage=StubStorage(), rolling_window=30
        )
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "excess_return": 0.001 + 0.01 * np.sin(np.arange(len(dates))),
        })

        crypto = computer._compute_rolling_sharpe(df, 365)
        equity = computer._compute_rolling_sharpe(df, 252)

        assert computer._rolling_window_for(365) == 30
        assert computer._rolling_window_for(252) == 30
        assert len(crypto) == len(equity) == len(df) - 30 + 1
        assert crypto[0]["date"] == equity[0]["date"] == "2024-01-30"

    def test_unconfigured_calendar_series_is_inferred_from_weekends(self, computer):
        calendar_dates = pd.date_range("2024-01-01", periods=60, freq="D")
        weekday_dates = pd.date_range("2024-01-01", periods=60, freq="B")

        assert computer._annualization_factor("unknown", calendar_dates) == 365
        assert computer._annualization_factor("unknown", weekday_dates) == 252


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
    def test_current_regime_does_not_treat_unclassified_rows_as_neutral(self):
        glci = pd.DataFrame({"regime": [np.nan, np.nan]})
        assert RiskMetricsComputer._current_regime(glci) is None

        glci = pd.DataFrame({"regime": [1.0, np.nan]})
        assert RiskMetricsComputer._current_regime(glci) is None

        glci = pd.DataFrame({"regime": [np.nan, 1.0]})
        assert RiskMetricsComputer._current_regime(glci) == "loose"

    def test_missing_regime_column_is_rejected(self):
        storage = StubStorage({
            ("indices", "glci"): pd.DataFrame({
                "date": pd.date_range("2026-01-02", periods=3, freq="W-FRI"),
                "value": [99.0, 100.0, 101.0],
            })
        })
        computer = RiskMetricsComputer(
            fetcher=StubFetcher({}),
            storage=storage,
        )

        with pytest.raises(ValueError, match="missing the regime column"):
            computer._load_glci_regimes()

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

        storage = MetadataStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=StubFetcher(frames), storage=storage)

        result = computer.compute(save_output=True, verbose=False)

        assert len(result.assets) == len(ASSET_CONFIG)
        assert result.current_regime == "loose"
        assert ("risk", "risk_metrics") in storage.curated
        saved = storage.curated[("risk", "risk_metrics")]
        assert set(saved["asset_id"]) == set(ASSET_CONFIG)

        policy = result.metadata["asset_clock_policy"]
        assert result.metadata["annualization_policy"] == "per_asset_observation_clock"
        assert result.metadata["rolling_window_policy"] == "one_year_by_asset_clock"
        assert policy["sp500_price"] == {
            "annualization_factor": 252,
            "rolling_window": 252,
        }
        assert policy["bitcoin_price"] == {
            "annualization_factor": 365,
            "rolling_window": 365,
        }
        assert storage.saved_metadata[("risk", "risk_metrics")] == result.metadata
        assert storage.saved_metadata[("risk", "rolling_sharpe_sp500_price")] == {
            "asset_id": "sp500_price",
            "annualization_factor": 252,
            "window": 252,
            "rolling_window_policy": "one_year_by_asset_clock",
        }
        assert storage.saved_metadata[("risk", "rolling_sharpe_bitcoin_price")] == {
            "asset_id": "bitcoin_price",
            "annualization_factor": 365,
            "window": 365,
            "rolling_window_policy": "one_year_by_asset_clock",
        }

    def test_explicit_window_is_disclosed_in_result_and_save_metadata(self):
        glci, price_df, rf_df = build_regime_world()
        storage = MetadataStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(
            fetcher=StubFetcher({
                "sp500_price": price_df,
                "treasury_3m": rf_df,
            }),
            storage=storage,
            rolling_window=30,
        )

        result = computer.compute(save_output=True, verbose=False)

        assert result.metadata["rolling_window"] == 30
        assert result.metadata["rolling_window_policy"] == "explicit_override"
        assert result.metadata["asset_clock_policy"]["sp500_price"] == {
            "annualization_factor": 252,
            "rolling_window": 30,
        }
        assert storage.saved_metadata[("risk", "rolling_sharpe_sp500_price")] == {
            "asset_id": "sp500_price",
            "annualization_factor": 252,
            "window": 30,
            "rolling_window_policy": "explicit_override",
        }

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

    def test_glci_correlation_uses_weekly_returns_and_level_changes(self):
        fridays = pd.date_range("2021-01-01", periods=36, freq="W-FRI")
        changes = np.resize(np.array([-3.0, -1.0, 1.0, 3.0]), len(fridays))
        changes[0] = 0.0
        glci = pd.DataFrame({
            "date": fridays,
            "value": 100 + np.cumsum(changes),
            "regime": np.zeros(len(fridays), dtype=int),
        })

        daily_dates = pd.date_range(fridays[0], fridays[-1], freq="B")
        price = 100.0
        daily_prices = []
        friday_positions = {date: i for i, date in enumerate(fridays)}
        for date in daily_dates:
            if date.dayofweek == 0:
                week_end = date + pd.Timedelta(days=4)
                if week_end in friday_positions:
                    price *= 1 + changes[friday_positions[week_end]] / 1000
            daily_prices.append(price)
        price_df = make_series(daily_dates, daily_prices)

        fetcher = StubFetcher({"sp500_price": price_df})
        storage = StubStorage({("indices", "glci"): glci})
        computer = RiskMetricsComputer(fetcher=fetcher, storage=storage)
        glci_loaded = computer._load_glci_regimes()
        metrics = computer._compute_asset_metrics(
            "sp500_price", ASSET_CONFIG["sp500_price"],
            glci_loaded, None, None, None,
        )

        # Friday-to-Friday returns were constructed as a fixed multiple of
        # the corresponding GLCI level change, so the weekly correlation is 1.
        assert metrics.correlation_with_glci == pytest.approx(1.0, abs=1e-12)

        # The former daily/forward-filled calculation looks only at Friday
        # GLCI jumps, while this asset's weekly move occurs on Monday.
        old_daily = pd.merge_asof(
            price_df.assign(return_=price_df["value"].pct_change()),
            glci[["date", "value"]].rename(columns={"value": "glci_value"}),
            on="date",
            direction="backward",
        )
        old_correlation = old_daily["return_"].corr(
            old_daily["glci_value"].pct_change()
        )
        assert abs(metrics.correlation_with_glci - old_correlation) > 0.5

    def test_glci_correlation_requires_twenty_aligned_weeks(self, computer):
        fridays = pd.date_range("2024-01-05", periods=19, freq="W-FRI")
        prices = make_series(fridays, 100 + np.arange(len(fridays)))
        glci = pd.DataFrame({
            "date": fridays,
            "value": 100 + np.arange(len(fridays)) ** 2,
        })

        assert computer._compute_glci_correlation(prices, glci) is None

    def test_undefined_glci_correlation_is_unavailable(self, computer):
        fridays = pd.date_range("2024-01-05", periods=30, freq="W-FRI")
        prices = make_series(fridays, 100 + np.arange(len(fridays)))
        glci = pd.DataFrame({
            "date": fridays,
            "value": np.full(len(fridays), 100.0),
        })

        assert computer._compute_glci_correlation(prices, glci) is None

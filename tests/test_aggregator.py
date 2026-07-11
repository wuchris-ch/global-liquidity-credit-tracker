"""Tests for composite index aggregation (src/indicators/aggregator.py)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.aggregator import Aggregator
from src.config import get_index_config
from conftest import StubFetcher, make_series


@pytest.fixture
def net_liquidity_world(weekly_dates):
    """Synthetic Fed balance sheet components with known values.

    Units mirror production: assets/TGA in millions, RRP in billions
    (the index config multiplies RRP by 1000 to convert).
    """
    n = len(weekly_dates)
    assets = np.linspace(8_000_000, 8_500_000, n)   # millions USD
    tga = np.full(n, 700_000.0)                     # millions USD
    rrp = np.full(n, 500.0)                         # billions USD

    fetcher = StubFetcher({
        "fed_total_assets": make_series(weekly_dates, assets),
        "fed_treasury_general_account": make_series(weekly_dates, tga),
        "fed_reverse_repo": make_series(weekly_dates, rrp),
    })
    expected_latest = assets[-1] - tga[-1] - rrp[-1] * 1000
    return fetcher, expected_latest


class TestFedNetLiquidity:
    def test_formula_assets_minus_tga_minus_rrp(self, net_liquidity_world):
        fetcher, expected_latest = net_liquidity_world
        agg = Aggregator(fetcher=fetcher)

        df = agg.compute_index("fed_net_liquidity")

        assert not df.empty
        assert df["value"].iloc[-1] == pytest.approx(expected_latest)
        assert (df["index_id"] == "fed_net_liquidity").all()

    def test_output_is_weekly(self, net_liquidity_world):
        fetcher, _ = net_liquidity_world
        df = Aggregator(fetcher=fetcher).compute_index("fed_net_liquidity")
        gaps = df["date"].diff().dropna()
        assert (gaps == pd.Timedelta(days=7)).all()


class TestZscoreAverage:
    def test_credit_stress_is_weighted_zscore_average(self, daily_dates):
        n = len(daily_dates)
        hy = np.linspace(3.0, 8.0, n)
        ig = np.linspace(1.0, 2.0, n) ** 2
        fetcher = StubFetcher({
            "ice_bofa_us_high_yield_spread": make_series(daily_dates, hy),
            "ice_bofa_us_ig_spread": make_series(daily_dates, ig),
        })
        df = Aggregator(fetcher=fetcher).compute_index("usd_funding_stress")

        assert not df.empty
        hy_z = pd.Series(hy).rolling(252, min_periods=20).apply(
            lambda values: (values.iloc[-1] - values.mean()) / values.std()
        )
        ig_z = pd.Series(ig).rolling(252, min_periods=20).apply(
            lambda values: (values.iloc[-1] - values.mean()) / values.std()
        )
        expected = (hy_z + 0.5 * ig_z) / 1.5

        assert df["date"].iloc[0] == daily_dates[19]
        assert len(df) == n - 19
        assert df["value"].iloc[-1] == pytest.approx(expected.iloc[-1])

    def test_zscore_burn_in_is_not_reported_as_zero(self, daily_dates):
        n = len(daily_dates)
        fetcher = StubFetcher({
            "ice_bofa_us_high_yield_spread": make_series(
                daily_dates, np.linspace(3.0, 8.0, n)
            ),
            "ice_bofa_us_ig_spread": make_series(
                daily_dates, np.linspace(1.0, 2.0, n)
            ),
        })

        stress = Aggregator(fetcher=fetcher).compute_index("usd_funding_stress")

        assert stress["date"].min() == daily_dates[19]
        assert stress["value"].notna().all()

    def test_stress_spike_raises_index(self, daily_dates):
        n = len(daily_dates)
        calm = np.full(n, 1.0)
        spiked = calm.copy()
        spiked[-20:] = 8.0  # blow out spreads at the end

        def build(values):
            return StubFetcher({
                "ice_bofa_us_high_yield_spread": make_series(daily_dates, values),
                "ice_bofa_us_ig_spread": make_series(daily_dates, values),
            })

        stress = Aggregator(fetcher=build(spiked)).compute_index("usd_funding_stress")
        assert stress["value"].iloc[-1] > 1.0


class TestStressConfiguration:
    def test_credit_stress_retains_api_id_and_oas_weights(self):
        config = get_index_config("usd_funding_stress")
        weights = {
            component["series"]: component["weight"]
            for component in config["components"]
        }

        assert weights == {
            "ice_bofa_us_high_yield_spread": 1.0,
            "ice_bofa_us_ig_spread": 0.5,
        }
        assert config["name"] == "USD Credit Stress"

    def test_glci_stress_pillar_excludes_discontinued_ted(self):
        config = get_index_config("global_liquidity_credit_index")
        components = {
            component["series"]
            for component in config["pillars"]["stress"]["components"]
        }

        assert components == {
            "ice_bofa_us_high_yield_spread",
            "ice_bofa_us_ig_spread",
            "sofr",
            "fed_funds_rate",
            "vix",
            "nfci",
        }


class TestUnknownIndex:
    def test_raises_for_unconfigured_index(self):
        with pytest.raises(ValueError, match="not found"):
            Aggregator(fetcher=StubFetcher({})).compute_index("nonexistent_index")

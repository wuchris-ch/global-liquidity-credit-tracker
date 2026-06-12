"""Tests for composite index aggregation (src/indicators/aggregator.py)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.aggregator import Aggregator
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
    def test_funding_stress_is_weighted_zscore_average(self, daily_dates):
        n = len(daily_dates)
        rng = np.random.default_rng(0)
        fetcher = StubFetcher({
            "ted_spread": make_series(daily_dates, rng.normal(0.5, 0.1, n)),
            "ice_bofa_us_high_yield_spread": make_series(daily_dates, rng.normal(4.0, 0.5, n)),
            "ice_bofa_us_ig_spread": make_series(daily_dates, rng.normal(1.2, 0.2, n)),
        })
        df = Aggregator(fetcher=fetcher).compute_index("usd_funding_stress")

        assert not df.empty
        # A z-score average over stationary noise stays in a tight band
        assert df["value"].dropna().abs().max() < 5

    def test_stress_spike_raises_index(self, daily_dates):
        n = len(daily_dates)
        calm = np.full(n, 1.0)
        spiked = calm.copy()
        spiked[-20:] = 8.0  # blow out spreads at the end

        def build(values):
            return StubFetcher({
                "ted_spread": make_series(daily_dates, values),
                "ice_bofa_us_high_yield_spread": make_series(daily_dates, values),
                "ice_bofa_us_ig_spread": make_series(daily_dates, values),
            })

        stress = Aggregator(fetcher=build(spiked)).compute_index("usd_funding_stress")
        assert stress["value"].iloc[-1] > 1.0


class TestUnknownIndex:
    def test_raises_for_unconfigured_index(self):
        with pytest.raises(ValueError, match="not found"):
            Aggregator(fetcher=StubFetcher({})).compute_index("nonexistent_index")

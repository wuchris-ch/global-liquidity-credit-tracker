"""Tests for the liquidity-destinations computation (src/indicators/flows.py)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.flows import (
    FLOW_DESTINATIONS,
    FLOW_WINDOW,
    FlowsComputer,
    PAIR_DENOMINATOR,
    PAIR_NUMERATOR,
)
from conftest import StubFetcher, StubStorage, make_series


def weekly_dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2019-01-04", periods=n, freq="W-FRI")


def flat_growth_series(n: int, weekly_growth: float, start: float = 100.0) -> np.ndarray:
    return start * np.cumprod(np.full(n, 1 + weekly_growth))


def build_world(n: int = 220) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """One price frame per configured destination plus a synthetic GLCI."""
    dates = weekly_dates(n)
    rng = np.random.default_rng(7)
    frames = {}
    for i, dest in enumerate(FLOW_DESTINATIONS):
        base = flat_growth_series(n, 0.001 * (i + 1))
        noise = 1 + rng.normal(0, 0.002, n)
        frames[dest["series_id"]] = make_series(dates, base * noise)

    glci = pd.DataFrame({
        "date": dates,
        "value": np.linspace(95, 105, n) + rng.normal(0, 0.5, n),
    })
    return frames, glci


@pytest.fixture
def world():
    frames, glci = build_world()
    fetcher = StubFetcher(frames)
    storage = StubStorage({("indices", "glci"): glci})
    return FlowsComputer(fetcher=fetcher, storage=storage)


class TestTrailingReturn:
    def test_known_constant_growth(self):
        n = 60
        weekly = pd.Series(
            flat_growth_series(n, 0.01), index=weekly_dates(n)
        )
        ret = FlowsComputer._trailing_return(weekly, 13)
        assert ret == pytest.approx(1.01**13 - 1, rel=1e-9)

    def test_too_short_returns_none(self):
        weekly = pd.Series([100.0, 101.0], index=weekly_dates(2))
        assert FlowsComputer._trailing_return(weekly, 13) is None


class TestFlowZscore:
    def test_constant_growth_is_degenerate(self):
        # Identical 13w return every week -> no dispersion to score against
        n = 220
        weekly = pd.Series(flat_growth_series(n, 0.005), index=weekly_dates(n))
        assert FlowsComputer._flow_zscore(weekly) is None

    def test_matches_manual_computation(self):
        n = 220
        rng = np.random.default_rng(3)
        weekly = pd.Series(
            100 * np.cumprod(1 + rng.normal(0.002, 0.02, n)),
            index=weekly_dates(n),
        )
        z = FlowsComputer._flow_zscore(weekly)

        window_returns = weekly.pct_change(13).dropna().iloc[-156:]
        expected = (window_returns.iloc[-1] - window_returns.mean()) / window_returns.std()
        assert z == pytest.approx(float(expected))

    def test_recent_surge_scores_positive(self):
        n = 220
        prices = flat_growth_series(n, 0.001)
        prices[-FLOW_WINDOW:] = prices[-FLOW_WINDOW:] * np.cumprod(
            np.full(FLOW_WINDOW, 1.03)
        )
        weekly = pd.Series(prices, index=weekly_dates(n))
        z = FlowsComputer._flow_zscore(weekly)
        assert z is not None and z > 1.5

    def test_short_history_returns_none(self):
        weekly = pd.Series(
            flat_growth_series(30, 0.01), index=weekly_dates(30)
        )
        assert FlowsComputer._flow_zscore(weekly) is None


class TestComputePayload:
    def test_full_payload_shape(self, world):
        payload = world.compute(save_output=False, verbose=False)

        assert len(payload["destinations"]) == len(FLOW_DESTINATIONS)
        ids = {d["id"] for d in payload["destinations"]}
        assert "ai_semis" in ids and "bitcoin" in ids

        for dest in payload["destinations"]:
            assert dest["ret_13w"] is not None
            assert dest["flow_z"] is not None
            assert dest["glci_corr_52w"] is not None
            assert len(dest["spark"]) == 52
            assert dest["last_date"] == payload["as_of"]

    def test_pair_indexed_to_100(self, world):
        payload = world.compute(save_output=False, verbose=False)
        pair = payload["pair"]
        assert pair is not None
        assert pair["numerator"] == PAIR_NUMERATOR
        assert pair["denominator"] == PAIR_DENOMINATOR
        assert pair["ratio"][0]["value"] == pytest.approx(100.0)
        assert pair["spread_13w"] is not None

    def test_missing_series_is_skipped(self):
        frames, glci = build_world()
        del frames["semis_price"]
        del frames["gold_price"]
        computer = FlowsComputer(
            fetcher=StubFetcher(frames),
            storage=StubStorage({("indices", "glci"): glci}),
        )
        payload = computer.compute(save_output=False, verbose=False)
        ids = {d["id"] for d in payload["destinations"]}
        assert "ai_semis" not in ids and "gold" not in ids
        assert len(payload["destinations"]) == len(FLOW_DESTINATIONS) - 2
        # The headline pair needs semis; without it the payload says so
        assert payload["pair"] is None

    def test_fewer_than_two_destinations_raises(self):
        frames, glci = build_world()
        only_one = {"sp500_price": frames["sp500_price"]}
        computer = FlowsComputer(
            fetcher=StubFetcher(only_one),
            storage=StubStorage({("indices", "glci"): glci}),
        )
        with pytest.raises(ValueError):
            computer.compute(save_output=False, verbose=False)

    def test_missing_glci_omits_correlations(self):
        frames, _ = build_world()
        computer = FlowsComputer(
            fetcher=StubFetcher(frames), storage=StubStorage()
        )
        payload = computer.compute(save_output=False, verbose=False)
        assert all(d["glci_corr_52w"] is None for d in payload["destinations"])

    def test_daily_input_collapses_to_weekly(self):
        """Daily (including weekend, like crypto) input must not distort returns."""
        # 897 days from a Friday ends exactly on a Friday, so the last
        # weekly bucket is complete and the 13w window spans 91 days.
        days = pd.date_range("2021-01-01", periods=897, freq="D")
        prices = 100 * np.cumprod(np.full(len(days), 1.0005))
        frames = {
            "sp500_price": make_series(days, prices),
            "bitcoin_price": make_series(days, prices * 2),
        }
        computer = FlowsComputer(
            fetcher=StubFetcher(frames), storage=StubStorage()
        )
        payload = computer.compute(save_output=False, verbose=False)
        sp = next(d for d in payload["destinations"] if d["id"] == "sp500")
        # 13 weeks of 7 daily steps at 5bp each
        assert sp["ret_13w"] == pytest.approx(1.0005 ** (13 * 7) - 1, rel=1e-3)


class TestCompletedWeeklyClock:
    def test_payload_through_thursday_reports_previous_friday(self):
        days = pd.date_range("2024-01-01", "2024-06-20", freq="D")
        frame = make_series(days, np.arange(len(days), dtype=float) + 100)
        computer = FlowsComputer(
            fetcher=StubFetcher({"sp500_price": frame, "bitcoin_price": frame}),
            storage=StubStorage(),
        )

        payload = computer.compute(save_output=False, verbose=False)

        assert payload["as_of"] == "2024-06-14"
        assert all(d["last_date"] == "2024-06-14" for d in payload["destinations"])
        assert all(d["spark"][-1]["date"] == "2024-06-14" for d in payload["destinations"])

    def test_glci_data_through_thursday_drops_future_friday_bucket(self):
        fridays = pd.date_range("2024-01-05", "2024-06-14", freq="W-FRI")
        dates = fridays.append(pd.DatetimeIndex([pd.Timestamp("2024-06-20")]))
        glci = pd.DataFrame({"date": dates, "value": np.arange(len(dates))})
        computer = FlowsComputer(
            fetcher=StubFetcher({}),
            storage=StubStorage({("indices", "glci"): glci}),
        )

        weekly = computer._load_glci_weekly()

        assert weekly is not None
        assert weekly.index[-1] == pd.Timestamp("2024-06-14")
        assert pd.Timestamp("2024-06-21") not in weekly.index

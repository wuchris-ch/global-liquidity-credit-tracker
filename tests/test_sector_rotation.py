"""Focused offline tests for sector-flow and options activity analytics."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from src.data_sources.occ import OCCOptionsClient, OCC_VOLUME_QUERY_URL
from src.data_sources.state_street import (
    STATE_STREET_NAV_HISTORY_URL,
    StateStreetETFClient,
)
from src.indicators.sector_rotation import (
    BENCHMARK_TICKER,
    FLOW_HISTORY_DAYS,
    FLOW_Z_CLIP,
    SECTOR_ETFS,
    SectorRotationComputer,
    compute_net_issuance,
)


class StubResponse:
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content
        self.raise_for_status_calls = 0

    def raise_for_status(self) -> None:
        self.raise_for_status_calls += 1


class StubSession:
    def __init__(self, response: StubResponse) -> None:
        self.response = response
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs) -> StubResponse:
        self.calls.append((url, kwargs))
        return self.response


def _state_street_workbook(
    ticker: str,
    rows: int = 260,
    zero_share_inception_marker: bool = False,
) -> bytes:
    dates = pd.bdate_range("2023-01-02", periods=rows)
    nav = 100 * np.exp(0.0002 * np.arange(rows))
    shares = 5_000_000 + np.arange(rows) * 100
    table = pd.DataFrame(
        {
            "Date": dates,
            "NAV": nav,
            "Shares Outstanding": shares,
            "Total Net Assets": nav * shares,
        }
    )
    if zero_share_inception_marker:
        marker = pd.DataFrame(
            {
                "Date": [dates[0] - pd.offsets.BDay()],
                "NAV": [100.0],
                "Shares Outstanding": [0.0],
                "Total Net Assets": [0.0],
            }
        )
        table = pd.concat([marker, table], ignore_index=True)
    preamble = pd.DataFrame(
        [
            [None, None, None, None],
            [None, ticker, None, None],
            [None, None, None, None],
            list(table.columns),
        ]
    )
    raw = pd.concat(
        [preamble, pd.DataFrame(table.to_numpy())],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        raw.to_excel(writer, index=False, header=False)
    return buffer.getvalue()


def _issuance_history(
    dates: pd.DatetimeIndex,
    daily_share_changes: np.ndarray | float,
    *,
    split_date: date | None = None,
    split_factor: float = 2.0,
    split_creation_shares: float = 0.0,
) -> pd.DataFrame:
    changes = np.broadcast_to(daily_share_changes, len(dates)).astype(float).copy()
    nav = np.empty(len(dates), dtype=float)
    shares = np.empty(len(dates), dtype=float)
    nav[0] = 100.0
    shares[0] = 5_000_000.0
    for index in range(1, len(dates)):
        if split_date is not None and dates[index].date() == split_date:
            nav[index] = nav[index - 1] * 1.0002 / split_factor
            shares[index] = shares[index - 1] * split_factor + split_creation_shares
        else:
            nav[index] = nav[index - 1] * 1.0002
            shares[index] = shares[index - 1] + changes[index]
    return pd.DataFrame(
        {
            "date": dates,
            "nav": nav,
            "shares_outstanding": shares,
            "total_net_assets": nav * shares,
        }
    )


class TestStateStreetETFClient:
    def test_get_nav_history_parses_mocked_workbook_without_network(self):
        response = StubResponse(content=_state_street_workbook("XLK"))
        session = StubSession(response)
        client = StateStreetETFClient(session=session, timeout=(1.0, 2.0))

        result = client.get_nav_history("XLK")

        assert len(result) == 260
        assert list(result.columns) == [
            "date",
            "nav",
            "shares_outstanding",
            "total_net_assets",
        ]
        assert result["date"].is_monotonic_increasing
        assert response.raise_for_status_calls == 1
        assert session.calls == [
            (
                STATE_STREET_NAV_HISTORY_URL.format(ticker="xlk"),
                {"timeout": (1.0, 2.0)},
            )
        ]

    def test_zero_share_inception_marker_is_not_an_active_observation(self):
        response = StubResponse(
            content=_state_street_workbook(
                "XLC",
                zero_share_inception_marker=True,
            )
        )
        client = StateStreetETFClient(session=StubSession(response))

        result = client.get_nav_history("XLC")

        assert len(result) == 260
        assert (result["shares_outstanding"] > 0).all()


OCC_REPORT = """quantity,underlying,symbol,actype,porc,exchange,actdate
10,XLK,XLK,C,C,CBOE,07/10/2026,
6,XLK,XLK,M,C,CBOE,07/10/2026,
4,XLK,XLK,F,C,CBOE,07/10/2026,
12,XLK,XLK,C,P,CBOE,07/10/2026,
8,XLK,XLK,M,P,CBOE,07/10/2026,
8,XLK,2XLK,C,C,CBOE,07/10/2026,
8,XLK,2XLK,M,C,CBOE,07/10/2026,
"""


class TestOCCOptionsClient:
    def test_trailing_comma_parsing_and_standard_root_aggregation(self):
        response = StubResponse(text=OCC_REPORT)
        session = StubSession(response)
        client = OCCOptionsClient(session=session, timeout=(1.0, 2.0))

        frame = client.get_report("xlk", date(2026, 7, 10), "D")
        aggregate = client.aggregate_report(frame, "XLK")

        assert len(frame) == 7
        assert aggregate["call_volume"] == 10
        assert aggregate["put_volume"] == 10
        assert aggregate["total_volume"] == 20
        assert aggregate["put_call_ratio"] == 1.0
        assert aggregate["sessions"] == 1
        assert aggregate["excluded_adjusted_roots"] == ["2XLK"]
        assert response.raise_for_status_calls == 1
        assert session.calls[0][0] == OCC_VOLUME_QUERY_URL
        assert session.calls[0][1] == {
            "params": {
                "reportDate": "20260710",
                "format": "csv",
                "volumeQueryType": "O",
                "symbolType": "U",
                "symbol": "XLK",
                "reportType": "D",
                "accountType": "ALL",
                "productKind": "OSTK",
                "porc": "BOTH",
            },
            "timeout": (1.0, 2.0),
        }

    def test_odd_account_side_total_fails_closed(self):
        frame = OCCOptionsClient._parse_csv(
            "quantity,underlying,symbol,actype,porc,exchange,actdate\n"
            "3,XLK,XLK,C,C,CBOE,07/10/2026,\n"
        )

        with pytest.raises(ValueError, match="account-side quantity is not an even"):
            OCCOptionsClient.aggregate_report(frame, "XLK")

    def test_malformed_or_duplicate_aggregate_rows_fail_closed(self):
        malformed = (
            "quantity,underlying,symbol,actype,porc,exchange,actdate\n"
            "not-a-number,XLK,XLK,C,C,CBOE,07/10/2026,\n"
        )
        with pytest.raises(ValueError, match="invalid quantity or date"):
            OCCOptionsClient._parse_csv(malformed)

        duplicate = (
            "quantity,underlying,symbol,actype,porc,exchange,actdate\n"
            "2,XLK,XLK,C,C,CBOE,07/10/2026,\n"
            "4,XLK,XLK,C,C,CBOE,07/10/2026,\n"
        )
        with pytest.raises(ValueError, match="duplicate aggregate rows"):
            OCCOptionsClient._parse_csv(duplicate)


class TestNetIssuance:
    def test_known_split_preserves_same_day_creation(self):
        dates = pd.bdate_range("2024-10-01", "2025-12-31")
        split_date = date(2025, 12, 5)
        created_shares = 50_000.0
        frame = _issuance_history(
            dates,
            1_000.0,
            split_date=split_date,
            split_creation_shares=created_shares,
        )

        result, metrics = compute_net_issuance(frame, "XLK")
        split_row = result.loc[result["date"].dt.date == split_date].iloc[0]

        assert split_row["flow_usd"] == pytest.approx(created_shares * split_row["nav"])
        assert metrics["split_adjustments"] == 1

    def test_unknown_split_like_jump_fails_closed(self):
        dates = pd.bdate_range("2023-01-02", periods=300)
        unknown_date = dates[150].date()
        frame = _issuance_history(
            dates,
            0.0,
            split_date=unknown_date,
            split_creation_shares=10_000.0,
        )

        with pytest.raises(
            ValueError,
            match=rf"Unrecognized split-like NAV/share jump for XLF on {unknown_date}",
        ):
            compute_net_issuance(frame, "XLF")

    def test_robust_z_history_excludes_current_observation(self):
        dates = pd.bdate_range("2023-01-02", periods=320)
        rng = np.random.default_rng(123)
        changes = np.rint(rng.normal(0, 1_000, len(dates)))
        changes[0] = 0
        changes[-1] = 0
        frame = _issuance_history(dates, changes)

        result, metrics = compute_net_issuance(frame, "XLF")
        current = float(result["flow_20d_pct_aum"].iloc[-1])
        prior = result["flow_20d_pct_aum"].shift(1).dropna().iloc[-FLOW_HISTORY_DAYS:]
        median = float(prior.median())
        mad = float((prior - median).abs().median())
        expected = float(
            np.clip((current - median) / (1.4826 * mad), -FLOW_Z_CLIP, FLOW_Z_CLIP)
        )

        inclusive = result["flow_20d_pct_aum"].dropna().iloc[-FLOW_HISTORY_DAYS:]
        inclusive_median = float(inclusive.median())
        inclusive_mad = float((inclusive - inclusive_median).abs().median())
        inclusive_z = float(
            np.clip(
                (current - inclusive_median) / (1.4826 * inclusive_mad),
                -FLOW_Z_CLIP,
                FLOW_Z_CLIP,
            )
        )

        assert metrics["history_observations"] == FLOW_HISTORY_DAYS
        assert metrics["flow_20d_z"] == pytest.approx(expected, abs=0.0005)
        assert round(expected, 3) != round(inclusive_z, 3)


PRICE_DATES = pd.bdate_range("2023-01-02", periods=320)
ALL_TICKERS = [
    BENCHMARK_TICKER,
    *(sector["ticker"] for sector in SECTOR_ETFS),
]


class StubMarketClient:
    def __init__(self) -> None:
        step = np.arange(len(PRICE_DATES), dtype=float)
        self.frames: dict[str, pd.DataFrame] = {}
        for index, ticker in enumerate(ALL_TICKERS):
            growth = 0.0003 if ticker == BENCHMARK_TICKER else 0.0001 * index
            values = 100 * np.exp(growth * step + 0.003 * np.sin(step / 11 + index / 3))
            self.frames[ticker] = pd.DataFrame(
                {"date": PRICE_DATES, "value": values, "source": "test"}
            )

    def get_adjusted_histories(self, tickers, start_date, end_date):
        assert set(tickers) == set(ALL_TICKERS)
        assert start_date < end_date
        return {ticker: self.frames[ticker].copy() for ticker in tickers}


class StubFundClient:
    def __init__(self, direction: float) -> None:
        self.histories: dict[str, pd.DataFrame] = {}
        step = np.arange(len(PRICE_DATES), dtype=float)
        for index, ticker in enumerate(ALL_TICKERS):
            changes = direction * (100 + index * 5 + 20 * np.sin(step / 9))
            self.histories[ticker] = _issuance_history(PRICE_DATES, changes)

    def get_nav_history(self, ticker: str) -> pd.DataFrame:
        return self.histories[ticker].copy()


class StubOptionsClient:
    def __init__(self, activity_multiplier: float) -> None:
        self.activity_multiplier = activity_multiplier

    def latest_completed_week(self, as_of):
        return date(2024, 2, 16)

    def get_report(self, ticker, report_date, report_type):
        return {"ticker": ticker, "report_date": report_date, "type": report_type}

    def aggregate_report(self, report, ticker):
        index = ALL_TICKERS.index(ticker)
        if report["type"] == "W":
            sessions = 5
            daily_volume = int((1_000 + index * 10) * self.activity_multiplier)
            start_date = "2024-02-12"
            end_date = "2024-02-16"
        else:
            sessions = 20
            daily_volume = 1_000 + index * 10
            start_date = "2024-01-02"
            end_date = "2024-01-31"
        total = daily_volume * sessions
        call_volume = total * 3 // 5
        put_volume = total - call_volume
        return {
            "call_volume": call_volume,
            "put_volume": put_volume,
            "total_volume": total,
            "put_call_ratio": round(put_volume / call_volume, 4),
            "start_date": start_date,
            "end_date": end_date,
            "sessions": sessions,
            "excluded_adjusted_roots": [],
        }


def _rotation_payload(flow_direction: float, options_multiplier: float) -> dict:
    computer = SectorRotationComputer(
        market_client=StubMarketClient(),
        fund_client=StubFundClient(flow_direction),
        options_client=StubOptionsClient(options_multiplier),
    )
    return computer.compute(include_options=True, verbose=False)


class TestSectorRotationComputer:
    def test_complete_eleven_sector_ranking(self):
        payload = _rotation_payload(flow_direction=1.0, options_multiplier=2.0)
        rows = payload["sectors"]

        assert len(rows) == len(SECTOR_ETFS) == 11
        assert {row["ticker"] for row in rows} == {
            sector["ticker"] for sector in SECTOR_ETFS
        }
        assert sorted(row["rank"] for row in rows) == list(range(1, 12))
        assert payload["coverage"] == {
            "expected_sectors": 11,
            "price": 11,
            "fund_flows": 11,
            "options": 11,
            "complete_price_universe": True,
            "complete_fund_flow_universe": True,
            "options_status": "complete",
            "options_errors": {},
        }
        assert payload["opportunities"]["leaders"] == [row["id"] for row in rows[:3]]
        assert payload["opportunities"]["laggards"] == [row["id"] for row in rows[-3:]]

    def test_score_and_rank_are_independent_of_flow_and_options(self):
        positive = _rotation_payload(flow_direction=1.0, options_multiplier=3.0)
        negative = _rotation_payload(flow_direction=-1.0, options_multiplier=0.25)

        score_fields = {
            row["ticker"]: (
                row["rank"],
                row["price_score"],
                row["relative_strength"],
                row["absolute_trend"],
            )
            for row in positive["sectors"]
        }
        changed_score_fields = {
            row["ticker"]: (
                row["rank"],
                row["price_score"],
                row["relative_strength"],
                row["absolute_trend"],
            )
            for row in negative["sectors"]
        }

        assert changed_score_fields == score_fields
        positive_xlk = next(
            row for row in positive["sectors"] if row["ticker"] == "XLK"
        )
        negative_xlk = next(
            row for row in negative["sectors"] if row["ticker"] == "XLK"
        )
        assert positive_xlk["fund_flow"]["flow_20d_pct_aum"] > 0
        assert negative_xlk["fund_flow"]["flow_20d_pct_aum"] < 0
        assert positive_xlk["options_activity"]["activity_ratio"] == 3.0
        assert negative_xlk["options_activity"]["activity_ratio"] == 0.25
        assert positive["methodology"]["excluded_from_score"] == [
            "fund_flow",
            "options_activity",
        ]

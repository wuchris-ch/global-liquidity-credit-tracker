"""OCC cleared options-volume client.

The OCC Volume Query reports quantities by account side, call/put, exchange,
and product root. With ``accountType=ALL``, market-wide contract volume is half
the sum of all account-side quantities because every cleared trade has two
sides. This client publishes activity only. The feed does not identify who
initiated a trade or whether either side opened or closed a position.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import requests

from .http import retrying_session


OCC_VOLUME_QUERY_URL = "https://marketdata.theocc.com/volume-query"
OCC_BATCH_DOC_URL = (
    "https://www.theocc.com/market-data/market-data-reports/"
    "other-market-data-info/batch-processing/volume-query-batch-processing"
)

_REQUIRED_COLUMNS = {
    "quantity",
    "underlying",
    "symbol",
    "actype",
    "porc",
    "exchange",
    "actdate",
}


class OCCOptionsClient:
    """Fetch and aggregate no-key OCC options-volume reports."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 30.0),
    ) -> None:
        self.session = session or retrying_session()
        self.timeout = timeout
        self.session.headers.setdefault(
            "User-Agent",
            "global-liquidity-credit-tracker/1.0 (research dashboard)",
        )

    @staticmethod
    def _parse_csv(text: str) -> pd.DataFrame:
        """Parse OCC's seven-column header plus optional blank eighth field."""
        if not text.strip():
            return pd.DataFrame(columns=sorted(_REQUIRED_COLUMNS))

        rows = list(csv.reader(StringIO(text)))
        if not rows:
            return pd.DataFrame(columns=sorted(_REQUIRED_COLUMNS))
        header = [value.strip() for value in rows[0]]
        missing = sorted(_REQUIRED_COLUMNS - set(header))
        if missing:
            raise ValueError(
                "OCC volume response is missing columns: " + ", ".join(missing)
            )

        records: list[dict[str, str]] = []
        for raw_row in rows[1:]:
            row = list(raw_row)
            if len(row) == len(header) + 1 and not row[-1].strip():
                row = row[:-1]
            if len(row) != len(header):
                raise ValueError(
                    f"OCC volume row has {len(row)} fields; expected {len(header)}"
                )
            records.append(dict(zip(header, row)))

        frame = pd.DataFrame(records)
        if frame.empty:
            return pd.DataFrame(columns=header)
        frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
        frame["actdate"] = pd.to_datetime(frame["actdate"], errors="coerce")
        if frame[["quantity", "actdate"]].isna().any().any():
            raise ValueError("OCC volume response contains an invalid quantity or date")
        if (frame["quantity"] < 0).any():
            raise ValueError("OCC volume response contains a negative quantity")
        if (frame["quantity"] % 1 != 0).any():
            raise ValueError("OCC volume response contains a non-integer quantity")
        frame["quantity"] = frame["quantity"].astype("int64")
        for column in ("underlying", "symbol", "actype", "porc", "exchange"):
            frame[column] = frame[column].astype(str).str.strip().str.upper()
        if frame[["underlying", "symbol", "exchange"]].eq("").any().any():
            raise ValueError("OCC volume response contains a blank market identifier")
        if not set(frame["actype"]).issubset({"C", "F", "M"}):
            raise ValueError("OCC volume response contains an unknown account type")
        if not set(frame["porc"]).issubset({"C", "P"}):
            raise ValueError("OCC volume response contains an unknown call/put code")
        keys = ["underlying", "symbol", "actype", "porc", "exchange", "actdate"]
        if frame.duplicated(keys).any():
            raise ValueError("OCC volume response contains duplicate aggregate rows")
        return frame.reset_index(drop=True)

    def get_report(
        self,
        ticker: str,
        report_date: date,
        report_type: str,
    ) -> pd.DataFrame:
        """Fetch a daily, weekly, or monthly OCC report for one underlying."""
        report_type = report_type.upper()
        if report_type not in {"D", "W", "M"}:
            raise ValueError("OCC report_type must be D, W, or M")
        symbol = ticker.strip().upper()
        response = self.session.get(
            OCC_VOLUME_QUERY_URL,
            params={
                "reportDate": report_date.strftime("%Y%m%d"),
                "format": "csv",
                "volumeQueryType": "O",
                "symbolType": "U",
                "symbol": symbol,
                "reportType": report_type,
                "accountType": "ALL",
                "productKind": "OSTK",
                "porc": "BOTH",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        frame = self._parse_csv(response.text)
        if not frame.empty and not set(frame["underlying"]).issubset({symbol}):
            received = ", ".join(sorted(set(frame["underlying"])))
            raise ValueError(
                f"OCC response underlying mismatch for {symbol}: {received}"
            )
        return frame

    @staticmethod
    def aggregate_report(frame: pd.DataFrame, ticker: str) -> dict:
        """Single-count standard-root calls and puts from account-side rows."""
        symbol = ticker.strip().upper()
        if frame.empty:
            return {
                "call_volume": 0,
                "put_volume": 0,
                "total_volume": 0,
                "put_call_ratio": None,
                "start_date": None,
                "end_date": None,
                "sessions": 0,
                "excluded_adjusted_roots": [],
            }

        roots = sorted(set(frame["symbol"]))
        adjusted_roots = [root for root in roots if root != symbol]
        standard = frame[frame["symbol"] == symbol]

        volumes: dict[str, int] = {}
        for code, label in (("C", "call_volume"), ("P", "put_volume")):
            account_side_quantity = float(
                standard.loc[standard["porc"] == code, "quantity"].sum()
            )
            if not account_side_quantity.is_integer() or int(account_side_quantity) % 2:
                raise ValueError(
                    f"OCC {symbol} {code} account-side quantity is not an even integer"
                )
            volumes[label] = int(account_side_quantity) // 2

        total = volumes["call_volume"] + volumes["put_volume"]
        call_volume = volumes["call_volume"]
        dates = standard["actdate"].dropna().sort_values()
        return {
            **volumes,
            "total_volume": total,
            "put_call_ratio": (
                round(volumes["put_volume"] / call_volume, 4)
                if call_volume > 0
                else None
            ),
            "start_date": dates.iloc[0].strftime("%Y-%m-%d")
            if not dates.empty
            else None,
            "end_date": dates.iloc[-1].strftime("%Y-%m-%d")
            if not dates.empty
            else None,
            "sessions": int(dates.dt.normalize().nunique()) if not dates.empty else 0,
            "excluded_adjusted_roots": adjusted_roots,
        }

    def latest_completed_week(
        self,
        as_of: date | None = None,
        reference_symbol: str = "SPY",
        max_weeks_back: int = 4,
    ) -> date:
        """Find the latest Friday-labelled weekly report that OCC serves."""
        cursor = as_of or date.today()
        cursor -= timedelta(days=(cursor.weekday() - 4) % 7)
        for _ in range(max_weeks_back):
            report = self.get_report(reference_symbol, cursor, "W")
            if not report.empty:
                return cursor
            cursor -= timedelta(days=7)
        raise RuntimeError("OCC did not return a completed weekly report")

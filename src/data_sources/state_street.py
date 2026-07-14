"""State Street ETF fund-history client.

State Street publishes a daily NAV-history workbook for each Select Sector
SPDR. The files contain the inputs needed to estimate primary-market net
issuance without inferring flows from secondary-market price or volume:

    estimated flow_t = NAV_t * (shares_t - shares_{t-1})

The estimate is a dollar value for net creations/redemptions. Creations can
be in-kind, so it must not be described as literal cash transferred into the
fund.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import requests

from .http import retrying_session


STATE_STREET_NAV_HISTORY_URL = (
    "https://www.ssga.com/us/en/intermediary/library-content/products/"
    "fund-data/etfs/us/navhist-us-en-{ticker}.xlsx"
)


class StateStreetETFClient:
    """Download and validate official State Street ETF NAV histories."""

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
    def _parse_workbook(content: bytes, expected_ticker: str) -> pd.DataFrame:
        """Parse one NAV-history workbook into a stable typed schema."""
        if not content.startswith(b"PK"):
            raise ValueError("State Street response is not an XLSX workbook")

        raw = pd.read_excel(BytesIO(content), header=None, engine="openpyxl")
        if raw.shape[0] < 5 or raw.shape[1] < 4:
            raise ValueError("State Street workbook is missing its data table")

        file_ticker = str(raw.iloc[1, 1]).strip().upper()
        expected = expected_ticker.strip().upper()
        if file_ticker != expected:
            raise ValueError(
                f"State Street workbook ticker mismatch: expected {expected}, "
                f"received {file_ticker or '<blank>'}"
            )

        header = [str(value).strip() for value in raw.iloc[3].tolist()]
        table = raw.iloc[4:].copy()
        table.columns = header

        required = [
            "Date",
            "NAV",
            "Shares Outstanding",
            "Total Net Assets",
        ]
        missing = sorted(set(required) - set(table.columns))
        if missing:
            raise ValueError(
                "State Street workbook is missing columns: " + ", ".join(missing)
            )

        result = table[required].rename(
            columns={
                "Date": "date",
                "NAV": "nav",
                "Shares Outstanding": "shares_outstanding",
                "Total Net Assets": "total_net_assets",
            }
        )
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        for column in ("nav", "shares_outstanding", "total_net_assets"):
            result[column] = pd.to_numeric(result[column], errors="coerce")

        result = (
            result.dropna(
                subset=["date", "nav", "shares_outstanding", "total_net_assets"]
            )
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )
        positive_fund = (
            result[["nav", "shares_outstanding", "total_net_assets"]] > 0
        ).all(axis=1)
        if not positive_fund.any():
            raise ValueError(
                f"State Street workbook for {expected} has no active fund history"
            )
        # Some sponsor files include a zero-share inception marker before the
        # first active day. It is metadata, not an investable observation.
        result = result.loc[positive_fund.idxmax() :].reset_index(drop=True)
        if len(result) < 260:
            raise ValueError(
                f"State Street workbook for {expected} has only {len(result)} valid rows"
            )
        if (result[["nav", "shares_outstanding", "total_net_assets"]] <= 0).any().any():
            raise ValueError(
                f"State Street workbook for {expected} contains non-positive fund values"
            )
        return result

    def get_nav_history(self, ticker: str) -> pd.DataFrame:
        """Return official daily NAV, shares outstanding, and net assets."""
        normalized = ticker.strip().lower()
        response = self.session.get(
            STATE_STREET_NAV_HISTORY_URL.format(ticker=normalized),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._parse_workbook(response.content, ticker)

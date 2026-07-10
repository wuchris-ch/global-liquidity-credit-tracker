"""Liquidity-sensitive price leadership across market destinations.

Ranks liquidity-sensitive asset classes ("destinations") by how unusual
their trailing bid is relative to their own history, so the frontend can
answer: is the marginal liquidity dollar going into AI, crypto, gold,
small caps, or duration?

Per destination, on a weekly (Friday) grid:
  - trailing total returns over 4, 13 and 26 weeks
  - a flow score: the current 13-week return expressed as a z-score
    against that asset's own trailing three years of (overlapping)
    13-week returns. Comparable across assets with very different
    volatility: +1 means an unusually strong bid *for that asset*.
  - the 52-week correlation of weekly returns with weekly GLCI changes
    (how liquidity-sensitive the destination has recently been)

Plus one headline pair: bitcoin priced in semiconductors, the cleanest
"crypto vs the AI trade" ratio available from the configured series.

Output is a JSON document saved under curated/flows/flows.json, mirrored
to /api/flows by the static export.
"""
import json
from datetime import datetime

import pandas as pd

from ..config import CURATED_DATA_PATH
from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage

# Destinations, in display order. Group is editorial, not computational.
FLOW_DESTINATIONS = [
    {"id": "ai_semis", "series_id": "semis_price", "name": "Semiconductors (SMH)", "group": "AI trade"},
    {"id": "megacap_tech", "series_id": "nasdaq100", "name": "Nasdaq 100", "group": "AI trade"},
    {"id": "bitcoin", "series_id": "bitcoin_price", "name": "Bitcoin", "group": "Crypto"},
    {"id": "ethereum", "series_id": "ethereum_price", "name": "Ethereum", "group": "Crypto"},
    {"id": "zcash", "series_id": "zcash_price", "name": "Zcash", "group": "Crypto"},
    {"id": "sp500", "series_id": "sp500_price", "name": "S&P 500", "group": "Broad equities"},
    {"id": "small_caps", "series_id": "russell2000_price", "name": "Small caps (IWM)", "group": "Broad equities"},
    {"id": "gold", "series_id": "gold_price", "name": "Gold (GLD)", "group": "Hedges"},
    {"id": "long_bonds", "series_id": "long_bond_price", "name": "Long Treasuries (TLT)", "group": "Duration"},
]

# The headline pair: crypto priced in the AI trade.
PAIR_NUMERATOR = "bitcoin_price"
PAIR_DENOMINATOR = "semis_price"

RETURN_WINDOWS = (4, 13, 26)
FLOW_WINDOW = 13          # weeks; the "trailing quarter" bid
FLOW_HISTORY = 156        # weeks of own history the z-score is measured against
FLOW_MIN_HISTORY = 52     # minimum observations before a z-score is emitted
GLCI_CORR_WINDOW = 52     # weeks
SPARK_WEEKS = 52
PAIR_WEEKS = 156


def _completed_weekly_closes(series: pd.Series) -> pd.Series:
    """Return Friday-stamped closes without a partial current-week bucket."""
    max_observation_date = series.index.max().normalize()
    weekly = series.resample("W-FRI").last().dropna()
    last_completed_friday = pd.offsets.Week(weekday=4).rollback(max_observation_date)
    return weekly.loc[weekly.index <= last_completed_friday]


class FlowsComputer:
    """Computes the liquidity-destinations payload."""

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        storage: DataStorage | None = None,
    ) -> None:
        self.fetcher = fetcher or DataFetcher()
        self.storage = storage or DataStorage()

    # -- data loading -------------------------------------------------------

    def _load_weekly_prices(self, series_id: str) -> pd.Series | None:
        """Fetch a price series and collapse it to Friday-stamped weekly closes."""
        try:
            df = self.fetcher.fetch_series(series_id)
        except Exception as e:
            print(f"  Warning: could not fetch {series_id}: {e}")
            return None
        if df is None or df.empty:
            return None

        dates = pd.to_datetime(df["date"])
        if getattr(dates.dt, "tz", None) is not None:
            dates = dates.dt.tz_localize(None)
        prices = pd.Series(
            df["value"].astype(float).values,
            index=dates.astype("datetime64[ns]"),
        ).sort_index()
        weekly = _completed_weekly_closes(prices)
        return weekly if len(weekly) >= FLOW_WINDOW + 1 else None

    def _load_glci_weekly(self) -> pd.Series | None:
        glci = self.storage.load_curated("indices", "glci")
        if glci is None or glci.empty:
            return None
        dates = pd.to_datetime(glci["date"]).astype("datetime64[ns]")
        series = pd.Series(glci["value"].astype(float).values, index=dates).sort_index()
        return _completed_weekly_closes(series)

    # -- metrics ------------------------------------------------------------

    @staticmethod
    def _trailing_return(weekly: pd.Series, weeks: int) -> float | None:
        if len(weekly) <= weeks:
            return None
        now = weekly.iloc[-1]
        then = weekly.iloc[-1 - weeks]
        if then == 0 or pd.isna(now) or pd.isna(then):
            return None
        return float(now / then - 1)

    @staticmethod
    def _flow_zscore(weekly: pd.Series) -> float | None:
        """Current 13w return vs the asset's own trailing 13w-return history."""
        window_returns = weekly.pct_change(FLOW_WINDOW).dropna()
        if len(window_returns) < FLOW_MIN_HISTORY:
            return None
        history = window_returns.iloc[-FLOW_HISTORY:]
        current = history.iloc[-1]
        std = history.std()
        if pd.isna(std) or std < 1e-12:
            return None
        return float((current - history.mean()) / std)

    @staticmethod
    def _glci_correlation(weekly: pd.Series, glci_weekly: pd.Series | None) -> float | None:
        if glci_weekly is None:
            return None
        returns = weekly.pct_change().dropna()
        glci_changes = glci_weekly.diff().dropna()
        aligned = pd.concat([returns, glci_changes], axis=1, join="inner").dropna()
        aligned = aligned.iloc[-GLCI_CORR_WINDOW:]
        if len(aligned) < 26:
            return None
        corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        return None if pd.isna(corr) else float(corr)

    @staticmethod
    def _spark(weekly: pd.Series) -> list[dict]:
        tail = weekly.iloc[-SPARK_WEEKS:]
        return [
            {"date": ts.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
            for ts, v in tail.items()
            if not pd.isna(v)
        ]

    def _build_pair(
        self, prices: dict[str, pd.Series]
    ) -> dict | None:
        num = prices.get(PAIR_NUMERATOR)
        den = prices.get(PAIR_DENOMINATOR)
        if num is None or den is None:
            return None
        ratio = (num / den).dropna().iloc[-PAIR_WEEKS:]
        if len(ratio) < FLOW_MIN_HISTORY:
            return None
        indexed = ratio / ratio.iloc[0] * 100

        spread = None
        ret_num = self._trailing_return(num, FLOW_WINDOW)
        ret_den = self._trailing_return(den, FLOW_WINDOW)
        if ret_num is not None and ret_den is not None:
            spread = round(ret_num - ret_den, 4)

        return {
            "id": "crypto_vs_ai",
            "name": "Bitcoin priced in semiconductors",
            "numerator": PAIR_NUMERATOR,
            "denominator": PAIR_DENOMINATOR,
            "spread_13w": spread,
            "ratio": [
                {"date": ts.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
                for ts, v in indexed.items()
            ],
        }

    # -- top level ----------------------------------------------------------

    def compute(self, save_output: bool = False, verbose: bool = True) -> dict:
        if verbose:
            print("Computing liquidity flows...")

        glci_weekly = self._load_glci_weekly()
        if verbose and glci_weekly is None:
            print("  Warning: GLCI not available; correlations will be omitted")

        prices: dict[str, pd.Series] = {}
        destinations = []
        for dest in FLOW_DESTINATIONS:
            weekly = self._load_weekly_prices(dest["series_id"])
            if weekly is None:
                if verbose:
                    print(f"  Skipped {dest['id']} (no usable data)")
                continue
            prices[dest["series_id"]] = weekly

            entry = {
                "id": dest["id"],
                "series_id": dest["series_id"],
                "name": dest["name"],
                "group": dest["group"],
                "last_date": weekly.index[-1].strftime("%Y-%m-%d"),
                "flow_z": self._flow_zscore(weekly),
                "glci_corr_52w": self._glci_correlation(weekly, glci_weekly),
                "spark": self._spark(weekly),
            }
            for weeks in RETURN_WINDOWS:
                ret = self._trailing_return(weekly, weeks)
                entry[f"ret_{weeks}w"] = None if ret is None else round(ret, 4)
            if entry["flow_z"] is not None:
                entry["flow_z"] = round(entry["flow_z"], 2)
            if entry["glci_corr_52w"] is not None:
                entry["glci_corr_52w"] = round(entry["glci_corr_52w"], 2)
            destinations.append(entry)
            if verbose:
                z = entry["flow_z"]
                print(f"  {dest['id']}: 13w={entry['ret_13w']}, z={z}")

        if len(destinations) < 2:
            raise ValueError(
                f"Only {len(destinations)} flow destinations computed; need at least 2"
            )

        as_of = max(d["last_date"] for d in destinations)
        payload = {
            "computed_at": datetime.utcnow().isoformat(),
            "as_of": as_of,
            "flow_window_weeks": FLOW_WINDOW,
            "flow_history_weeks": FLOW_HISTORY,
            "glci_corr_window_weeks": GLCI_CORR_WINDOW,
            "destinations": destinations,
            "pair": self._build_pair(prices),
        }

        if save_output:
            out_dir = CURATED_DATA_PATH / "flows"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "flows.json"
            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)
            if verbose:
                print(f"  Saved {out_path}")

        return payload


def compute_flows(save: bool = False, verbose: bool = True) -> dict:
    """Convenience entry point used by the scheduled pipeline."""
    return FlowsComputer().compute(save_output=save, verbose=verbose)

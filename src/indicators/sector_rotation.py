"""Select Sector SPDR net issuance and descriptive rotation analytics.

The rotation rank is deliberately price-only: medium-term relative strength
and risk-adjusted absolute trend. Official State Street share-count changes
and OCC cleared options volume are published beside it as separate evidence.
Neither auxiliary layer can silently change the rank until a point-in-time,
out-of-sample test demonstrates incremental value.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..data_sources import OCCOptionsClient, StateStreetETFClient, YFinanceClient
from ..data_sources.occ import OCC_BATCH_DOC_URL, OCC_VOLUME_QUERY_URL
from ..data_sources.state_street import STATE_STREET_NAV_HISTORY_URL


SECTOR_ETFS = (
    {"id": "materials", "ticker": "XLB", "name": "Materials"},
    {"id": "communication_services", "ticker": "XLC", "name": "Communication Services"},
    {"id": "energy", "ticker": "XLE", "name": "Energy"},
    {"id": "financials", "ticker": "XLF", "name": "Financials"},
    {"id": "industrials", "ticker": "XLI", "name": "Industrials"},
    {"id": "technology", "ticker": "XLK", "name": "Technology"},
    {"id": "consumer_staples", "ticker": "XLP", "name": "Consumer Staples"},
    {"id": "real_estate", "ticker": "XLRE", "name": "Real Estate"},
    {"id": "utilities", "ticker": "XLU", "name": "Utilities"},
    {"id": "health_care", "ticker": "XLV", "name": "Health Care"},
    {"id": "consumer_discretionary", "ticker": "XLY", "name": "Consumer Discretionary"},
)

BENCHMARK_TICKER = "SPY"
RETURN_DAYS = (21, 63, 126)
FLOW_SHORT_DAYS = 5
FLOW_WINDOW_DAYS = 20
FLOW_HISTORY_DAYS = 252
FLOW_Z_CLIP = 3.0
FLOW_VALIDATION_HISTORY_DAYS = 800

# State Street histories show an inverse NAV/share-count jump on this date.
# Applying the split factor preserves any same-day creation/redemption instead
# of zeroing the entire observation. Any other inverse jump fails closed.
KNOWN_SHARE_SPLITS: dict[tuple[str, date], float] = {
    ("XLB", date(2025, 12, 5)): 2.0,
    ("XLE", date(2025, 12, 5)): 2.0,
    ("XLK", date(2025, 12, 5)): 2.0,
    ("XLU", date(2025, 12, 5)): 2.0,
    ("XLY", date(2025, 12, 5)): 2.0,
}


def _json_number(value: object, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _market_series(frame: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(frame["date"], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    values = pd.to_numeric(frame["value"], errors="coerce")
    series = pd.Series(values.values, index=dates).dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series


def _split_factors(frame: pd.DataFrame, ticker: str) -> pd.Series:
    """Return per-row share split factors and fail on unknown split-like jumps."""
    shares = frame["shares_outstanding"].astype(float)
    nav = frame["nav"].astype(float)
    share_ratio = shares / shares.shift(1)
    nav_ratio = nav / nav.shift(1)

    extreme_share_jump = (share_ratio >= 1.5) | (share_ratio <= (2 / 3))
    inverse_nav_jump = (share_ratio * nav_ratio - 1).abs() <= 0.10
    split_like = extreme_share_jump & inverse_nav_jump

    factors = pd.Series(1.0, index=frame.index)
    for index in frame.index[split_like]:
        split_date = pd.Timestamp(frame.loc[index, "date"]).date()
        key = (ticker.upper(), split_date)
        if key not in KNOWN_SHARE_SPLITS:
            raise ValueError(
                f"Unrecognized split-like NAV/share jump for {ticker} on {split_date}"
            )
        factor = KNOWN_SHARE_SPLITS[key]
        if abs(float(share_ratio.loc[index]) / factor - 1) > 0.10:
            raise ValueError(
                f"Unexpected share ratio for {ticker} split on {split_date}"
            )
        if abs(float(nav_ratio.loc[index]) * factor - 1) > 0.10:
            raise ValueError(f"Unexpected NAV ratio for {ticker} split on {split_date}")
        factors.loc[index] = factor

    expected_dates = {
        split_date
        for (split_ticker, split_date), _ in KNOWN_SHARE_SPLITS.items()
        if split_ticker == ticker.upper()
        and frame["date"].min().date() <= split_date <= frame["date"].max().date()
    }
    observed_dates = {
        pd.Timestamp(frame.loc[index, "date"]).date()
        for index in frame.index[factors != 1]
    }
    if expected_dates != observed_dates:
        missing = ", ".join(
            str(value) for value in sorted(expected_dates - observed_dates)
        )
        raise ValueError(f"Configured split was not observed for {ticker}: {missing}")
    return factors


def compute_net_issuance(frame: pd.DataFrame, ticker: str) -> tuple[pd.DataFrame, dict]:
    """Compute split-adjusted daily and rolling ETF net-issuance estimates."""
    ordered = (
        frame.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
        .copy()
    )
    if len(ordered) < FLOW_HISTORY_DAYS + FLOW_WINDOW_DAYS + 1:
        raise ValueError(f"Insufficient State Street history for {ticker}")
    # Old sponsor files contain isolated legacy share-count restatements that
    # predate the published signal window by years. Validate a fixed recent
    # history that comfortably covers the 252-observation robust baseline.
    ordered = ordered.tail(FLOW_VALIDATION_HISTORY_DAYS).reset_index(drop=True)

    implied_assets = ordered["nav"] * ordered["shares_outstanding"]
    relative_asset_error = (
        implied_assets - ordered["total_net_assets"]
    ).abs() / ordered["total_net_assets"]
    if relative_asset_error.max() > 0.002:
        raise ValueError(
            f"NAV times shares does not reconcile to net assets for {ticker}"
        )

    factors = _split_factors(ordered, ticker)
    previous_adjusted_shares = ordered["shares_outstanding"].shift(1) * factors
    flow_usd = (ordered["shares_outstanding"] - previous_adjusted_shares) * ordered[
        "nav"
    ]

    economic_nav_return = ordered["nav"] * factors / ordered["nav"].shift(1)
    residual_flow = (
        ordered["total_net_assets"]
        - ordered["total_net_assets"].shift(1) * economic_nav_return
    )
    comparison = pd.concat([flow_usd, residual_flow], axis=1).dropna()
    tolerance = np.maximum(100_000.0, comparison.abs().max(axis=1) * 0.0001)
    if ((comparison.iloc[:, 0] - comparison.iloc[:, 1]).abs() > tolerance).any():
        raise ValueError(f"Share and net-asset flow estimates diverge for {ticker}")

    ordered["flow_usd"] = flow_usd
    ordered["flow_5d_usd"] = flow_usd.rolling(
        FLOW_SHORT_DAYS, min_periods=FLOW_SHORT_DAYS
    ).sum()
    ordered["flow_20d_usd"] = flow_usd.rolling(
        FLOW_WINDOW_DAYS, min_periods=FLOW_WINDOW_DAYS
    ).sum()
    ordered["flow_5d_pct_aum"] = ordered["flow_5d_usd"] / ordered[
        "total_net_assets"
    ].shift(FLOW_SHORT_DAYS)
    ordered["flow_20d_pct_aum"] = ordered["flow_20d_usd"] / ordered[
        "total_net_assets"
    ].shift(FLOW_WINDOW_DAYS)

    current = ordered.iloc[-1]
    history = ordered["flow_20d_pct_aum"].shift(1).dropna().iloc[-FLOW_HISTORY_DAYS:]
    flow_z = None
    if len(history) >= FLOW_HISTORY_DAYS:
        median = float(history.median())
        mad = float((history - median).abs().median())
        scale = 1.4826 * mad
        if scale > 1e-12:
            raw_z = (float(current["flow_20d_pct_aum"]) - median) / scale
            flow_z = float(np.clip(raw_z, -FLOW_Z_CLIP, FLOW_Z_CLIP))

    metrics = {
        "as_of": pd.Timestamp(current["date"]).strftime("%Y-%m-%d"),
        "aum_usd": _json_number(current["total_net_assets"], 2),
        "flow_1d_usd": _json_number(current["flow_usd"], 2),
        "flow_5d_usd": _json_number(current["flow_5d_usd"], 2),
        "flow_20d_usd": _json_number(current["flow_20d_usd"], 2),
        "flow_5d_pct_aum": _json_number(current["flow_5d_pct_aum"]),
        "flow_20d_pct_aum": _json_number(current["flow_20d_pct_aum"]),
        "flow_20d_z": _json_number(flow_z, 3),
        "history_observations": int(len(history)),
        "split_adjustments": int((factors != 1).sum()),
    }
    return ordered, metrics


def _log_return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        raise ValueError(f"Price history has fewer than {periods + 1} rows")
    now = float(series.iloc[-1])
    then = float(series.iloc[-1 - periods])
    if now <= 0 or then <= 0:
        raise ValueError("Price history contains a non-positive level")
    return float(math.log(now / then))


def _percentile(values: pd.Series) -> pd.Series:
    if len(values) <= 1:
        return pd.Series(50.0, index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (ranks - 1) / (len(values) - 1) * 100


class SectorRotationComputer:
    """Compute the separate price, net-issuance, and options evidence layers."""

    def __init__(
        self,
        market_client: object | None = None,
        fund_client: object | None = None,
        options_client: object | None = None,
    ) -> None:
        self.market_client = market_client or YFinanceClient()
        self.fund_client = fund_client or StateStreetETFClient()
        self.options_client = options_client or OCCOptionsClient()

    def _load_fund_histories(self, verbose: bool) -> dict[str, pd.DataFrame]:
        histories: dict[str, pd.DataFrame] = {}
        for ticker in (sector["ticker"] for sector in SECTOR_ETFS):
            if verbose:
                print(f"  State Street {ticker} NAV and shares...")
            histories[ticker] = self.fund_client.get_nav_history(ticker)
        return histories

    def _load_prices(self) -> tuple[dict[str, pd.Series], str]:
        tickers = [BENCHMARK_TICKER, *(sector["ticker"] for sector in SECTOR_ETFS)]
        now_et = datetime.now(ZoneInfo("America/New_York"))
        today_et = now_et.date()
        start = today_et - timedelta(days=365 * 4)
        # yfinance treats end as exclusive. Admit today's bar only after a
        # conservative post-close buffer so an intraday partial bar cannot rank.
        end_exclusive = today_et + timedelta(days=1) if now_et.hour >= 18 else today_et
        download_error: Exception | None = None
        try:
            frames = self.market_client.get_adjusted_histories(
                tickers,
                start_date=start.isoformat(),
                end_date=end_exclusive.isoformat(),
            )
        except Exception as exc:
            download_error = exc
            frames = {}

        for ticker in tickers:
            if ticker in frames:
                continue
            get_series = getattr(self.market_client, "get_series", None)
            if callable(get_series):
                try:
                    frames[ticker] = get_series(
                        ticker,
                        start_date=start.isoformat(),
                        end_date=end_exclusive.isoformat(),
                    )
                except Exception as exc:
                    download_error = download_error or exc

        missing = sorted(set(tickers) - set(frames))
        if missing:
            reason = f": {download_error}" if download_error else ""
            raise RuntimeError(
                "Adjusted total-return price history is unavailable for "
                + ", ".join(missing)
                + reason
            )

        prices = {ticker: _market_series(frames[ticker]) for ticker in tickers}
        too_short = sorted(
            ticker for ticker, series in prices.items() if len(series) < 260
        )
        if too_short:
            raise ValueError(
                "Insufficient adjusted price history for " + ", ".join(too_short)
            )
        return prices, "yahoo_adjusted_close"

    def _load_options(self, verbose: bool) -> tuple[dict[str, dict], dict]:
        if self.options_client is None:
            return {}, {"status": "disabled", "as_of": None, "baseline_month": None}

        today_et = datetime.now(ZoneInfo("America/New_York")).date()
        report_date = self.options_client.latest_completed_week(as_of=today_et)
        prior_month_end = report_date.replace(day=1) - timedelta(days=1)
        activity: dict[str, dict] = {}
        errors: dict[str, str] = {}

        for sector in SECTOR_ETFS:
            ticker = sector["ticker"]
            try:
                if verbose:
                    print(f"  OCC {ticker} cleared options volume...")
                weekly = self.options_client.aggregate_report(
                    self.options_client.get_report(ticker, report_date, "W"), ticker
                )
                monthly = self.options_client.aggregate_report(
                    self.options_client.get_report(ticker, prior_month_end, "M"), ticker
                )
                weekly_daily_average = (
                    weekly["total_volume"] / weekly["sessions"]
                    if weekly["sessions"] > 0
                    else None
                )
                monthly_daily_average = (
                    monthly["total_volume"] / monthly["sessions"]
                    if monthly["sessions"] > 0
                    else None
                )
                activity_ratio = (
                    weekly_daily_average / monthly_daily_average
                    if weekly_daily_average is not None
                    and monthly_daily_average is not None
                    and monthly_daily_average > 0
                    else None
                )
                activity[ticker] = {
                    "evidence_level": "cleared_activity",
                    "direction": None,
                    "trade_side": "unavailable",
                    "open_close": "unavailable",
                    "as_of": weekly["end_date"],
                    "week_start": weekly["start_date"],
                    "week_end": weekly["end_date"],
                    "sessions": weekly["sessions"],
                    "call_volume": weekly["call_volume"],
                    "put_volume": weekly["put_volume"],
                    "total_volume": weekly["total_volume"],
                    "put_call_ratio": weekly["put_call_ratio"],
                    "prior_month_daily_average": _json_number(monthly_daily_average, 2),
                    "activity_ratio": _json_number(activity_ratio, 3),
                    "excluded_adjusted_roots": sorted(
                        set(weekly["excluded_adjusted_roots"])
                        | set(monthly["excluded_adjusted_roots"])
                    ),
                }
            except Exception as exc:
                errors[ticker] = str(exc)

        status = (
            "complete"
            if len(activity) == len(SECTOR_ETFS)
            else ("partial" if activity else "unavailable")
        )
        activity_dates = [
            value["as_of"] for value in activity.values() if value.get("as_of")
        ]
        return activity, {
            "status": status,
            "as_of": min(activity_dates) if activity_dates else None,
            "report_date": report_date.isoformat(),
            "baseline_month": prior_month_end.strftime("%Y-%m"),
            "errors": errors,
        }

    def compute(self, include_options: bool = True, verbose: bool = True) -> dict:
        if verbose:
            print("Computing Select Sector SPDR flows and rotation...")

        fund_histories = self._load_fund_histories(verbose)
        flow_metrics: dict[str, dict] = {}
        for sector in SECTOR_ETFS:
            ticker = sector["ticker"]
            _, flow_metrics[ticker] = compute_net_issuance(
                fund_histories[ticker], ticker
            )

        prices, price_basis = self._load_prices()
        last_dates = {ticker: series.index.max() for ticker, series in prices.items()}
        common_date = min(last_dates.values())
        aligned = {
            ticker: series.loc[series.index <= common_date]
            for ticker, series in prices.items()
        }
        benchmark = aligned[BENCHMARK_TICKER]

        benchmark_returns = {days: _log_return(benchmark, days) for days in RETURN_DAYS}
        rows: list[dict] = []
        for sector in SECTOR_ETFS:
            ticker = sector["ticker"]
            series = aligned[ticker]
            returns = {days: _log_return(series, days) for days in RETURN_DAYS}
            excess = {
                days: returns[days] - benchmark_returns[days] for days in RETURN_DAYS
            }
            daily_returns = np.log(series / series.shift(1)).dropna().iloc[-63:]
            volatility = float(daily_returns.std(ddof=1))
            absolute_trend = (
                returns[126] / (volatility * math.sqrt(126))
                if volatility > 1e-12
                else 0.0
            )
            relative_strength = 0.5 * excess[63] + 0.5 * excess[126]
            acceleration = excess[21] - excess[63] / 3
            phase = (
                "leading"
                if relative_strength >= 0 and acceleration >= 0
                else "weakening"
                if relative_strength >= 0
                else "improving"
                if acceleration >= 0
                else "lagging"
            )
            rows.append(
                {
                    **sector,
                    "price_as_of": pd.Timestamp(common_date).strftime("%Y-%m-%d"),
                    "return_21d": _json_number(returns[21]),
                    "return_63d": _json_number(returns[63]),
                    "return_126d": _json_number(returns[126]),
                    "excess_21d": _json_number(excess[21]),
                    "excess_63d": _json_number(excess[63]),
                    "excess_126d": _json_number(excess[126]),
                    "relative_strength": _json_number(relative_strength),
                    "acceleration": _json_number(acceleration),
                    "absolute_trend": _json_number(absolute_trend),
                    "above_200d": bool(
                        len(series) >= 200
                        and series.iloc[-1] > series.iloc[-200:].mean()
                    ),
                    "phase": phase,
                    "fund_flow": flow_metrics[ticker],
                }
            )

        frame = pd.DataFrame(rows).set_index("ticker")
        relative_percentile = _percentile(frame["relative_strength"].astype(float))
        trend_percentile = _percentile(frame["absolute_trend"].astype(float))
        frame["price_score"] = 0.65 * relative_percentile + 0.35 * trend_percentile
        frame = frame.sort_values(["price_score", "relative_strength"], ascending=False)
        frame["rank"] = np.arange(1, len(frame) + 1)

        ranked_rows: list[dict] = []
        for ticker, row in frame.iterrows():
            item = row.to_dict()
            item["ticker"] = ticker
            item["rank"] = int(item["rank"])
            item["price_score"] = _json_number(item["price_score"], 1)
            ranked_rows.append(item)

        options_activity: dict[str, dict] = {}
        options_meta = {"status": "disabled", "as_of": None, "baseline_month": None}
        if include_options:
            options_activity, options_meta = self._load_options(verbose)

        for row in ranked_rows:
            ticker = row["ticker"]
            row["options_activity"] = options_activity.get(ticker)
            flow_value = row["fund_flow"]["flow_20d_pct_aum"]
            phase = row["phase"]
            if flow_value is None or flow_value == 0:
                row["flow_confirmation"] = "neutral"
            elif phase in {"leading", "improving"}:
                row["flow_confirmation"] = "supports" if flow_value > 0 else "diverges"
            else:
                row["flow_confirmation"] = "supports" if flow_value < 0 else "diverges"

        flow_ranked = sorted(
            ranked_rows,
            key=lambda row: (
                row["fund_flow"]["flow_20d_z"] is not None,
                (
                    row["fund_flow"]["flow_20d_z"]
                    if row["fund_flow"]["flow_20d_z"] is not None
                    else float("-inf")
                ),
            ),
            reverse=True,
        )
        options_ranked = sorted(
            [row for row in ranked_rows if row["options_activity"] is not None],
            key=lambda row: (
                row["options_activity"]["activity_ratio"]
                if row["options_activity"]["activity_ratio"] is not None
                else float("-inf")
            ),
            reverse=True,
        )

        computed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        flow_dates = [metrics["as_of"] for metrics in flow_metrics.values()]
        if len(set(flow_dates)) != 1:
            raise ValueError(
                "State Street sector histories do not share one as-of date"
            )
        payload = {
            "schema_version": "1.0",
            "computed_at": computed_at,
            "status": "complete",
            "signal_status": "descriptive_not_backtested",
            "universe": "select_sector_spdr_11",
            "benchmark": BENCHMARK_TICKER,
            "price_as_of": pd.Timestamp(common_date).strftime("%Y-%m-%d"),
            "fund_flow_as_of": min(flow_dates),
            "options_as_of": options_meta.get("as_of"),
            "price_basis": price_basis,
            "coverage": {
                "expected_sectors": len(SECTOR_ETFS),
                "price": len(ranked_rows),
                "fund_flows": len(flow_metrics),
                "options": len(options_activity),
                "complete_price_universe": len(ranked_rows) == len(SECTOR_ETFS),
                "complete_fund_flow_universe": len(flow_metrics) == len(SECTOR_ETFS),
                "options_status": options_meta.get("status"),
                "options_errors": options_meta.get("errors", {}),
            },
            "methodology": {
                "price_score": (
                    "65% cross-sectional percentile of average 63d/126d log excess "
                    "return vs SPY + 35% percentile of 126d return divided by "
                    "63d daily volatility scaled to 126d"
                ),
                "phase": (
                    "sign of medium relative strength crossed with sign of "
                    "21d acceleration vs one-third of 63d excess return"
                ),
                "fund_flow": (
                    "State Street Select Sector SPDR net issuance estimate: "
                    "NAV times split-adjusted change in shares outstanding"
                ),
                "flow_z": (
                    "20-session net issuance as a share of starting net assets, "
                    "robust z-score vs the prior 252 observations, clipped at +/-3"
                ),
                "options": (
                    "OCC standard-root cleared call/put account-side quantities "
                    "divided by two; weekly daily average vs prior-month daily average"
                ),
                "score_inputs": ["price_relative_strength", "absolute_trend"],
                "excluded_from_score": ["fund_flow", "options_activity"],
            },
            "sources": {
                "fund_flows": {
                    "provider": "State Street Investment Management",
                    "url_template": STATE_STREET_NAV_HISTORY_URL,
                    "point_in_time_history": False,
                    "revision_policy": "current sponsor workbook",
                },
                "prices": {
                    "provider": "Yahoo Finance via yfinance",
                    "basis": price_basis,
                    "point_in_time_history": False,
                },
                "options": {
                    "provider": "The Options Clearing Corporation",
                    "url": OCC_VOLUME_QUERY_URL,
                    "documentation": OCC_BATCH_DOC_URL,
                    "evidence_level": "cleared_activity",
                    "trade_direction": "unavailable",
                    "open_close": "unavailable",
                    "standard_roots_only": True,
                    "baseline_month": options_meta.get("baseline_month"),
                },
            },
            "opportunities": {
                "leaders": [row["id"] for row in ranked_rows[:3]],
                "laggards": [row["id"] for row in ranked_rows[-3:]],
                "improving": [
                    row["id"]
                    for row in sorted(
                        (row for row in ranked_rows if row["phase"] == "improving"),
                        key=lambda row: row["acceleration"] or 0,
                        reverse=True,
                    )[:3]
                ],
                "strongest_inflows": [row["id"] for row in flow_ranked[:3]],
                "most_active_options": [row["id"] for row in options_ranked[:3]],
            },
            "sectors": ranked_rows,
        }
        return payload


def compute_sector_rotation(
    include_options: bool = True,
    verbose: bool = True,
) -> dict:
    return SectorRotationComputer().compute(
        include_options=include_options,
        verbose=verbose,
    )

"""Observed, forward-only evaluation of published GLCI signals.

This module deliberately does not reconstruct old signals. It selects the first
immutable publication for each signal date and only evaluates market bars whose
weekly period end is later than that publication. The resulting record starts
when the publication ledger starts and is therefore small by design at first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_series_config
from ..etl.storage import DataStorage


FREQUENCY = "W-FRI"
LIVE_MIN_OBSERVATIONS = 20
REGIME_LABELS = {-1: "tight", 0: "neutral", 1: "loose"}


def _first_publications(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Return the first valid recorded computation for every signal date."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()

    required_columns = {"signal_date", "computed_at", "regime"}
    missing_columns = required_columns.difference(snapshots.columns)
    if missing_columns:
        raise ValueError(
            "Signal publication ledger is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    publications = snapshots.copy()
    publications["_signal_date"] = pd.to_datetime(
        publications.get("signal_date"), errors="coerce", utc=True
    ).dt.tz_convert(None).dt.normalize()
    publications["_computed_at"] = pd.to_datetime(
        publications.get("computed_at"), errors="coerce", utc=True
    )
    if publications[["_signal_date", "_computed_at"]].isna().any(axis=None):
        raise ValueError(
            "Signal publication ledger contains an unparseable signal_date or computed_at"
        )
    regime_values = pd.to_numeric(publications["regime"], errors="coerce")
    if regime_values.isna().any() or not regime_values.isin(REGIME_LABELS).all():
        raise ValueError(
            "Signal publication ledger contains a regime outside -1, 0, or 1"
        )
    publications["regime"] = regime_values.astype(int)
    computed_dates = publications["_computed_at"].dt.tz_convert(None).dt.normalize()
    if (computed_dates < publications["_signal_date"]).any():
        raise ValueError(
            "Signal publication ledger contains a computation before its signal date"
        )
    publications = publications.sort_values(
        ["_signal_date", "_computed_at"], kind="stable"
    )
    return publications.drop_duplicates("_signal_date", keep="first").reset_index(
        drop=True
    )


def _weekly_prices(raw: pd.DataFrame | None) -> pd.Series:
    """Convert raw prices to complete weekly closing observations without fill."""
    if raw is None or raw.empty or not {"date", "value"}.issubset(raw.columns):
        return pd.Series(dtype=float)

    prices = raw[["date", "value"]].copy()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    if prices["date"].dt.tz is not None:
        prices["date"] = prices["date"].dt.tz_localize(None)
    prices["value"] = pd.to_numeric(prices["value"], errors="coerce")
    prices = prices.dropna().sort_values("date").drop_duplicates("date", keep="last")
    if prices.empty:
        return pd.Series(dtype=float)

    last_observation = prices["date"].max().normalize()
    last_completed_friday = pd.offsets.Week(weekday=4).rollback(last_observation)
    weekly = prices.set_index("date")["value"].resample(FREQUENCY).last()
    weekly = weekly.loc[weekly.index <= last_completed_friday]
    weekly.index.name = "date"
    return weekly


def _entry_date(computed_at) -> pd.Timestamp:
    """Return the first W-FRI period end strictly after the computation date."""
    timestamp = pd.Timestamp(computed_at)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    day_after_publication = timestamp.normalize() + pd.Timedelta(days=1)
    return pd.offsets.Week(weekday=4).rollforward(day_after_publication)


def _outcome_rows(
    publications: pd.DataFrame,
    prices: pd.Series,
    horizon: int,
) -> list[dict]:
    latest_market_date = prices.index.max() if not prices.empty else None
    rows: list[dict] = []
    for _, publication in publications.iterrows():
        entry_date = _entry_date(publication["_computed_at"])
        exit_date = entry_date + pd.offsets.Week(n=horizon, weekday=4)
        status = "unavailable"
        outcome = None

        if latest_market_date is not None:
            if entry_date > latest_market_date or exit_date > latest_market_date:
                status = "pending"
            else:
                entry_price = prices.get(entry_date)
                exit_price = prices.get(exit_date)
                if (
                    entry_price is not None
                    and exit_price is not None
                    and np.isfinite(entry_price)
                    and np.isfinite(exit_price)
                    and entry_price != 0
                ):
                    status = "matured"
                    outcome = float(exit_price / entry_price - 1)

        regime = pd.to_numeric(publication.get("regime"), errors="coerce")
        rows.append(
            {
                "signal_date": publication["_signal_date"],
                "computed_at": publication["_computed_at"],
                "entry_date": entry_date,
                "exit_date": exit_date,
                "regime": int(regime) if pd.notna(regime) else None,
                "status": status,
                "return": outcome,
            }
        )
    return rows


def _summarize_outcomes(rows: list[dict], min_observations: int) -> dict:
    matured_returns = np.asarray(
        [row["return"] for row in rows if row["status"] == "matured"],
        dtype=float,
    )
    matured = int(len(matured_returns))
    pending_rows = [row for row in rows if row["status"] == "pending"]
    reportable = matured >= min_observations
    return {
        "issued": int(len(rows)),
        "matured": matured,
        "pending": int(len(pending_rows)),
        "unavailable": int(
            sum(row["status"] == "unavailable" for row in rows)
        ),
        "median": (
            round(float(np.median(matured_returns)), 6) if reportable else None
        ),
        "hit_rate": (
            round(float(np.mean(matured_returns > 0)), 4) if reportable else None
        ),
        "next_maturity_date": (
            min(row["exit_date"] for row in pending_rows).strftime("%Y-%m-%d")
            if pending_rows
            else None
        ),
        "status": "reportable" if reportable else "collecting",
    }


def _asset_record(
    asset_id: str,
    asset: dict,
    publications: pd.DataFrame,
    prices: pd.Series,
    horizons: list[int],
    min_observations: int,
) -> dict:
    by_horizon: dict[str, dict] = {}
    for horizon in horizons:
        rows = _outcome_rows(publications, prices, horizon)
        summary = _summarize_outcomes(rows, min_observations)
        by_regime = {
            label: _summarize_outcomes(
                [row for row in rows if row["regime"] == code],
                min_observations,
            )
            for code, label in REGIME_LABELS.items()
        }
        # All-signal counts describe ledger operations, not predictive
        # evidence. Only a published-regime cell can become reportable.
        summary["median"] = None
        summary["hit_rate"] = None
        summary["status"] = (
            "reportable"
            if any(stats["status"] == "reportable" for stats in by_regime.values())
            else "collecting"
        )
        summary["by_regime"] = by_regime
        by_horizon[str(horizon)] = summary

    return {
        "id": asset_id,
        "name": asset["name"],
        "category": asset["category"],
        "horizons": by_horizon,
    }


def compute_live_evaluation(
    storage: DataStorage,
    asset_config: dict[str, dict],
    *,
    horizons: list[int],
    min_observations: int = LIVE_MIN_OBSERVATIONS,
) -> dict:
    """Evaluate first-published signals against later, cached weekly prices."""
    if min_observations <= 0:
        raise ValueError("min_observations must be positive")
    if not horizons or any(horizon <= 0 for horizon in horizons):
        raise ValueError("horizons must contain positive week counts")

    snapshots = storage.load_curated("indices", "glci_vintages")
    if snapshots is None:
        snapshots = pd.DataFrame()
    publications = _first_publications(snapshots)

    signal_dates = pd.to_datetime(
        snapshots.get("signal_date", pd.Series(dtype=object)),
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None).dropna()
    unique_signal_dates = int(signal_dates.dt.normalize().nunique())
    ledger = {
        "vintage_count": int(len(snapshots)),
        "unique_signal_dates": unique_signal_dates,
        "duplicate_vintages": max(0, int(len(snapshots)) - unique_signal_dates),
        "first_signal_date": (
            signal_dates.min().strftime("%Y-%m-%d") if not signal_dates.empty else None
        ),
        "latest_signal_date": (
            signal_dates.max().strftime("%Y-%m-%d") if not signal_dates.empty else None
        ),
    }
    methodology = {
        "signal_selection": "first_publication_per_signal_date",
        "entry_rule": "first_complete_W-FRI_bar_after_computed_at",
        "evidence_unit": "asset_horizon_regime",
        "source_vintage_complete": False,
        "outcome_vintage_complete": False,
        "signal_recorded_before_outcome": True,
        "min_observations": int(min_observations),
    }

    if publications.empty:
        return {
            "status": "unavailable",
            "methodology": methodology,
            "ledger": ledger,
            "assets": [],
        }

    assets = []
    for asset_id, asset in asset_config.items():
        config = get_series_config(asset_id)
        source = config.get("source")
        raw = storage.load_raw(source, asset_id) if source else None
        assets.append(
            _asset_record(
                asset_id,
                asset,
                publications,
                _weekly_prices(raw),
                horizons,
                min_observations,
            )
        )

    reportable = any(
        regime_stats["status"] == "reportable"
        for asset in assets
        for horizon_stats in asset["horizons"].values()
        for regime_stats in horizon_stats["by_regime"].values()
    )
    return {
        "status": "reportable" if reportable else "collecting",
        "methodology": methodology,
        "ledger": ledger,
        "assets": assets,
    }

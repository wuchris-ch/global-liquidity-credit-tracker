"""Shared provenance and freshness helpers for GLCI delivery surfaces."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import get_index_config
from .etl.storage import DataStorage


STALENESS_ALLOWANCE_DAYS = {
    "daily": 10,
    "weekly": 21,
    "monthly": 62,
    "quarterly": 150,
    "annual": 450,
}
DEFAULT_STALENESS_ALLOWANCE_DAYS = 45


def staleness_allowance_days(frequency: str | None) -> int:
    """Return a release-cadence-aware staleness allowance."""
    return STALENESS_ALLOWANCE_DAYS.get(
        str(frequency or "").lower(),
        DEFAULT_STALENESS_ALLOWANCE_DAYS,
    )


def utc_timestamp(value: Any) -> pd.Timestamp | None:
    """Parse a timestamp and normalize it to UTC, or return null."""
    if value is None or pd.isna(value):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def freshness_state(
    last_date: Any,
    frequency: str | None,
    *,
    now: Any | None = None,
) -> tuple[int, bool]:
    """Return calendar days old and whether the observation is stale."""
    latest = utc_timestamp(last_date)
    current = utc_timestamp(now if now is not None else pd.Timestamp.now(tz="UTC"))
    if latest is None or current is None:
        return -1, True
    days_old = int((current.normalize() - latest.normalize()).days)
    return days_old, days_old < 0 or days_old > staleness_allowance_days(frequency)


def _safe_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(number) or number in (float("inf"), float("-inf")):
        return None
    return int(number) if number.is_integer() else number


def _series_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    names = []
    for value in values:
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        if isinstance(value, str) and value:
            names.append(value)
    return names


def _snapshot_summary(storage: DataStorage) -> dict:
    snapshots_df = storage.load_curated("indices", "glci_vintages")
    if snapshots_df is None or snapshots_df.empty:
        return {
            "count": 0,
            "first_computed_at": None,
            "last_computed_at": None,
        }

    computed = [
        timestamp
        for timestamp in (
            utc_timestamp(value)
            for value in snapshots_df.get("computed_at", pd.Series(dtype=object))
        )
        if timestamp is not None
    ]
    return {
        "count": int(len(snapshots_df)),
        "first_computed_at": (
            min(computed).isoformat().replace("+00:00", "Z") if computed else None
        ),
        "last_computed_at": (
            max(computed).isoformat().replace("+00:00", "Z") if computed else None
        ),
    }


def _format_date(value: Any) -> str | None:
    timestamp = utc_timestamp(value)
    return timestamp.strftime("%Y-%m-%d") if timestamp is not None else None


def build_glci_trust_payload(
    storage: DataStorage,
    series_config: dict[str, dict],
    *,
    now: Any | None = None,
) -> dict:
    """Build one trust payload for both static export and the live API."""
    metadata = storage.load_curated_metadata("indices", "glci") or {}
    has_model_pillar_metadata = "pillar_stats" in metadata
    raw_pillar_stats = metadata.get("pillar_stats", {})
    if not isinstance(raw_pillar_stats, dict):
        raw_pillar_stats = {}

    index_config = get_index_config("global_liquidity_credit_index") or {}
    configured_pillars = index_config.get("pillars", {})
    expected_components: set[str] = set()
    covered_components: set[str] = set()
    missing_components: set[str] = set()
    stale_components: set[str] = set()
    excluded_components: set[str] = set()
    failed_pillars: set[str] = set()
    pillar_stats: dict[str, dict] = {}

    for pillar_name, pillar_config in configured_pillars.items():
        raw_stats = raw_pillar_stats.get(pillar_name)
        pillar_metadata_present = isinstance(raw_stats, dict)
        stats = raw_stats
        if not pillar_metadata_present:
            stats = {}
        quality = stats.get("data_quality", {})
        if not isinstance(quality, dict):
            quality = {}

        components = {
            component["series"]
            for component in pillar_config.get("components", [])
            if component.get("series")
        }
        expected_components.update(components)

        if has_model_pillar_metadata and not pillar_metadata_present:
            failed_pillars.add(pillar_name)

        has_pillar_quality = any(
            key in quality
            for key in (
                "loaded_series",
                "available_series",
                "used_series",
                "missing_series",
                "stale_series",
            )
        )
        used_series = set(_series_names(quality.get("used_series")))
        excluded_series = set(_series_names(quality.get("excluded_series")))
        pillar_missing = set(_series_names(quality.get("missing_series")))
        pillar_stale = set(_series_names(quality.get("stale_series")))

        # Fitted-pillar metadata is authoritative once it exists. An omitted
        # pillar cannot gain model coverage from raw files left in the cache.
        if has_model_pillar_metadata and not has_pillar_quality:
            pillar_missing.update(components)

        if "used_series" in quality:
            covered_components.update(used_series)
        elif has_pillar_quality:
            covered_components.update(components - pillar_missing - excluded_series)

        missing_components.update(pillar_missing)
        stale_components.update(pillar_stale)
        excluded_components.update(excluded_series)

        for series_id in components:
            component_config = series_config.get(series_id, {})
            latest = storage.get_latest_date(
                component_config.get("source", "unknown"),
                series_id,
            )
            if latest is None:
                # Factor inputs are fetched directly and are not guaranteed to
                # be copied into DataStorage. Model quality is authoritative.
                if not has_pillar_quality and not has_model_pillar_metadata:
                    missing_components.add(series_id)
                    pillar_missing.add(series_id)
                continue

            _, is_stale = freshness_state(
                latest,
                component_config.get("frequency"),
                now=now,
            )
            if is_stale:
                stale_components.add(series_id)
                pillar_stale.add(series_id)
            if not has_pillar_quality and not has_model_pillar_metadata:
                covered_components.add(series_id)

        missing_components.update(pillar_missing)

        pillar_stats[pillar_name] = {
            "method": stats.get("method"),
            "explained_variance": _safe_number(stats.get("explained_variance")),
            "n_variables": _safe_number(stats.get("n_variables")),
            "data_quality": {
                "total_series": _safe_number(
                    quality.get("total_series", len(components))
                ),
                "available_series": _safe_number(
                    quality.get("available_series", quality.get("loaded_series"))
                ),
                "loaded_series": _safe_number(quality.get("loaded_series")),
                "used_series": sorted(used_series),
                "excluded_series": sorted(excluded_series),
                "missing_series": sorted(pillar_missing),
                "low_coverage": sorted(set(_series_names(quality.get("low_coverage")))),
                "stale_series": sorted(pillar_stale),
            },
        }

    covered_components &= expected_components
    missing_components &= expected_components
    stale_components &= expected_components
    excluded_components &= expected_components

    glci_df = storage.load_curated("indices", "glci")
    as_of = None
    if glci_df is not None and not glci_df.empty and "date" in glci_df:
        as_of = _format_date(glci_df["date"].max())

    return {
        "as_of": as_of,
        "historical_mode": "reconstructed_current_vintage",
        "point_in_time": False,
        "frequency": "W-FRI",
        "snapshots": _snapshot_summary(storage),
        "data_quality": {
            # Keep the established field name for the frontend contract, but
            # count only components represented in fitted factors when known.
            "loaded_components": len(covered_components),
            "total_components": len(expected_components),
            "missing_components": sorted(missing_components),
            "stale_components": sorted(stale_components),
            "excluded_components": sorted(excluded_components),
            "failed_pillars": sorted(failed_pillars),
        },
        "pillar_stats": pillar_stats,
    }

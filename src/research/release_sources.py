"""Bounded, public FRED release tracks. Calendar expectations are not availability."""

from __future__ import annotations

import os
from datetime import date

from .contracts import Series

WORKSPACE = "public-release-lab"
TRACKING_START = "2026-06-01"
OBSERVATION_START = "2022-12-01"
TRACKS = {
    "PAYEMS": dict(
        name="Nonfarm payrolls",
        agency="Bureau of Labor Statistics",
        release_id=50,
        release_name="Employment Situation",
        frequency="monthly",
        unit="Thousands of Persons",
        adjustment="SA",
        operation="difference",
        result_unit="thousand jobs",
        threshold=100,
        decimals=0,
        source_url="https://www.bls.gov/ces/",
        license_url="https://www.bls.gov/bls/linksite.htm",
    ),
    "INDPRO": dict(
        name="Industrial production",
        agency="Federal Reserve Board",
        release_id=13,
        release_name="G.17 Industrial Production and Capacity Utilization",
        frequency="monthly",
        unit="Index 2017=100",
        adjustment="SA",
        operation="pct_change",
        result_unit="%",
        threshold=0,
        decimals=2,
        source_url="https://www.federalreserve.gov/releases/g17/",
        license_url="https://www.federalreserve.gov/disclaimer.htm",
    ),
    "A191RL1Q225SBEA": dict(
        name="Real GDP growth",
        agency="Bureau of Economic Analysis",
        release_id=53,
        release_name="Gross Domestic Product",
        frequency="quarterly",
        unit="Percent Change from Preceding Period",
        adjustment="SAAR",
        operation="level",
        result_unit="% annualized",
        threshold=1.5,
        decimals=1,
        source_url="https://www.bea.gov/data/gdp/gross-domestic-product",
        license_url="https://www.bea.gov/about/policies-and-information",
    ),
}


def declaration(series_id: str) -> Series:
    track = TRACKS[series_id]
    return Series(
        id=series_id,
        source_id=series_id,
        name=track["name"],
        source="fred",
        country="US",
        frequency=track["frequency"],
        unit=track["unit"],
        dimensions={"seasonal_adjustment": track["adjustment"]},
        source_url=track["source_url"],
        redistribution="allowed",
    )


def periods(start: str, end: str, frequency="monthly") -> list[str]:
    """Exact calendar grid. December is not a quarterly observation anchor."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    year, month = a.year, a.month
    output = []
    while date(year, month, 1) <= b:
        current = date(year, month, 1)
        if current >= a and (frequency == "monthly" or month in (1, 4, 7, 10)):
            output.append(current.isoformat())
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return output


def paged(transport, endpoint, field, params, budget=10000):
    """Archive every page; reject unstable counts, duplicate pages and date escapes."""
    if not os.getenv("FRED_API_KEY"):
        raise ValueError("FRED_API_KEY is not configured")
    offset, total, rows, captures = 0, None, [], []
    while True:
        data, cap = transport.get(
            "https://api.stlouisfed.org/fred/" + endpoint,
            {
                **params,
                "api_key": os.environ["FRED_API_KEY"],
                "file_type": "json",
                "limit": min(10000, budget),
                "offset": offset,
                "sort_order": "asc",
            },
        )
        captures.append(cap)
        count = int(data["count"])
        if total is None:
            total = count
        if (
            count != total
            or count < 0
            or count > budget
            or int(data["offset"]) != offset
        ):
            raise ValueError("Unstable or excessive source page count")
        page = data[field]
        rows.extend(page)
        offset += len(page)
        if offset >= total:
            break
        if not page:
            raise ValueError("Source pagination is incomplete")
    if len(rows) != total:
        raise ValueError("Source count does not match returned rows")
    return rows, captures


def release_inventory(transport, series_id, start, today, end):
    track = TRACKS[series_id]
    releases, release_cap = transport.get(
        "https://api.stlouisfed.org/fred/series/release",
        {
            "series_id": series_id,
            "api_key": os.environ["FRED_API_KEY"],
            "file_type": "json",
        },
    )
    if [r["id"] for r in releases["releases"]] != [track["release_id"]]:
        raise ValueError("Series release association changed; review the track")
    # FRED's default real-time day can still be yesterday after UTC midnight.
    # Use the returned provider date, not an inferred timezone or future cutoff.
    source_as_of = min(today, releases["realtime_end"])
    date.fromisoformat(source_as_of)
    calendar, calendar_caps = paged(
        transport,
        "release/dates",
        "release_dates",
        {
            "release_id": track["release_id"],
            "realtime_start": start,
            "realtime_end": end,
            "include_release_dates_with_no_data": "true",
        },
    )
    vintages, vintage_caps = paged(
        transport,
        "series/vintagedates",
        "vintage_dates",
        {"series_id": series_id, "realtime_start": start, "realtime_end": source_as_of},
    )
    dates = [r["date"] for r in calendar]
    if any(r["release_id"] != track["release_id"] for r in calendar):
        raise ValueError("Calendar contains another release")
    if (
        len(dates) != len(set(dates))
        or len(vintages) != len(set(vintages))
        or any(not start <= d <= end for d in dates)
        or any(not start <= d <= today for d in vintages)
    ):
        raise ValueError("Duplicate or out-of-range release dates")
    # Parse, rather than accepting lexically plausible but invalid dates.
    for d in dates + vintages:
        date.fromisoformat(d)
    return dict(
        calendar=sorted(dates),
        vintages=sorted(vintages),
        source_as_of=source_as_of,
        captures=[release_cap, *calendar_caps, *vintage_caps],
    )


def validate_partition(store, series_id, scope, rows, captures):
    """Completeness follows vintage-specific provider metadata, never wall-clock lag."""
    track = TRACKS[series_id]
    metadata = store.objects.json(
        store.control.get(WORKSPACE, "capture", captures[0])["body"]
    )
    meta = metadata["seriess"][0]
    if meta["seasonal_adjustment_short"] != track["adjustment"]:
        raise ValueError("Seasonal adjustment changed; publication held for review")
    if meta["realtime_start"] != str(scope.information_date) or meta[
        "realtime_end"
    ] != str(scope.information_date):
        raise ValueError("Metadata information date differs from the requested vintage")
    last = min(meta["observation_end"], str(scope.end))
    expected = periods(str(scope.start), last, track["frequency"])
    if len(expected) < 2 or [str(r.date) for r in rows] != expected:
        raise ValueError(
            "Partial partition: calendar grid or last published period is missing"
        )
    if any(r.status != "observed" for r in rows):
        raise ValueError(
            "Partial partition: source reports missing or retracted observations"
        )
    for cap in captures[1:]:
        data = store.objects.json(store.control.get(WORKSPACE, "capture", cap)["body"])
        if (
            data["realtime_start"] != str(scope.information_date)
            or data["realtime_end"] != str(scope.information_date)
            or data.get("units") != "lin"
            or int(data.get("output_type", 0)) != 1
        ):
            raise ValueError(
                "Observation response has a different vintage or transformation"
            )
    if any(
        r.attributes.get("query_realtime_start") != str(scope.information_date)
        or r.attributes.get("query_realtime_end") != str(scope.information_date)
        for r in rows
    ):
        raise ValueError(
            "Observation information date differs from the requested vintage"
        )

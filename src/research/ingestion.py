"""Bounded source acquisition; resumable jobs commit one explicit partition."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .contracts import Observation, Scope, Series
from .storage import ResearchStore, canonical


class TransientSourceError(RuntimeError):
    pass


class Transport:
    """One retry owner. Global request spacing is per collector process."""

    def __init__(self, store, workspace, session=None, spacing=2.0):
        self.store, self.workspace = store, workspace
        self.session = session or requests.Session()
        self.spacing, self.last_request = spacing, 0.0

    def get(self, url, params, headers=None):
        deadline = time.monotonic() + 120
        for attempt in range(4):
            time.sleep(max(0, self.spacing - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.get(
                    url, params=params, headers=headers or {}, timeout=(5, 20)
                )
            except requests.RequestException:
                response = None
            retry = response is None or response.status_code in (
                429,
                500,
                502,
                503,
                504,
            )
            if retry:
                delay = min(15, 2**attempt + random.random())
                if response is not None:
                    try:
                        delay = min(
                            60,
                            max(delay, float(response.headers.get("Retry-After", "0"))),
                        )
                    except ValueError:
                        from datetime import datetime, timezone
                        from email.utils import parsedate_to_datetime

                        try:
                            delay = min(
                                60,
                                max(
                                    delay,
                                    (
                                        parsedate_to_datetime(
                                            response.headers["Retry-After"]
                                        )
                                        - datetime.now(timezone.utc)
                                    ).total_seconds(),
                                ),
                            )
                        except (KeyError, ValueError, TypeError):
                            pass
                if attempt == 3 or time.monotonic() + delay >= deadline:
                    raise TransientSourceError(
                        "Source unavailable after bounded retries"
                    ) from None
                time.sleep(delay)
                continue
            if response.status_code != 200:
                raise ValueError(
                    f"Source rejected request (HTTP {response.status_code})"
                )
            capture = self.store.capture(self.workspace, url, params, response.content)
            try:
                return response.json(), capture["id"]
            except ValueError:
                raise ValueError(
                    "Source returned malformed JSON; response preserved"
                ) from None
        raise TransientSourceError("Source timeout")


def fred_snapshot(
    store: ResearchStore, workspace: str, series: Series, scope: Scope, transport=None
):
    if scope.mode != "source_vintage":
        raise ValueError("FRED historical queries require source_vintage mode")
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise ValueError("FRED_API_KEY is not configured")
    transport = transport or Transport(store, workspace)
    params = {
        "series_id": series.source_id,
        "api_key": key,
        "file_type": "json",
        "realtime_start": str(scope.information_date),
        "realtime_end": str(scope.information_date),
        "observation_start": str(scope.start),
        "observation_end": str(scope.end),
        "limit": 10000,
        "offset": 0,
    }
    from .source_metadata import verify_fred

    metadata_capture = verify_fred(series, scope, transport)
    rows, captures, total = [], [metadata_capture], None
    while True:
        data, cap = transport.get(
            "https://api.stlouisfed.org/fred/series/observations", params
        )
        captures.append(cap)
        if total is None:
            total = int(data["count"])
        if (
            total != int(data["count"])
            or total > 200000
            or int(data["offset"]) != params["offset"]
        ):
            raise ValueError("Unstable or excessive FRED page count")
        page = data["observations"]
        for r in page:
            missing = r["value"] == "."
            rows.append(
                Observation(
                    date=r["date"],
                    value=None if missing else r["value"],
                    status="missing" if missing else "observed",
                    attributes={
                        "query_realtime_start": r["realtime_start"],
                        "query_realtime_end": r["realtime_end"],
                    },
                )
            )
        params["offset"] += len(page)
        if params["offset"] >= total:
            break
        if not page:
            raise ValueError("Incomplete FRED pagination")
    if len(rows) != total:
        raise ValueError("FRED observation count mismatch")
    return store.ingest(workspace, series, scope, rows, captures)


def fred_vintage_dates(store, workspace, source_id, start, end, transport=None):
    transport = transport or Transport(store, workspace)
    if not os.getenv("FRED_API_KEY"):
        raise ValueError("FRED_API_KEY is not configured")
    dates, offset, total = [], 0, None
    while True:
        data, _ = transport.get(
            "https://api.stlouisfed.org/fred/series/vintagedates",
            {
                "series_id": source_id,
                "file_type": "json",
                "api_key": os.environ["FRED_API_KEY"],
                "realtime_start": start,
                "realtime_end": end,
                "offset": offset,
                "limit": 10000,
            },
        )
        if total is None:
            total = int(data["count"])
        if total != int(data["count"]) or total > 100000:
            raise ValueError("Unstable vintage enumeration")
        page = data["vintage_dates"]
        dates.extend(page)
        offset += len(page)
        if offset >= total:
            break
        if not page:
            raise ValueError("Incomplete vintage enumeration")
    if len(dates) != total or len(set(dates)) != len(dates):
        raise ValueError("Incomplete or duplicate vintage enumeration")
    return sorted(dates)


def source_snapshot(store, workspace, series: Series, scope: Scope, transport=None):
    if series.source == "fred":
        return fred_snapshot(store, workspace, series, scope, transport)
    if (
        scope.mode != "forward_capture"
        or scope.information_date != datetime.now(timezone.utc).date()
    ):
        raise ValueError(
            "This source supports forward captures only; do not backdate current data"
        )
    transport = transport or Transport(store, workspace)
    captures, rows = [], []
    if series.source == "worldbank":
        import re

        if not re.fullmatch("[A-Z]{3}", series.country):
            raise ValueError("World Bank requires one ISO3 country")
        allowed_units = {
            "NY.GDP.MKTP.CD": "current USD",
            "NY.GDP.MKTP.KD.ZG": "percent",
            "FS.AST.PRVT.GD.ZS": "percent GDP",
            "FM.LBL.BMNY.GD.ZS": "percent GDP",
            "FD.AST.PRVT.GD.ZS": "percent GDP",
        }
        if (
            allowed_units.get(series.source_id) != series.unit
            or series.frequency != "annual"
        ):
            raise ValueError(
                "World Bank unit/frequency contract is unreviewed or mismatched"
            )
        base = f"https://api.worldbank.org/v2/country/{series.country}/indicator/{series.source_id}"
        page, total, updated = 1, None, None
        while True:
            data, cap = transport.get(
                base,
                {
                    "format": "json",
                    "date": f"{scope.start.year}:{scope.end.year}",
                    "source": series.dimensions.get("source", "2"),
                    "footnote": "y",
                    "per_page": 1000,
                    "page": page,
                },
            )
            captures.append(cap)
            meta, observations = data
            if total is None:
                total, updated = int(meta["total"]), meta.get("lastupdated")
            if (
                int(meta["total"]) != total
                or meta.get("lastupdated") != updated
                or int(meta["pages"]) > 200
            ):
                raise ValueError("World Bank snapshot changed during pagination")
            for r in observations or []:
                if r.get("countryiso3code") != series.country:
                    raise ValueError(
                        "Unexpected World Bank country; use an ISO3 single-country series"
                    )
                rows.append(
                    Observation(
                        date=f"{r['date']}-12-31",
                        value=r["value"],
                        status="observed" if r["value"] is not None else "missing",
                        attributes={
                            "footnote": str(r.get("footnote", "")),
                            "obs_status": str(r.get("obs_status", "")),
                        },
                    )
                )
            if page >= int(meta["pages"]):
                break
            page += 1
        if len(rows) != total:
            raise ValueError("Incomplete World Bank response")
    elif series.source == "nyfed":
        if series.source_id.lower() != "sofr":
            raise ValueError("Research NY Fed adapter currently admits SOFR only")
        data, cap = transport.get(
            "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json",
            {"startDate": str(scope.start), "endDate": str(scope.end)},
        )
        captures.append(cap)
        if (
            series.unit != "percent"
            or series.frequency != "daily"
            or series.country != "USA"
        ):
            raise ValueError("SOFR requires daily percent rates for USA")
        for r in data["refRates"]:
            rows.append(
                Observation(
                    date=r["effectiveDate"],
                    value=r["percentRate"],
                    attributes={
                        "revisionIndicator": str(r.get("revisionIndicator", "")),
                        "volumeInBillions": str(r.get("volumeInBillions", "")),
                    },
                )
            )
    elif series.source == "bis":
        dataflow = series.dimensions.get("dataflow", "WS_TC")
        import re

        if dataflow != "WS_TC" or not re.fullmatch(
            r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){6}", series.source_id
        ):
            raise ValueError("BIS research requires a full seven-dimension WS_TC key")
        data, cap = transport.get(
            f"https://stats.bis.org/api/v1/data/{dataflow}/{series.source_id}",
            {"startPeriod": str(scope.start), "endPeriod": str(scope.end)},
            headers={"Accept": "application/vnd.sdmx.data+json;version=1.0.0"},
        )
        captures.append(cap)
        section = data.get("data", data)
        structure = section["structure"]
        observations = section["dataSets"][0]["series"]
        if len(observations) != 1:
            raise ValueError("BIS query must resolve to exactly one full dimension key")
        from .source_metadata import verify_bis

        verify_bis(series, structure, next(iter(observations)))
        series_values = next(iter(observations.values()))
        attributes = {
            a["id"]: a["values"][i]["id"]
            for a, i in zip(
                structure["attributes"]["series"], series_values["attributes"]
            )
            if i is not None
        }
        multiplier = {"9": "billions", "6": "millions", "0": "units"}.get(
            attributes.get("UNIT_MULT")
        )
        if (
            series.unit != f"{multiplier} {attributes.get('UNIT_MEASURE')}"
            or series.frequency != "quarterly"
        ):
            raise ValueError("BIS unit multiplier or frequency differs from contract")
        time_dim = next(
            d["values"]
            for d in structure["dimensions"]["observation"]
            if d["id"] == "TIME_PERIOD"
        )
        import pandas as pd

        for idx, values in next(iter(observations.values()))["observations"].items():
            label = time_dim[int(idx)]["id"]
            period = (
                pd.Period(label, freq="Q").end_time.date()
                if "-Q" in label
                else pd.Timestamp(label).date()
            )
            rows.append(
                Observation(
                    date=period,
                    value=values[0],
                    status="observed" if values[0] is not None else "missing",
                    attributes={
                        "source_period": label,
                        "structure_hash": store.objects.write(canonical(structure)),
                    },
                )
            )
    else:
        raise ValueError("Unsupported research source")
    rows = [r for r in rows if scope.start <= r.date <= scope.end]
    return store.ingest(workspace, series, scope, rows, captures)


def load_demo(store, workspace="personal"):
    fixture = Path(__file__).parent / "fixtures" / "gdp-vintages.json"
    series = Series(
        id="fred:A191RL1Q225SBEA",
        name="US real GDP growth",
        source="fred",
        source_id="A191RL1Q225SBEA",
        country="USA",
        unit="percent_qoq_saar",
        frequency="quarterly",
        redistribution="allowed",
        source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
        notes="Authentic 2024 Q1 estimates. Imported archival fixture, not a past platform publication.",
    )
    for item in json.loads(fixture.read_text()):
        capture = store.capture(
            workspace,
            item["url"],
            item["params"],
            canonical(item["response"]),
            "reviewed_json_fixture",
        )
        scope = Scope(
            start="2024-01-01",
            end="2024-01-01",
            information_date=item["params"]["realtime_start"],
            mode="source_vintage",
        )
        rows = [
            Observation(date=r["date"], value=r["value"])
            for r in item["response"]["observations"]
        ]
        store.ingest(workspace, series, scope, rows, [capture["id"]])
    return series

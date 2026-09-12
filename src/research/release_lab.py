"""Release reconciliation, immutable captures and atomic public research bundles."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .contracts import Query, Scope, now
from .control import Conflict
from .ingestion import Transport, TransientSourceError, fred_snapshot
from .release_sources import (
    OBSERVATION_START,
    TRACKING_START,
    TRACKS,
    WORKSPACE,
    declaration,
    release_inventory,
    validate_partition,
)
from .storage import canonical, digest


def capture_release(store, series_id, information_date, transport=None):
    start = (
        "2023-01-01"
        if TRACKS[series_id]["frequency"] == "quarterly"
        else OBSERVATION_START
    )
    scope = Scope(
        start=start,
        end=information_date,
        information_date=information_date,
        mode="source_vintage",
    )
    transport = transport or Transport(store, WORKSPACE)
    manifest = fred_snapshot(
        store,
        WORKSPACE,
        declaration(series_id),
        scope,
        transport,
        validator=lambda rows, caps: validate_partition(
            store, series_id, scope, rows, caps
        ),
    )
    result = store.query(
        WORKSPACE,
        Query(
            series_id=series_id,
            start=scope.start,
            end=scope.end,
            as_of=information_date,
            dataset=manifest,
        ),
    )
    snapshot = dict(
        series_id=series_id,
        information_date=information_date,
        observation_start=result["data"][0]["date"],
        observation_end=result["data"][-1]["date"],
        observations=[{k: row[k] for k in ("date", "value")} for row in result["data"]],
        captures=result["evidence_ids"],
        dataset_manifest=manifest,
    )
    identifier = result["logical_hash"]
    try:
        # Fencing also protects the public snapshot pointer after the data commit.
        from .fencing import guard

        with store.control.transaction() as tx:
            guard(store.control, WORKSPACE, tx)
            store.control.put(
                WORKSPACE, "release_snapshot", identifier, snapshot, connection=tx
            )
    except Conflict:
        if (
            store.control.get(WORKSPACE, "release_snapshot", identifier)["observations"]
            != snapshot["observations"]
        ):
            raise
    return identifier


def upsert(store, kind, key, body):
    try:
        prior = store.control.get(WORKSPACE, kind, key)
    except KeyError:
        prior = None
    return store.control.put(
        WORKSPACE, kind, key, body, prior["version"] if prior else None
    )


def reconcile_releases(store, today=None, start=TRACKING_START, transport=None):
    """Enumerate the entire bounded horizon on every run, including missed polls.

    Successful older vintages are immutable. The two newest per series are
    rechecked once per 12-hour slot to detect same-vintage source corrections.
    A correction that conflicts with history is quarantined, never overwritten.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    day = date.fromisoformat(today)
    if day < date.fromisoformat(start):
        raise ValueError("Reconciliation date precedes the tracking horizon")
    end = (day + timedelta(days=45)).isoformat()
    transport = transport or Transport(store, WORKSPACE)
    slot = str(int(datetime.now(timezone.utc).timestamp()) // (12 * 3600))
    snapshots = store.control.list(WORKSPACE, "release_snapshot")
    complete = {(s["series_id"], s["information_date"]) for s in snapshots}
    queued = 0
    for series_id in TRACKS:
        try:
            inventory = release_inventory(transport, series_id, start, today, end)
            upsert(
                store,
                "release_inventory",
                series_id,
                dict(
                    **inventory,
                    checked_at=now(),
                    as_of=today,
                    horizon_start=start,
                    horizon_end=end,
                    error=None,
                ),
            )
        except (ValueError, KeyError, TransientSourceError):
            # Preserve previous calendar and complete snapshots when discovery fails.
            try:
                inventory = store.control.get(WORKSPACE, "release_inventory", series_id)
            except KeyError:
                inventory = dict(calendar=[], vintages=[], captures=[])
            upsert(
                store,
                "release_inventory",
                series_id,
                {
                    **inventory,
                    "attempted_at": now(),
                    "error": "Source discovery did not pass verification; last complete inventory retained.",
                },
            )
            continue
        for vintage in inventory["vintages"]:
            if (series_id, vintage) in complete and vintage not in inventory[
                "vintages"
            ][-2:]:
                continue
            # Stable within a poll slot; failed/exhausted jobs can recover next slot.
            key = digest(
                canonical(
                    {
                        "track": series_id,
                        "vintage": vintage,
                        "slot": slot,
                        "validation": "calendar-grid/1",
                    }
                )
            )
            store.control.enqueue(
                WORKSPACE,
                key,
                "release_ingest",
                {"series_id": series_id, "information_date": vintage},
            )
            queued += 1
    return {"queued": queued, "as_of": today, "tracking_start": start}


def public_snapshot(store, snapshot):
    caps = [store.control.get(WORKSPACE, "capture", c) for c in snapshot["captures"]]
    return {
        k: snapshot[k]
        for k in (
            "id",
            "series_id",
            "information_date",
            "observation_start",
            "observation_end",
            "observations",
        )
    } | {
        "evidence": [c["body"] for c in caps],
        "captured_at": max(c["first_seen_at"] for c in caps),
    }


def bundle_evidence(store, capture_ids):
    result = {}
    for identifier in sorted(set(capture_ids)):
        cap = store.control.get(WORKSPACE, "capture", identifier)
        if not cap["url"].startswith("https://api.stlouisfed.org/fred/"):
            raise ValueError("Public bundle contains an unapproved source")
        body = store.objects.read(cap["body"])
        if os.getenv("FRED_API_KEY", "\x00").encode() in body:
            raise ValueError("Public source response contains a credential")
        result.setdefault(
            cap["body"],
            dict(
                sha256=cap["body"],
                source_url=cap["url"],
                params=cap["params"],
                captured_at=cap["first_seen_at"],
                bytes=len(body),
                body=body.decode("utf-8"),
            ),
        )
    return result


def seal_bundle(payload):
    # Integer-valued floats have one portable representation in browser JSON.
    def normalize(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        return value

    payload = normalize(payload)
    return {**payload, "id": digest(canonical(payload))}


def live_bundle(store, as_of=None):
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    snapshots = store.control.list(WORKSPACE, "release_snapshot")
    chosen, captures, inbox = [], [], []
    jobs = store.control.list(WORKSPACE, "job")
    for series_id in TRACKS:
        inventory = store.control.get(WORKSPACE, "release_inventory", series_id)
        candidates = sorted(
            [
                s
                for s in snapshots
                if s["series_id"] == series_id
                and s["information_date"] <= as_of
                and s["information_date"] in inventory["vintages"]
            ],
            key=lambda s: s["information_date"],
        )
        if len(candidates) < 2:
            raise ValueError(
                f"{series_id}: two complete verified vintages required before publication"
            )
        selected = candidates[-6:]
        chosen.extend(selected)
        for s in selected:
            captures.extend(s["captures"])
        captures.extend(inventory["captures"])
        if inventory.get("error"):
            inbox.append(
                dict(
                    series_id=series_id,
                    date=as_of,
                    status="discovery_held",
                    detail=inventory["error"],
                    checked_at=inventory.get("checked_at"),
                )
            )
        complete = {s["information_date"] for s in candidates}
        for d in sorted(set(inventory["calendar"]) | set(inventory["vintages"])):
            current_jobs = [
                j
                for j in jobs
                if j["payload"].get("series_id") == series_id
                and j["payload"].get("information_date") == d
            ]
            job = current_jobs[-1] if current_jobs else None
            if job and job["status"] in ("quarantined", "exhausted", "retry_wait"):
                status, detail = (
                    "verification_held",
                    "Capture held for verification. The previous complete snapshot remains available.",
                )
                if isinstance(job.get("result"), dict) and job["result"].get("error"):
                    detail = job["result"]["error"]
            elif d in complete:
                status = "verified" if d in inventory["calendar"] else "revision"
                detail = (
                    "Complete archived vintage verified."
                    if status == "verified"
                    else "An additional archived revision was captured outside the current release calendar."
                )
            elif d in inventory["vintages"]:
                status, detail = (
                    "queued",
                    "Archived vintage identified; capture and completeness checks are pending.",
                )
            elif d > as_of:
                status, detail = (
                    "scheduled",
                    "Provider calendar expectation. Source availability is checked separately.",
                )
            else:
                status, detail = (
                    "awaiting_vintage",
                    "No changed vintage is listed for this calendar date. The series may be unchanged or awaiting archive availability.",
                )
            inbox.append(
                dict(
                    series_id=series_id,
                    date=d,
                    status=status,
                    detail=detail,
                    checked_at=inventory.get("checked_at"),
                    evidence=[
                        store.control.get(WORKSPACE, "capture", c)["body"]
                        for c in inventory["captures"]
                    ],
                )
            )
    return seal_bundle(
        dict(
            schema_version="release-lab/1",
            kind="releases",
            as_of=as_of,
            captured_at=now(),
            tracking_start=TRACKING_START,
            series=[dict(id=key, **value) for key, value in TRACKS.items()],
            snapshots=[public_snapshot(store, s) for s in chosen],
            evidence=bundle_evidence(store, captures),
            inbox=inbox,
        )
    )


def write_bundle(bundle, target):
    """Readers see either the old complete JSON or the new complete JSON."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(bundle)
    if target.stem == bundle["id"] and target.exists():
        if target.read_bytes() != raw:
            raise ValueError("An immutable publication object changed")
        return len(raw)
    temp = target.with_suffix(".pending")
    with temp.open("wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, target)
    return len(raw)

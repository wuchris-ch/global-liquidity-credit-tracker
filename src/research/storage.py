"""Immutable objects with a transactional, workspace-scoped manifest head."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .contracts import Observation, Query, Scope, Series, now
from .control import Conflict, Control


def canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CoverageError(ValueError):
    pass


class Objects:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, identifier):
        if not re.fullmatch("[a-f0-9]{64}", identifier):
            raise ValueError("Invalid object digest")
        return self.root / identifier[:2] / identifier

    def write(self, data: bytes) -> str:
        identifier = digest(data)
        path = self.path(identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(temp, path)  # Atomic create-if-absent; never overwrite.
            except FileExistsError:
                if self.read(identifier) != data:
                    raise ValueError("Object hash collision")
        finally:
            os.unlink(temp)
        return identifier

    def read(self, identifier):
        data = self.path(identifier).read_bytes()
        if digest(data) != identifier:
            raise ValueError("Object integrity failure")
        return data

    def json(self, identifier):
        return json.loads(self.read(identifier))


class ResearchStore:
    def __init__(self, root: Path | str, database_url: str | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = Objects(self.root / "objects")
        self.control = Control(self.root, database_url)

    def capture(self, workspace, url, params, body, representation="http_response"):
        parsed = urlsplit(url)
        # Allowlist protocol parameters, not a growing blacklist of secret names.
        allowed = {
            "series_id",
            "file_type",
            "realtime_start",
            "realtime_end",
            "observation_start",
            "observation_end",
            "limit",
            "offset",
            "startPeriod",
            "endPeriod",
            "format",
            "date",
            "page",
            "per_page",
            "startDate",
            "endDate",
            "source",
            "footnote",
            "release_id",
            "include_release_dates_with_no_data",
            "sort_order",
            "output_type",
        }
        safe = {k: v for k, v in params.items() if k in allowed}
        clean_url = urlunsplit(
            (parsed.scheme, parsed.hostname or "", parsed.path, "", "")
        )
        body_id = self.objects.write(body)
        record = {
            "url": clean_url,
            "params": safe,
            "body": body_id,
            "representation": representation,
            "first_seen_at": now(),
        }
        return self.control.put(workspace, "capture", uuid.uuid4().hex, record)

    def ingest(
        self,
        workspace,
        series: Series,
        scope: Scope,
        rows: list[Observation],
        captures: list[str],
    ):
        if len(rows) > 200000:
            raise ValueError("Partition exceeds row budget")
        if len({r.date for r in rows}) != len(rows):
            raise ValueError(
                "Duplicate observation identity in a single-series snapshot"
            )
        if any(r.date < scope.start or r.date > scope.end for r in rows):
            raise ValueError("Observation outside capture scope")
        for c in captures:
            self.control.get(workspace, "capture", c)
        normalized = [
            r.model_dump(mode="json") for r in sorted(rows, key=lambda r: r.date)
        ]
        schema = pa.schema(
            [
                ("date", pa.string()),
                ("value", pa.string()),
                ("status", pa.string()),
                ("attributes", pa.string()),
            ]
        )
        table = pa.Table.from_pylist(
            [
                {**r, "attributes": json.dumps(r["attributes"], sort_keys=True)}
                for r in normalized
            ],
            schema=schema,
        )
        buffer = pa.BufferOutputStream()
        pq.write_table(table, buffer, compression="zstd")
        part = self.objects.write(buffer.getvalue().to_pybytes())
        logical = digest(
            canonical(
                {
                    "series": series.model_dump(mode="json"),
                    "scope": scope.model_dump(mode="json"),
                    "rows": normalized,
                }
            )
        )
        snapshot = {
            "series": series.model_dump(mode="json"),
            "scope": scope.model_dump(mode="json"),
            "part": part,
            "logical_hash": logical,
            "captures": captures,
            "row_count": len(rows),
        }
        # Concurrent publishers must retry the CAS and incorporate the winner's snapshots.
        for _ in range(8):
            try:
                head = self.control.get(workspace, "head", "current")
                old = self.objects.json(head["manifest"])
            except KeyError:
                head, old = None, {"snapshots": []}
            if any(s["logical_hash"] == logical for s in old["snapshots"]):
                return head["manifest"]
            for prior in old["snapshots"]:
                if prior["series"]["id"] == series.id and any(
                    prior["series"][k] != snapshot["series"][k]
                    for k in ("source", "source_id", "country", "dimensions")
                ):
                    raise ValueError(
                        "Series identity changed; register a new identity after review"
                    )
                if (
                    prior["series"]["id"] == series.id
                    and prior["scope"] == snapshot["scope"]
                    and scope.mode == "source_vintage"
                ):
                    raise ValueError(
                        "Conflicting historical snapshot for the same scope; explicit review required"
                    )
            manifest = {
                "schema_version": "1.0",
                "snapshots": old["snapshots"] + [snapshot],
            }
            identifier = self.objects.write(canonical(manifest))
            try:
                with self.control.transaction() as tx:
                    from .fencing import guard

                    guard(self.control, workspace, tx)
                    self.control.put(
                        workspace,
                        "manifest",
                        identifier,
                        {"object": identifier},
                        connection=tx,
                    )
                    self.control.put(
                        workspace,
                        "head",
                        "current",
                        {"manifest": identifier},
                        head["version"] if head else None,
                        tx,
                    )
                return identifier
            except Conflict:
                continue
        raise Conflict("Concurrent ingestion: retry this partition")

    def manifest(self, workspace, identifier=None, cutoff=None):
        if cutoff:
            choices = [
                m
                for m in self.control.list(workspace, "manifest")
                if m["created_at"] <= cutoff
            ]
            if identifier:
                choices = [m for m in choices if m["id"] == identifier]
            if not choices:
                raise CoverageError(
                    "No committed platform dataset existed at this timestamp"
                )
            identifier = choices[-1]["id"]
        elif identifier is None:
            try:
                identifier = self.control.get(workspace, "head", "current")["manifest"]
            except KeyError:
                raise CoverageError(
                    "No research data captured. Load the demo or ingest a series."
                ) from None
        self.control.get(workspace, "manifest", identifier)  # Authorization boundary.
        return identifier, self.objects.json(identifier)

    def catalog(self, workspace):
        try:
            _, manifest = self.manifest(workspace)
        except CoverageError:
            return []
        found = {}
        for s in sorted(
            manifest["snapshots"], key=lambda s: s["scope"]["information_date"]
        ):
            item = found.setdefault(
                s["series"]["id"], {**s["series"], "information_dates": [], "modes": []}
            )
            item.update(s["series"])
            item["information_dates"].append(s["scope"]["information_date"])
            item["modes"].append(s["scope"]["mode"])
        for s in found.values():
            s["information_dates"] = sorted(set(s["information_dates"]))
            s["modes"] = sorted(set(s["modes"]))
        return sorted(found.values(), key=lambda s: s["name"])

    def query(self, workspace, query: Query):
        identifier, manifest = self.manifest(
            workspace, query.dataset, query.as_of if query.basis == "platform" else None
        )
        candidates = [
            s for s in manifest["snapshots"] if s["series"]["id"] == query.series_id
        ]
        if query.basis == "source":
            candidates = [
                s
                for s in candidates
                if s["scope"]["mode"] == "source_vintage"
                and s["scope"]["information_date"] == query.as_of
            ]
        # Source snapshots have day precision. Require an actually captured date,
        # rather than pretending two checked dates establish the entire interval.
        covering = [
            s
            for s in candidates
            if s["scope"]["complete"]
            and s["scope"]["start"] <= str(query.start)
            and s["scope"]["end"] >= str(query.end)
        ]
        partial = False
        if not covering:
            if not query.allow_partial or not candidates:
                raise CoverageError(
                    "Historical coverage unavailable for this date/range; no current-data fallback"
                )
            covering, partial = candidates, True
        selected = max(reversed(covering), key=lambda s: s["scope"]["information_date"])
        self.objects.read(selected["part"])
        with duckdb.connect() as db:
            db.execute("SET memory_limit='1GB'")
            data = db.execute(
                "SELECT date,value,status,attributes FROM read_parquet(?) WHERE date >= ? AND date <= ? ORDER BY date LIMIT 100001",
                [
                    str(self.objects.path(selected["part"])),
                    str(query.start),
                    str(query.end),
                ],
            ).fetchall()
        if len(data) > 100000:
            raise ValueError("Query exceeds 100000 rows; narrow the range")
        return {
            "schema_version": "1.0",
            "series": selected["series"],
            "query": query.model_dump(mode="json"),
            "dataset_manifest": identifier,
            "coverage": {**selected["scope"], "complete_for_query": not partial},
            "evidence_ids": selected["captures"],
            "logical_hash": selected["logical_hash"],
            "data": [
                {"date": d, "value": v, "status": status, "attributes": json.loads(a)}
                for d, v, status, a in data
            ],
        }

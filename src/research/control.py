"""Transactional workspace state, portable between SQLite and PostgreSQL."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .contracts import now

metadata = MetaData()
records = Table(
    "research_records",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("kind", String(40), primary_key=True),
    Column("id", String(200), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("body", Text, nullable=False),
)


class Conflict(ValueError):
    pass


class Control:
    def __init__(self, root: Path, url: str | None = None):
        self.engine = create_engine(
            url or f'sqlite:///{root / "control.sqlite"}', pool_pre_ping=True
        )
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def settings(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=10000")

        metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        with self.engine.begin() as connection:
            yield connection

    def get(self, workspace, kind, identifier, connection=None):
        if connection is None:
            with self.engine.connect() as c:
                return self.get(workspace, kind, identifier, c)
        row = (
            connection.execute(
                select(records).where(
                    records.c.workspace == workspace,
                    records.c.kind == kind,
                    records.c.id == identifier,
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(identifier)
        return {
            "id": row["id"],
            "version": row["version"],
            "created_at": row["created_at"],
            **json.loads(row["body"]),
        }

    def list(self, workspace, kind, connection=None):
        if connection is None:
            with self.engine.connect() as c:
                return self.list(workspace, kind, c)
        rows = connection.execute(
            select(records)
            .where(records.c.workspace == workspace, records.c.kind == kind)
            .order_by(records.c.created_at, records.c.id)
        ).mappings()
        return [
            {
                "id": r["id"],
                "version": r["version"],
                "created_at": r["created_at"],
                **json.loads(r["body"]),
            }
            for r in rows
        ]

    def put(self, workspace, kind, identifier, body, expected=None, connection=None):
        if connection is None:
            with self.transaction() as c:
                return self.put(workspace, kind, identifier, body, expected, c)
        body = dict(body)
        for reserved in ("id", "version", "created_at"):
            body.pop(reserved, None)
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            if expected is None:
                connection.execute(
                    insert(records).values(
                        workspace=workspace,
                        kind=kind,
                        id=identifier,
                        version=1,
                        created_at=now(),
                        body=encoded,
                    )
                )
            else:
                result = connection.execute(
                    update(records)
                    .where(
                        records.c.workspace == workspace,
                        records.c.kind == kind,
                        records.c.id == identifier,
                        records.c.version == expected,
                    )
                    .values(body=encoded, version=expected + 1)
                )
                if result.rowcount != 1:
                    raise Conflict("Record changed; reload before retrying")
        except IntegrityError:
            raise Conflict("Record already exists") from None
        return self.get(workspace, kind, identifier, connection)

    def audit(self, workspace, actor, action, target, connection=None):
        return self.put(
            workspace,
            "audit",
            uuid.uuid4().hex,
            {"actor": actor, "action": action, "target": target},
            connection=connection,
        )

    def enqueue(self, workspace, key, kind, payload):
        try:
            return self.put(
                workspace,
                "job",
                key,
                {
                    "job_kind": kind,
                    "payload": payload,
                    "status": "planned",
                    "attempts": 0,
                    "due_at": now(),
                    "generation": 0,
                },
            )
        except Conflict:
            existing = self.get(workspace, "job", key)
            if existing["payload"] != payload or existing["job_kind"] != kind:
                raise Conflict("Idempotency key used for a different request")
            return existing

    def claim(self, workspace, worker, lease_seconds=300):
        current = now()
        for job in self.list(workspace, "job"):
            if not (
                (
                    job["status"] in ("planned", "retry_wait")
                    and job["due_at"] <= current
                )
                or (job["status"] == "running" and job["lease_until"] < current)
            ):
                continue
            if job["attempts"] >= 4:
                try:
                    self.put(
                        workspace,
                        "job",
                        job["id"],
                        {**job, "status": "exhausted"},
                        job["version"],
                    )
                except Conflict:
                    pass
                continue
            body = {
                **job,
                "status": "running",
                "worker": worker,
                "generation": job["generation"] + 1,
                "attempts": job["attempts"] + 1,
                "lease_until": (
                    datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                ).isoformat(),
            }
            try:
                return self.put(workspace, "job", job["id"], body, job["version"])
            except Conflict:
                continue
        return None

    def finish(self, workspace, job, status, result=None):
        current = self.get(workspace, "job", job["id"])
        if current["status"] != "running" or current["generation"] != job["generation"]:
            raise Conflict("Lease lost")
        if current["lease_until"] < now():
            raise Conflict("Lease expired")
        body = {**current, "status": status, "result": result}
        if status == "retry_wait":
            body["due_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=2 ** current["attempts"])
            ).isoformat()
        return self.put(workspace, "job", job["id"], body, current["version"])

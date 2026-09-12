"""Fence final commits by the worker's current lease in the same transaction."""

from contextvars import ContextVar

from sqlalchemy import update

from .contracts import now
from .control import Conflict, records

lease = ContextVar("research_lease", default=None)


def guard(control, workspace, tx):
    job = lease.get()
    if job is None:
        return
    current = control.get(workspace, "job", job["id"], tx)
    if (
        current["generation"] != job["generation"]
        or current["status"] != "running"
        or current["lease_until"] < now()
    ):
        raise Conflict("Lease lost before commit")
    # A conditional write locks the job row through the manifest/run commit.
    result = tx.execute(
        update(records)
        .where(
            records.c.workspace == workspace,
            records.c.kind == "job",
            records.c.id == job["id"],
            records.c.version == current["version"],
        )
        .values(version=current["version"])
    )
    if result.rowcount != 1:
        raise Conflict("Lease changed before commit")

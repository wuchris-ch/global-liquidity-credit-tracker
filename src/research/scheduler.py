"""Reconcile missed collection slots with persisted, idempotent partition jobs."""

from datetime import datetime, timedelta, timezone

from pydantic import Field

from .contracts import Contract, Scope, Series, now
from .control import Conflict
from .storage import canonical, digest


class Schedule(Contract):
    series: Series
    start: str
    interval_hours: int = Field(default=12, ge=1, le=8760)
    enabled: bool = True


def reconcile(store, workspace):
    queued = []
    for schedule in store.control.list(workspace, "schedule"):
        if not schedule["enabled"] or schedule.get("next_due_at", "") > now():
            continue
        spec = Schedule.model_validate({k: schedule[k] for k in Schedule.model_fields})
        current = datetime.now(timezone.utc)
        day = current.date()
        scope = Scope(
            start=spec.start,
            end=day,
            information_date=day,
            mode=(
                "source_vintage" if spec.series.source == "fred" else "forward_capture"
            ),
        )
        slot = int(current.timestamp() // (spec.interval_hours * 3600))
        key = digest(canonical({"schedule": schedule["id"], "slot": slot}))
        # Enqueue before advancing checkpoint. A crash reuses the same key.
        job = store.control.enqueue(
            workspace,
            key,
            "ingest",
            {
                "series": spec.series.model_dump(mode="json"),
                "scope": scope.model_dump(mode="json"),
            },
        )
        try:
            store.control.put(
                workspace,
                "schedule",
                schedule["id"],
                {
                    **schedule,
                    "last_job": job["id"],
                    "last_reconciled_at": now(),
                    "next_due_at": (
                        current + timedelta(hours=spec.interval_hours)
                    ).isoformat(),
                },
                schedule["version"],
            )
        except Conflict:
            pass
        queued.append(key)
    return queued

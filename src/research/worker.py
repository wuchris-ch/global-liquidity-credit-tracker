"""Restartable worker with fenced, idempotent effects and bounded retries."""

import logging
import uuid

from .contracts import Scope, Series
from .control import Conflict
from .fencing import lease
from .ingestion import TransientSourceError, source_snapshot
from .service import Research


def tick(store, workspace="personal"):
    job = store.control.claim(workspace, uuid.uuid4().hex, lease_seconds=900)
    if not job:
        return None

    def finish(status, result):
        try:
            return store.control.finish(workspace, job, status, result)
        except Conflict:
            return None

    token = lease.set(job)
    try:
        if job["job_kind"] == "analysis":
            result = {
                "run_id": Research(store).execute(workspace, job["payload"])["id"]
            }
        elif job["job_kind"] == "ingest":
            payload = job["payload"]
            result = {
                "manifest": source_snapshot(
                    store,
                    workspace,
                    Series.model_validate(payload["series"]),
                    Scope.model_validate(payload["scope"]),
                )
            }
        elif job["job_kind"] == "model":
            from .models import run_glci

            result = {"model_run_id": run_glci(store, workspace, job["payload"])["id"]}
        else:
            raise ValueError("Unknown job kind")
        return finish("succeeded", result)
    except TransientSourceError:
        return finish("retry_wait", {"error": "Source temporarily unavailable"})
    except Conflict:
        return None
    except (ValueError, KeyError, PermissionError) as exc:
        store.control.audit(workspace, "worker", "job_quarantined", job["id"])
        return finish("quarantined", {"error": str(exc)[:500]})
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).error(
            "Research job %s failed (%s)", job["id"], type(exc).__name__
        )
        return finish(
            "retry_wait", {"error": "Internal worker error; inspect local diagnostics"}
        )
    finally:
        lease.reset(token)

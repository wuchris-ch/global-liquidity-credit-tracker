# ruff: noqa: B008
"""Read-only queries and explicit mutations for the research workspace."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field

from .assistant import answer
from .auth import Auth, require_editor
from .contracts import Contract, Note, Query, Recipe, Release, Scope, Series, Watchlist
from .control import Conflict
from .models import ModelRequest
from .outcomes import Outcome, outcome_summary, record_outcome
from .scheduler import Schedule, reconcile
from .service import Research
from .storage import CoverageError, ResearchStore, canonical, digest
from .worker import tick


class RunRequest(Contract):
    refresh: bool = False


class PublicationRequest(Contract):
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class ComparisonRequest(Contract):
    left: str = Field(pattern=r"^[a-f0-9]{64}$")
    right: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssistantRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)
    run_ids: list[str] = Field(default_factory=list, max_length=2)


class IngestRequest(Contract):
    series: Series
    scope: Scope


def create_app(root=None, database_url=None, start_worker=True):
    store = ResearchStore(
        root or os.getenv("RESEARCH_DATA_PATH", "data/research"),
        database_url or os.getenv("RESEARCH_DATABASE_URL"),
    )
    service = Research(store)
    auth = Auth(store.control)

    @asynccontextmanager
    async def lifespan(app):
        async def work():
            while True:
                for workspace in os.getenv("RESEARCH_WORKSPACES", "personal").split(
                    ","
                ):
                    await asyncio.to_thread(reconcile, store, workspace)
                    await asyncio.to_thread(tick, store, workspace)
                await asyncio.sleep(1)

        task = (
            asyncio.create_task(work())
            if start_worker and os.getenv("RESEARCH_WORKER", "1") == "1"
            else None
        )
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Global Macro Research API", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    origins = os.getenv(
        "RESEARCH_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Workspace-ID",
            "Idempotency-Key",
            "If-Match",
        ],
        expose_headers=["ETag"],
    )

    @app.middleware("http")
    async def bounded_request(request, call_next):
        if request.method in ("POST", "PUT"):
            chunks = []
            length = 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 1024 * 1024:
                    return Response("Request exceeds 1MB", status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(CoverageError)
    async def coverage_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"code": "HISTORICAL_COVERAGE_UNAVAILABLE", "detail": str(exc)},
            status_code=422,
        )

    @app.exception_handler(Conflict)
    async def conflict_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "Resource not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=403)

    principal = auth.principal
    prefix = "/api/v1/research"

    @app.get("/health")
    def health():
        return {"status": "ok", "schema_version": "1.0"}

    @app.get(prefix + "/session")
    def session(p=Depends(principal)):
        return {
            "workspace": p.workspace,
            "subject": p.subject,
            "role": p.role,
            "auth_mode": auth.mode,
        }

    @app.get(prefix + "/series")
    def catalog(q: str = "", source: str = "", country: str = "", p=Depends(principal)):
        rows = store.catalog(p.workspace)
        return [
            r
            for r in rows
            if q.lower() in (r["id"] + " " + r["name"]).lower()
            and (not source or r["source"] == source)
            and (not country or r["country"] == country)
        ]

    @app.get(prefix + "/series/{identifier}/observations")
    def observations(
        identifier: str,
        start: str,
        end: str,
        as_of: str,
        basis: Literal["source", "platform"] = "source",
        dataset: str | None = None,
        allow_partial: bool = False,
        p=Depends(principal),
    ):
        return store.query(
            p.workspace,
            Query(
                series_id=identifier,
                start=start,
                end=end,
                as_of=as_of,
                basis=basis,
                dataset=dataset,
                allow_partial=allow_partial,
            ),
        )

    @app.get(prefix + "/series/{identifier}/vintages")
    def vintages(identifier: str, p=Depends(principal)):
        _, m = store.manifest(p.workspace)
        return [
            {
                "scope": s["scope"],
                "logical_hash": s["logical_hash"],
                "evidence_ids": s["captures"],
            }
            for s in m["snapshots"]
            if s["series"]["id"] == identifier
        ]

    @app.post(prefix + "/demo")
    def demo(p=Depends(principal)):
        require_editor(p)
        from .ingestion import load_demo

        load_demo(store, p.workspace)
        return {
            "status": "ready",
            "message": "Imported two authentic archived GDP estimates. No historical platform publication was created.",
        }

    @app.post(prefix + "/ingestions", status_code=202)
    def ingest(
        request: IngestRequest,
        p=Depends(principal),
        idempotency_key: str | None = Header(default=None),
    ):
        require_editor(p)
        if (
            len(
                [
                    j
                    for j in store.control.list(p.workspace, "job")
                    if j["status"] in ("planned", "running", "retry_wait")
                ]
            )
            >= 100
        ):
            raise HTTPException(
                429, "Workspace job quota reached", headers={"Retry-After": "60"}
            )
        return store.control.enqueue(
            p.workspace,
            idempotency_key or digest(canonical(request.model_dump(mode="json"))),
            "ingest",
            request.model_dump(mode="json"),
        )

    @app.get(prefix + "/analyses")
    def analyses(p=Depends(principal)):
        return store.control.list(p.workspace, "analysis")

    @app.post(prefix + "/analyses", status_code=201)
    def save(
        recipe: Recipe,
        p=Depends(principal),
        idempotency_key: str | None = Header(default=None),
    ):
        require_editor(p)
        return service.save_recipe(p.workspace, p.subject, recipe, idempotency_key)

    @app.post(prefix + "/analyses/{identifier}/runs", status_code=202)
    def run(
        identifier: str,
        request: RunRequest,
        p=Depends(principal),
        idempotency_key: str | None = Header(default=None),
    ):
        require_editor(p)
        return service.queue_run(
            p.workspace, p.subject, identifier, idempotency_key, request.refresh
        )

    @app.get(prefix + "/jobs")
    def jobs(p=Depends(principal)):
        return store.control.list(p.workspace, "job")[-100:]

    @app.get(prefix + "/jobs/{identifier}")
    def job(identifier: str, p=Depends(principal)):
        return store.control.get(p.workspace, "job", identifier)

    @app.post(prefix + "/jobs/{identifier}/cancel")
    def cancel(identifier: str, p=Depends(principal)):
        require_editor(p)
        with store.control.transaction() as tx:
            job = store.control.get(p.workspace, "job", identifier, tx)
            if job["status"] not in ("planned", "retry_wait", "running"):
                return job
            saved = store.control.put(
                p.workspace,
                "job",
                identifier,
                {**job, "status": "cancelled"},
                job["version"],
                tx,
            )
            store.control.audit(p.workspace, p.subject, "cancel_job", identifier, tx)
            return saved

    @app.get(prefix + "/runs")
    def runs(p=Depends(principal)):
        return [
            {
                "id": r["id"],
                "title": r["recipe"]["title"],
                "computed_at": r["computed_at"],
                "recipe": r["recipe"],
                "result": r["result"],
            }
            for r in store.control.list(p.workspace, "run")[-100:]
        ]

    @app.get(prefix + "/runs/{identifier}")
    def saved_run(identifier: str, p=Depends(principal)):
        return service.get_run(p.workspace, identifier)

    @app.get(prefix + "/runs/{identifier}/export")
    def export(
        identifier: str,
        format: Literal["csv", "json", "parquet", "html", "bundle"] = "json",
        p=Depends(principal),
    ):
        data, mime = service.export(p.workspace, identifier, format)
        return Response(
            data,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="analysis-{identifier[:12]}.{format if format!="bundle" else "json"}"',
                "ETag": f'"{digest(data)}"',
            },
        )

    @app.post(prefix + "/comparisons")
    def comparisons(request: ComparisonRequest, p=Depends(principal)):
        return service.comparison(p.workspace, request.left, request.right)

    @app.get(prefix + "/changes")
    def changes(p=Depends(principal)):
        return service.changes(p.workspace)

    @app.get(prefix + "/annotations")
    def notes(p=Depends(principal)):
        return store.control.list(p.workspace, "note")

    @app.post(prefix + "/annotations", status_code=201)
    def annotate(note: Note, p=Depends(principal)):
        require_editor(p)
        service.get_run(p.workspace, note.run_id)
        import uuid

        with store.control.transaction() as tx:
            result = store.control.put(
                p.workspace,
                "note",
                uuid.uuid4().hex,
                {**note.model_dump(), "author": p.subject},
                connection=tx,
            )
            store.control.audit(p.workspace, p.subject, "annotate", note.run_id, tx)
        return result

    @app.get(prefix + "/watchlists")
    def watches(p=Depends(principal)):
        return store.control.list(p.workspace, "watchlist")

    @app.put(prefix + "/watchlists/{identifier}")
    def watch(
        identifier: str,
        watchlist: Watchlist,
        p=Depends(principal),
        if_match: int | None = Header(default=None),
    ):
        require_editor(p)
        return store.control.put(
            p.workspace, "watchlist", identifier, watchlist.model_dump(), if_match
        )

    @app.get(prefix + "/releases")
    def releases(p=Depends(principal)):
        rows = store.control.list(p.workspace, "release")
        current = datetime.now(timezone.utc)
        return [
            {
                **r,
                "late_seconds": (
                    max(
                        0,
                        (
                            current - datetime.fromisoformat(r["expected_at"])
                        ).total_seconds(),
                    )
                    if r["state"] == "scheduled" and not r.get("observed_at")
                    else 0
                ),
            }
            for r in rows
        ]

    @app.put(prefix + "/releases/{identifier}")
    def release(
        identifier: str,
        release: Release,
        p=Depends(principal),
        if_match: int | None = Header(default=None),
    ):
        require_editor(p)
        if identifier != release.id:
            raise ValueError("Release identity mismatch")
        return store.control.put(
            p.workspace, "release", identifier, release.model_dump(), if_match
        )

    @app.post(prefix + "/publications", status_code=201)
    def publish(request: PublicationRequest, p=Depends(principal)):
        require_editor(p)
        report, _ = service.export(p.workspace, request.run_id, "html")
        artifact = store.objects.write(report)
        import uuid

        with store.control.transaction() as tx:
            saved = store.control.put(
                p.workspace,
                "publication",
                uuid.uuid4().hex,
                {
                    "run_id": request.run_id,
                    "report": artifact,
                    "visibility": "workspace",
                    "actor": p.subject,
                },
                connection=tx,
            )
            store.control.audit(
                p.workspace, p.subject, "freeze_private_report", saved["id"], tx
            )
        return saved

    @app.get(prefix + "/publications/{identifier}")
    def publication(identifier: str, p=Depends(principal)):
        return store.control.get(p.workspace, "publication", identifier)

    @app.get(prefix + "/evidence/{identifier}")
    def evidence(identifier: str, p=Depends(principal)):
        cap = store.control.get(p.workspace, "capture", identifier)
        return {k: v for k, v in cap.items() if k != "body_base64"}

    @app.post(prefix + "/assistant")
    def assistant(request: AssistantRequest, p=Depends(principal)):
        return answer(store, p.workspace, request.question, request.run_ids)

    @app.get(prefix + "/audit")
    def audit(p=Depends(principal)):
        if p.role != "owner":
            raise HTTPException(403, "Owner role required")
        return store.control.list(p.workspace, "audit")[-200:]

    @app.post(prefix + "/models", status_code=202)
    def model_run(request: ModelRequest, p=Depends(principal)):
        require_editor(p)
        for q in request.inputs.values():
            q.dataset = store.manifest(
                p.workspace, q.dataset, q.as_of if q.basis == "platform" else None
            )[0]
        import uuid

        return store.control.enqueue(
            p.workspace, uuid.uuid4().hex, "model", request.model_dump(mode="json")
        )

    @app.get(prefix + "/models/{identifier}")
    def model_result(identifier: str, p=Depends(principal)):
        return store.control.get(p.workspace, "model_run", identifier)

    @app.get(prefix + "/schedules")
    def schedules(p=Depends(principal)):
        return store.control.list(p.workspace, "schedule")

    @app.put(prefix + "/schedules/{identifier}")
    def schedule(
        identifier: str,
        spec: Schedule,
        p=Depends(principal),
        if_match: int | None = Header(default=None),
    ):
        require_editor(p)
        return store.control.put(
            p.workspace, "schedule", identifier, spec.model_dump(mode="json"), if_match
        )

    @app.post(prefix + "/outcomes")
    def outcome(spec: Outcome, p=Depends(principal)):
        require_editor(p)
        return record_outcome(store, p.workspace, spec)

    @app.get(prefix + "/outcomes")
    def outcomes(p=Depends(principal)):
        return outcome_summary(store, p.workspace)

    @app.get(prefix + "/workspace")
    def workspace_snapshot(p=Depends(principal)):
        return {
            "session": session(p),
            "series": catalog(p=p),
            "runs": runs(p),
            "jobs": jobs(p),
            "changes": changes(p),
            "annotations": notes(p),
            "watchlists": watches(p),
            "releases": releases(p),
        }

    return app

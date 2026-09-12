"""Local setup, acquisition, replay, worker and recovery commands."""

import argparse
import json
import os
import time
from pathlib import Path

from .contracts import Query, Recipe, Scope, Series
from .ingestion import fred_vintage_dates, load_demo
from .operations import backup, restore, retention_plan
from .scheduler import reconcile
from .service import Research, replay
from .storage import ResearchStore, canonical, digest
from .worker import tick


def main():
    parser = argparse.ArgumentParser(description="Global macro research workbench")
    parser.add_argument(
        "--data", default=os.getenv("RESEARCH_DATA_PATH", "data/research")
    )
    parser.add_argument("--workspace", default="personal")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("catalog")
    sub.add_parser("retention")
    sub.add_parser("evaluate")
    for name in ("replay", "backup", "restore", "ingest"):
        p = sub.add_parser(name)
        p.add_argument("path")
    backfill = sub.add_parser("backfill")
    backfill.add_argument("path")
    backfill.add_argument("--from-date", required=True)
    backfill.add_argument("--to-date", required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    member = sub.add_parser("member")
    member.add_argument("subject")
    member.add_argument(
        "--role", choices=["owner", "editor", "viewer"], default="viewer"
    )
    member.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    if args.command == "evaluate":
        from .evaluation import evaluate_assistant

        print(json.dumps(evaluate_assistant(), indent=2))
        return
    if args.command == "replay":
        print(json.dumps(replay(json.loads(Path(args.path).read_text())), indent=2))
        return
    store = ResearchStore(args.data, os.getenv("RESEARCH_DATABASE_URL"))
    workspace = args.workspace
    if args.command == "demo":
        load_demo(store, workspace)
        service = Research(store)
        runs = []
        for d in ("2024-04-25", "2024-05-30"):
            recipe = Recipe(
                title=f"US growth revision notebook | {d}",
                queries=[
                    Query(
                        series_id="fred:A191RL1Q225SBEA",
                        start="2024-01-01",
                        end="2024-01-01",
                        as_of=d,
                    )
                ],
                threshold="1.5",
            )
            saved = service.save_recipe(workspace, "local-user", recipe, "gdp-" + d)
            job = service.queue_run(workspace, "local-user", saved["id"])
            while store.control.get(workspace, "job", job["id"])["status"] == "planned":
                tick(store, workspace)
            completed = store.control.get(workspace, "job", job["id"])
            if completed["status"] != "succeeded":
                raise ValueError("Demo job did not succeed")
            run = service.get_run(workspace, completed["result"]["run_id"])
            runs.append(run["id"])
        print(json.dumps(service.comparison(workspace, *runs), indent=2))
        print(
            "No recorded platform publication for April 2024. Demo analyses were created now."
        )
    elif args.command == "catalog":
        print(json.dumps(store.catalog(workspace), indent=2))
    elif args.command in ("ingest", "backfill"):
        payload = json.loads(Path(args.path).read_text())
        series = Series.model_validate(payload["series"])
        scope = Scope.model_validate(payload["scope"])
        dates = [str(scope.information_date)]
        if args.command == "backfill":
            if series.source != "fred":
                raise ValueError(
                    "Historical enumeration currently requires FRED; other sources are forward captures"
                )
            dates = fred_vintage_dates(
                store, workspace, series.source_id, args.from_date, args.to_date
            )
        for d in dates:
            request = {
                "series": series.model_dump(mode="json"),
                "scope": {**scope.model_dump(mode="json"), "information_date": d},
            }
            store.control.enqueue(
                workspace, digest(canonical(request)), "ingest", request
            )
        print(json.dumps({"queued_partitions": len(dates)}))
    elif args.command == "worker":
        while True:
            reconcile(store, workspace)
            result = tick(store, workspace)
            if result:
                print(json.dumps(result))
            if args.once:
                break
            if not result:
                time.sleep(2)
    elif args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port)
    elif args.command == "backup":
        print(json.dumps(backup(store, args.path)))
    elif args.command == "restore":
        print(json.dumps(restore(store, args.path)))
    elif args.command == "retention":
        print(json.dumps(retention_plan(store)))
    elif args.command == "member":
        try:
            version = store.control.get(workspace, "member", args.subject)["version"]
        except KeyError:
            version = None
        store.control.put(
            workspace,
            "member",
            args.subject,
            {"role": args.role, "active": not args.revoke},
            version,
        )
        store.control.audit(workspace, "local-admin", "change_membership", args.subject)
        print("Membership updated")


if __name__ == "__main__":
    main()

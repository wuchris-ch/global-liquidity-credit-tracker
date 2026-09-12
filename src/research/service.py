"""Application use cases shared by HTTP, CLI and the bounded assistant."""

from __future__ import annotations

import csv
import html
import io
import platform
import sys
import uuid
from pathlib import Path

from .calculations import calculate, compare
from .contracts import Recipe, now
from .control import Conflict
from .storage import ResearchStore, canonical, digest


def environment():
    from importlib.metadata import distributions

    root = Path(__file__).resolve().parents[2]
    files = {
        str(p.relative_to(root)): digest(p.read_bytes())
        for folder in ("src", "config")
        for p in (root / folder).rglob("*")
        if p.suffix in (".py", ".yml")
    }
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": sorted(
            (d.metadata["Name"], d.version)
            for d in distributions()
            if d.metadata["Name"]
        ),
        "code": files,
        "lock": (
            digest((root / "uv.lock").read_bytes())
            if (root / "uv.lock").exists()
            else None
        ),
        "calculator": digest(Path(__file__).with_name("calculations.py").read_bytes()),
    }


class Research:
    def __init__(self, store: ResearchStore):
        self.store, self.control = store, store.control

    def save_recipe(self, workspace, actor, recipe: Recipe, key=None):
        body = {"recipe": recipe.model_dump(mode="json"), "author": actor}
        identifier = key or uuid.uuid4().hex
        try:
            with self.control.transaction() as tx:
                saved = self.control.put(
                    workspace, "analysis", identifier, body, connection=tx
                )
                self.control.audit(workspace, actor, "save_analysis", identifier, tx)
            return saved
        except Conflict:
            saved = self.control.get(workspace, "analysis", identifier)
            if saved["recipe"] != body["recipe"]:
                raise Conflict("Idempotency key reused for a different recipe")
            return saved

    def queue_run(self, workspace, actor, analysis_id, key=None, refresh=False):
        if key:
            try:
                existing = self.control.get(workspace, "job", key)
            except KeyError:
                existing = None
            if existing:
                prior = existing["payload"]
                if (
                    existing["job_kind"] == "analysis"
                    and prior["analysis_id"] == analysis_id
                    and prior["actor"] == actor
                    and prior.get("request", {}) == {"refresh": refresh}
                ):
                    return existing
                raise Conflict("Idempotency key reused for a different run request")
        analysis = self.control.get(workspace, "analysis", analysis_id)
        recipe = Recipe.model_validate(analysis["recipe"])
        # Resolve a manifest once, before work is enqueued. A retry never reads a new head.
        for query in recipe.queries:
            if refresh:
                query.dataset = None
            manifest, _ = self.store.manifest(
                workspace,
                query.dataset,
                query.as_of if query.basis == "platform" else None,
            )
            query.dataset = manifest
        payload = {
            "analysis_id": analysis_id,
            "recipe": recipe.model_dump(mode="json"),
            "actor": actor,
            "request": {"refresh": refresh},
        }
        return self.control.enqueue(
            workspace, key or uuid.uuid4().hex, "analysis", payload
        )

    def execute(self, workspace, payload):
        recipe = Recipe.model_validate(payload["recipe"])
        inputs = [self.store.query(workspace, q) for q in recipe.queries]
        result = calculate(recipe, inputs)
        env = environment()
        identity = {
            "analysis_id": payload["analysis_id"],
            "recipe": recipe.model_dump(mode="json"),
            "inputs": inputs,
            "environment": env,
        }
        run_id = digest(canonical(identity))
        record = {
            **identity,
            "result": result,
            "analysis_id": payload["analysis_id"],
            "computed_at": now(),
            "logical_result_hash": digest(canonical(result)),
            "historical_platform_publication": False,
        }
        artifact = self.store.objects.write(canonical(record))
        try:
            with self.control.transaction() as tx:
                __import__("src.research.fencing", fromlist=["guard"]).guard(
                    self.control, workspace, tx
                )
                self.control.put(
                    workspace,
                    "run",
                    run_id,
                    {"artifact": artifact, **record},
                    connection=tx,
                )
                self.control.audit(
                    workspace, payload["actor"], "compute_analysis", run_id, tx
                )
        except Conflict:
            pass
        return self.control.get(workspace, "run", run_id)

    def get_run(self, workspace, run_id):
        return self.control.get(workspace, "run", run_id)

    def comparison(self, workspace, left, right):
        return compare(self.get_run(workspace, left), self.get_run(workspace, right))

    def changes(self, workspace):
        try:
            head, manifest = self.store.manifest(workspace)
        except ValueError:
            return []
        results = []
        for run in self.control.list(workspace, "run"):
            changed = []
            for inp in run["inputs"]:
                same = [
                    s
                    for s in manifest["snapshots"]
                    if s["series"]["id"] == inp["series"]["id"]
                ]
                same.sort(key=lambda s: s["scope"]["information_date"])
                if same and same[-1]["logical_hash"] != inp["logical_hash"]:
                    changed.append(
                        {
                            "series_id": inp["series"]["id"],
                            "saved_information_date": inp["coverage"][
                                "information_date"
                            ],
                            "latest_information_date": same[-1]["scope"][
                                "information_date"
                            ],
                        }
                    )
            if changed:
                results.append(
                    {
                        "run_id": run["id"],
                        "title": run["recipe"]["title"],
                        "changes": changed,
                        "latest_manifest": head,
                    }
                )
        return results

    def bundle(self, workspace, run_id):
        run = self.get_run(workspace, run_id)
        if any(i["series"]["redistribution"] != "allowed" for i in run["inputs"]):
            raise PermissionError(
                "Export requires reviewed redistribution rights for all inputs"
            )
        captures = {}
        for inp in run["inputs"]:
            for cap_id in inp["evidence_ids"]:
                cap = self.control.get(workspace, "capture", cap_id)
                import base64

                captures[cap_id] = {
                    **cap,
                    "body_base64": base64.b64encode(
                        self.store.objects.read(cap["body"])
                    ).decode(),
                }
        bundle = {
            "schema_version": "1.0",
            "recipe": run["recipe"],
            "inputs": run["inputs"],
            "result": run["result"],
            "environment": run["environment"],
            "logical_result_hash": run["logical_result_hash"],
            "captures": captures,
        }
        return {**bundle, "bundle_hash": digest(canonical(bundle))}

    def export(self, workspace, run_id, format):
        bundle = self.bundle(workspace, run_id)
        if format == "json" or format == "bundle":
            return canonical(bundle), "application/json"
        if format == "html":
            title = html.escape(bundle["recipe"]["title"])
            rows = "".join(
                "<tr>"
                + "".join(
                    "<td>" + html.escape(str(row[k])) + "</td>"
                    for k in ("date", "value", "threshold_met")
                )
                + "</tr>"
                for row in bundle["result"]["data"]
            )
            sources = "".join(
                "<li>"
                + html.escape(i["series"]["name"])
                + " | "
                + html.escape(i["query"]["as_of"])
                + " | "
                + html.escape(i["dataset_manifest"])
                + "</li>"
                for i in bundle["inputs"]
            )
            page = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title><style>body{{max-width:900px;margin:50px auto;font:17px system-ui;padding:20px}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}code{{overflow-wrap:anywhere}}</style><h1>{title}</h1><p>Frozen analysis. Unit: {html.escape(bundle["result"]["unit"])}. No generated interpretation.</p><table><thead><tr><th>Period</th><th>Value</th><th>Threshold met</th></tr></thead><tbody>{rows}</tbody></table><h2>Inputs and data versions</h2><ul>{sources}</ul><p>Result hash: <code>{bundle["logical_result_hash"]}</code></p></html>'
            return page.encode(), "text/html"
        output_rows = [
            {
                **r,
                "unit": bundle["result"]["unit"],
                "run_id": run_id,
                "manifest": ",".join(i["dataset_manifest"] for i in bundle["inputs"]),
            }
            for r in bundle["result"]["data"]
        ]
        if format == "parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq

            table = pa.Table.from_pylist(output_rows)
            table = table.replace_schema_metadata(
                {
                    b"research_manifest": canonical(
                        {k: v for k, v in bundle.items() if k != "captures"}
                    )
                }
            )
            buffer = pa.BufferOutputStream()
            pq.write_table(table, buffer)
            return buffer.getvalue().to_pybytes(), "application/vnd.apache.parquet"
        if format == "csv":
            stream = io.StringIO()
            fields = ["date", "value", "threshold_met", "unit", "run_id", "manifest"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in output_rows:
                # Numeric values originate in Decimal, not user strings.
                for key in ("unit", "manifest"):
                    if (
                        str(row[key])
                        .lstrip()
                        .startswith(("=", "+", "-", "@", "\t", "\r"))
                    ):
                        row[key] = "'" + row[key]
                writer.writerow(row)
            return stream.getvalue().encode(), "text/csv"
        raise ValueError("Unsupported export format")


def replay(bundle):
    unsigned = {k: v for k, v in bundle.items() if k != "bundle_hash"}
    if digest(canonical(unsigned)) != bundle["bundle_hash"]:
        raise ValueError("Bundle integrity failure")
    if bundle["environment"]["calculator"] != digest(
        Path(__file__).with_name("calculations.py").read_bytes()
    ):
        raise ValueError(
            "Calculator version differs; restore the recorded implementation before replay"
        )
    import base64

    for cap in bundle["captures"].values():
        if digest(base64.b64decode(cap["body_base64"])) != cap["body"]:
            raise ValueError("Capture integrity failure")
    result = calculate(Recipe.model_validate(bundle["recipe"]), bundle["inputs"])
    if digest(canonical(result)) != bundle["logical_result_hash"]:
        raise ValueError("Replay differs from saved result")
    return result

"""Measure the real leased-worker path on captured public data, without network."""

import argparse
import json
import math
import os
import platform
import resource
import sys
import tempfile
import time
from statistics import median
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.research.contracts import Query, Recipe, now
from src.research.release_lab import capture_release
from src.research.release_sources import WORKSPACE
from src.research.revision_study import previous_month
from src.research.service import Research
from src.research.storage import ResearchStore, digest
from src.research.worker import tick


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default="data/release-lab-benchmark.json")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("Choose 1 to 8 workers")
    root = Path(__file__).resolve().parents[1]
    bundle = json.loads((root / "frontend/src/lib/release-study.json").read_text())
    # The actual source transport never runs; the credential is a non-secret sentinel.
    os.environ["FRED_API_KEY"] = "offline-capture-replay"
    evidence = list(bundle["evidence"].values())
    with tempfile.TemporaryDirectory(prefix="release-benchmark-") as temporary:
        store = ResearchStore(temporary)

        class Tape:
            def get(self, url, params):
                safe = {k: v for k, v in params.items() if k != "api_key"}
                cap = next(
                    e
                    for e in evidence
                    if e["source_url"] == url
                    and all(str(e["params"].get(k)) == str(v) for k, v in safe.items())
                )
                record = store.capture(WORKSPACE, url, safe, cap["body"].encode())
                return json.loads(cap["body"]), record["id"]

        cohort = bundle["study"]["rows"][:12]
        dates = sorted({r["initial_date"] for r in cohort} | {bundle["as_of"]})
        for day in dates:
            capture_release(store, "PAYEMS", day, Tape())
        research = Research(store)
        expected = {}
        for row in cohort:
            for version, day in (
                ("initial", row["initial_date"]),
                ("revised", row["revised_date"]),
            ):
                recipe = Recipe(
                    title=f"{row['period']} {version}",
                    operation="difference",
                    queries=[
                        Query(
                            series_id="PAYEMS",
                            start=previous_month(row["period"]),
                            end=row["period"],
                            as_of=day,
                        )
                    ],
                )
                saved = research.save_recipe(WORKSPACE, "release-benchmark", recipe)
                job = research.queue_run(WORKSPACE, "release-benchmark", saved["id"])
                expected[job["id"]] = row[version]
        before = resource.getrusage(resource.RUSAGE_SELF)
        start = time.perf_counter()

        def worker(_):
            timings = []
            while True:
                began = time.perf_counter()
                job = tick(store, WORKSPACE)
                elapsed = time.perf_counter() - began
                if job is None:
                    break
                if job["status"] != "succeeded":
                    raise ValueError("A benchmark job did not complete")
                run = research.get_run(WORKSPACE, job["result"]["run_id"])
                if run["result"]["data"][-1]["value"] != expected[job["id"]]:
                    raise ValueError(
                        "Concurrent result differs from captured source result"
                    )
                timings.append(elapsed)
            return timings

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            timings = [
                v
                for worker_times in pool.map(worker, range(args.workers))
                for v in worker_times
            ]
        elapsed = time.perf_counter() - start
        after = resource.getrusage(resource.RUSAGE_SELF)
        assert len(timings) == len(expected) == 24
        ordered = sorted(timings)
        receipt = dict(
            measured_at=now(),
            environment=dict(
                python=sys.version.split()[0],
                os=platform.system(),
                os_release=platform.release(),
                architecture=platform.machine(),
                logical_cpus=os.cpu_count(),
            ),
            workload=dict(
                workers=args.workers,
                jobs=24,
                source_snapshots=len(dates),
                observations_per_run=2,
                input_series="PAYEMS",
                study_periods="2023-01 through 2023-12",
                network_requests=0,
                path="leased claim, pinned DuckDB query, Decimal calculation, immutable result and fenced commit",
                setup_excluded=True,
                queue_wait_included_in_per_job=False,
            ),
            elapsed_seconds=elapsed,
            jobs_per_second=24 / elapsed,
            job_latency_seconds=dict(
                p50=median(ordered),
                p95=ordered[math.ceil(0.95 * len(ordered)) - 1],
                maximum=max(ordered),
            ),
            cpu_seconds=(after.ru_utime - before.ru_utime)
            + (after.ru_stime - before.ru_stime),
            process_peak_rss_bytes=int(
                after.ru_maxrss * (1 if platform.system() == "Darwin" else 1024)
            ),
            verified_results=24,
            failed_jobs=0,
            publication=bundle["id"],
            code={
                p: digest((root / p).read_bytes())
                for p in (
                    "src/research/worker.py",
                    "src/research/storage.py",
                    "src/research/calculations.py",
                    "scripts/benchmark_release_lab.py",
                )
            },
            lock_sha256=digest((root / "uv.lock").read_bytes()),
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt))


if __name__ == "__main__":
    main()

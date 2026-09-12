"""Reproducible synthetic query workload. Does not contact upstream sources."""

import argparse
import json
import platform
import resource
import statistics
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.research.contracts import Observation, Query, Scope, Series
from src.research.service import environment
from src.research.storage import ResearchStore, canonical, digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--series", type=int, default=100)
    p.add_argument("--rows", type=int, default=10000)
    p.add_argument("--queries", type=int, default=100)
    p.add_argument("--output", default="data/research-benchmark.json")
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as root:
        store = ResearchStore(root)
        start = date(1990, 1, 1)
        end = start + timedelta(days=a.rows - 1)
        scope = Scope(
            start=start, end=end, information_date="2024-04-25", mode="source_vintage"
        )
        started = time.perf_counter()
        for i in range(a.series):
            series = Series(
                id=f"fixture:{i}",
                name=f"Synthetic {i}",
                source="fixture",
                source_id=str(i),
                country="USA",
                unit="index",
                frequency="daily",
            )
            rows = [
                Observation(date=start + timedelta(days=j), value=str(i + j / 100))
                for j in range(a.rows)
            ]
            cap = store.capture(
                "personal",
                "https://example.invalid/synthetic",
                {},
                canonical({"series": i, "generator": "i+j/100", "rows": a.rows}),
            )
            store.ingest("personal", series, scope, rows, [cap["id"]])
        ingest = time.perf_counter() - started
        latencies = []
        hashes = []
        for i in range(a.queries):
            q = Query(
                series_id=f"fixture:{i%a.series}",
                start=end - timedelta(days=364),
                end=end,
                as_of="2024-04-25",
            )
            started = time.perf_counter()
            result = store.query("personal", q)
            latencies.append((time.perf_counter() - started) * 1000)
            assert len(result["data"]) == 365
            assert result["data"][-1]["value"] == str(i % a.series + (a.rows - 1) / 100)
            hashes.append(digest(canonical(result["data"])))
        report = {
            "measured_at": str(datetime.now(timezone.utc).date()),
            "platform": platform.platform(),
            "rows": a.series * a.rows,
            "series": a.series,
            "period": [str(start), str(end)],
            "query_count": a.queries,
            "query_rows": 365,
            "ingestion_seconds": ingest,
            "query_ms": {
                "p50": statistics.median(latencies),
                "p95": sorted(latencies)[int(0.95 * (len(latencies) - 1))],
                "max": max(latencies),
            },
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if platform.system() == "Darwin" else 1024),
            "logical_query_hash": digest(canonical(hashes)),
            "cache": "mixed OS cache; no claim of controlled cold-cache measurements",
            "concurrency": 1,
            "environment": environment(),
        }
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_bytes(canonical(report))
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "environment"}, indent=2
            )
        )


if __name__ == "__main__":
    main()

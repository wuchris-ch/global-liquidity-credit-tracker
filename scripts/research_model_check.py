"""Explicit opt-in, isolated current-vintage model reconstruction and replay."""

import argparse
import json
import os
import time
from pathlib import Path

from src.config import get_index_config, get_series_config
from src.research.contracts import Query, Scope, Series
from src.research.ingestion import Transport, source_snapshot
from src.research.models import run_glci
from src.research.storage import ResearchStore, canonical, digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/research-model-check")
    p.add_argument("--as-of", required=True)
    p.add_argument("--cutoff", default="2024-05-31")
    p.add_argument("--start", default="2000-01-01")
    a = p.parse_args()
    if not os.getenv("FRED_API_KEY"):
        raise ValueError("FRED_API_KEY required")
    store = ResearchStore(a.data)
    transport = Transport(store, "personal")
    inputs = {}
    required = {
        c["series"]
        for pillar in get_index_config("global_liquidity_credit_index")[
            "pillars"
        ].values()
        for c in pillar["components"]
    }
    for name in sorted(required):
        cfg = get_series_config(name)
        source = cfg["source"]
        sid = cfg["source_id"]
        dims = {}
        if source == "fred":
            meta, _ = transport.get(
                "https://api.stlouisfed.org/fred/series",
                {
                    "series_id": sid,
                    "api_key": os.environ["FRED_API_KEY"],
                    "file_type": "json",
                    "realtime_start": a.as_of,
                    "realtime_end": a.as_of,
                },
            )
            unit = meta["seriess"][0]["units"]
        elif source == "bis":
            dims = dict(
                zip(
                    [
                        "FREQ",
                        "BORROWERS_CTY",
                        "TC_BORROWERS",
                        "TC_LENDERS",
                        "VALUATION",
                        "UNIT_TYPE",
                        "TC_ADJUST",
                    ],
                    sid.split("."),
                )
            )
            dims["dataflow"] = "WS_TC"
            unit = (
                "billions "
                + {"US": "USD", "XM": "EUR", "CN": "CNY", "JP": "JPY"}[
                    dims["BORROWERS_CTY"]
                ]
            )
        else:
            raise ValueError("Unreviewed model source")
        country = {"US": "USA", "EU": "EMU", "CN": "CHN", "JP": "JPN"}.get(
            cfg["country"], cfg["country"]
        )
        series = Series(
            id="model:" + name,
            name=cfg["description"],
            source=source,
            source_id=sid,
            country=country,
            unit=unit,
            frequency=cfg["frequency"],
            dimensions=dims,
        )
        from datetime import datetime, timezone

        day = a.as_of if source == "fred" else str(datetime.now(timezone.utc).date())
        scope = Scope(
            start=a.start,
            end=a.cutoff,
            information_date=day,
            mode="source_vintage" if source == "fred" else "forward_capture",
        )
        source_snapshot(store, "personal", series, scope, transport)
        inputs[name] = Query(
            series_id=series.id,
            start=a.start,
            end=a.cutoff,
            as_of=(
                a.as_of if source == "fred" else datetime.now(timezone.utc).isoformat()
            ),
            basis="source" if source == "fred" else "platform",
        )
        print("Captured", name, flush=True)
    manifest = store.manifest("personal")[0]
    for q in inputs.values():
        q.dataset = manifest
        if q.basis == "platform":
            q.as_of = datetime.now(timezone.utc).isoformat()
    payload = {
        "cutoff": a.cutoff,
        "start": a.start,
        "inputs": {k: q.model_dump(mode="json") for k, q in inputs.items()},
        "interpretation": "reconstruction",
    }
    (Path(a.data) / "request.json").write_bytes(canonical(payload))
    started = time.perf_counter()
    first = run_glci(store, "personal", payload)
    second = run_glci(store, "personal", payload)
    assert first["id"] == second["id"]
    report = {
        "status": "passed",
        "model_run_id": first["id"],
        "inputs": len(inputs),
        "cutoff": a.cutoff,
        "observations": len(first["glci"]),
        "regime_coverage": first["regime_coverage"],
        "pillar_artifacts": len(first["models"]),
        "seconds_two_runs": time.perf_counter() - started,
        "interpretation": "current-vintage reconstruction, not a historical platform prediction",
        "glci_hash": digest(canonical(first["glci"])),
    }
    (Path(a.data) / "verification.json").write_bytes(canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

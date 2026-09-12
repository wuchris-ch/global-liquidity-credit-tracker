"""Capture a small public-only FRED vintage collection, independent of private stores.

Run with FRED_API_KEY in the environment. This intentionally never reads a
workspace database, notes, credentials file, or user analysis. Raw responses
are published byte-for-byte with SHA-256 receipts and allowlisted parameters.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

CASES = [
    dict(
        id="growth",
        title="Growth, reconsidered",
        category="Economic growth",
        series="A191RL1Q225SBEA",
        name="US real GDP growth",
        agency="Bureau of Economic Analysis",
        period="2024-01-01",
        period_label="Q1 2024",
        frequency="quarterly",
        operation="level",
        unit="%",
        delta_unit="pp",
        decimals=1,
        threshold=1.5,
        raw_unit="Percent change from preceding period, seasonally adjusted annual rate",
        description="Follow the first quarter from the advance estimate to the third release. The period stays fixed; the evidence changes.",
        question="Does growth clear your chosen reference level?",
        dates=["2024-04-25", "2024-05-30", "2024-06-27"],
        labels=["Advance estimate", "Second estimate", "Third estimate"],
        source_url="https://www.bea.gov/news/2024/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-and-gdp-industry",
    ),
    dict(
        id="employment",
        title="The jobs number moves",
        category="Labour market",
        series="PAYEMS",
        name="US total nonfarm payrolls",
        agency="Bureau of Labor Statistics",
        period="2024-07-01",
        period_label="July 2024",
        frequency="monthly",
        operation="difference",
        unit="k jobs",
        delta_unit="k jobs",
        decimals=0,
        threshold=100,
        raw_unit="Thousands of persons, seasonally adjusted",
        description="A monthly jobs estimate can move in both directions. Compare July payroll growth as later reports arrived.",
        question="Does monthly job creation clear your reference level?",
        dates=["2024-08-02", "2024-09-06", "2024-10-04"],
        labels=["August release", "September release", "October release"],
        source_url="https://www.bls.gov/news.release/archives/empsit_10042024.htm",
    ),
    dict(
        id="production",
        title="A changing industrial pulse",
        category="Real economy",
        series="INDPRO",
        name="US industrial production",
        agency="Federal Reserve Board",
        period="2024-07-01",
        period_label="July 2024",
        frequency="monthly",
        operation="pct_change",
        unit="%",
        delta_unit="pp",
        decimals=2,
        threshold=-0.5,
        raw_unit="Index 2017=100, seasonally adjusted",
        description="Reconstruct monthly production growth from the index available at each release, including revisions to the preceding month.",
        question="Is monthly production growth above your reference level?",
        dates=["2024-08-15", "2024-09-17", "2024-10-17"],
        labels=["August release", "September release", "October release"],
        source_url="https://www.federalreserve.gov/releases/g17/20241017/",
    ),
]


def publish():
    key = os.environ["FRED_API_KEY"]
    repo = Path(__file__).resolve().parents[1]
    public = repo / "frontend/public/research/evidence"
    public.mkdir(parents=True, exist_ok=True)
    collection = {
        "schema_version": "research-atlas/1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cases": [],
    }
    for declaration in CASES:
        case = {k: v for k, v in declaration.items() if k not in ("dates", "labels")}
        case["snapshots"] = []
        for date, label in zip(declaration["dates"], declaration["labels"]):
            params = dict(
                series_id=case["series"],
                file_type="json",
                realtime_start=date,
                realtime_end=date,
                observation_start="2021-01-01",
                observation_end=case["period"],
            )
            try:
                response = requests.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={**params, "api_key": key},
                    timeout=45,
                )
            except requests.RequestException:
                raise RuntimeError(
                    f"FRED transport failed for {case['series']} {date}"
                ) from None
            if response.status_code != 200:
                raise RuntimeError(
                    f"FRED capture failed for {case['series']} {date}: HTTP {response.status_code}"
                )
            payload = response.json()
            assert payload["realtime_start"] == payload["realtime_end"] == date
            assert payload["count"] == len(payload["observations"]) > 1
            assert payload["observations"][-1]["date"] == case["period"]
            assert all(row["value"] != "." for row in payload["observations"])
            filename = f"{case['series']}-{date}.json"
            raw = response.content
            assert key.encode() not in raw
            (public / filename).write_bytes(raw)
            case["snapshots"].append(
                dict(
                    date=date,
                    label=label,
                    captured_at=datetime.now(timezone.utc).isoformat(),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    bytes=len(raw),
                    raw_url=f"/research/evidence/{filename}",
                    source_url="https://api.stlouisfed.org/fred/series/observations",
                    params=params,
                    observations=[
                        dict(date=row["date"], value=row["value"])
                        for row in payload["observations"]
                    ],
                )
            )
        collection["cases"].append(case)
    encoded = json.dumps(collection, indent=2) + "\n"
    assert key not in encoded
    (public / "atlas.json").write_text(encoded)
    target = repo / "frontend/src/lib/research-atlas.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(encoded)
    print(
        f"Published {len(CASES)} studies and nine source captures. No private workspace data used."
    )


if __name__ == "__main__":
    publish()

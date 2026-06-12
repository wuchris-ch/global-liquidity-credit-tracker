#!/usr/bin/env python3
"""Smoke test for the Global Liquidity Tracker.

Verifies the system is healthy without requiring API keys:

  1. Config integrity   - series.yml parses; every index/pillar component
                          references a defined series; weights sum to 1.
  2. Numerics stack     - factor extraction, factor combination, and the
                          Fed Net Liquidity formula all produce correct
                          results on synthetic in-memory data (no network).
  3. Local artifacts    - if a local export exists (after a pipeline run),
                          validate the production-required JSON endpoints.
  4. Live endpoints     - with --live, fetch the published GitHub Pages
                          JSON and check it parses and is recent.

Usage:
  python scripts/smoke.py            # offline checks only
  python scripts/smoke.py --live     # also check the published site

Exit code 0 = healthy, 1 = at least one check failed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_LIVE_BASE = "https://wuchris-ch.github.io/global-liquidity-credit-tracker/latest"
LIVE_ENDPOINTS = (
    "api/glci/latest/index.json",
    "api/glci/freshness/index.json",
    "api/indices/fed_net_liquidity/index.json",
    "api/risk/index.json",
    "api/backtest/track_record/index.json",
    "api/flows/index.json",
    "api/series/fed_total_assets/latest/index.json",
)
MAX_LIVE_AGE_DAYS = 30


class Smoke:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  PASS  {label}" + (f" ({detail})" if detail else ""))

    def fail(self, label: str, detail: str) -> None:
        print(f"  FAIL  {label}: {detail}")
        self.failures.append(f"{label}: {detail}")

    def warn(self, label: str, detail: str) -> None:
        print(f"  WARN  {label}: {detail}")
        self.warnings.append(f"{label}: {detail}")


def check_config(s: Smoke) -> None:
    print("\n[1/4] Config integrity")
    try:
        from src.config import get_all_indices, get_all_series, get_index_config
        all_series = get_all_series()
        all_indices = get_all_indices()
    except Exception as e:
        s.fail("config load", str(e))
        return

    s.ok("series.yml parses", f"{len(all_series)} series, {len(all_indices)} indices")

    missing = []
    for index_id, cfg in all_indices.items():
        for comp in cfg.get("components", []):
            if comp["series"] not in all_series:
                missing.append(f"{index_id} -> {comp['series']}")
        for pillar, pcfg in cfg.get("pillars", {}).items():
            for comp in pcfg.get("components", []):
                if comp["series"] not in all_series:
                    missing.append(f"{index_id}/{pillar} -> {comp['series']}")
    if missing:
        s.fail("index component references", ", ".join(missing))
    else:
        s.ok("all index components reference defined series")

    glci = get_index_config("global_liquidity_credit_index")
    weights = glci.get("pillar_weights", {})
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        s.fail("GLCI pillar weights", f"sum to {sum(weights.values())}, expected 1.0")
    else:
        s.ok("GLCI pillar weights sum to 1.0", str(weights))


def check_numerics(s: Smoke) -> None:
    print("\n[2/4] Numerics stack (synthetic data, offline)")
    try:
        import numpy as np
        import pandas as pd
        from src.indicators.dynamic_factor import DynamicFactorModel, combine_factors
    except Exception as e:
        s.fail("imports", str(e))
        return

    # Factor extraction recovers a known latent factor
    rng = np.random.default_rng(0)
    n = 150
    factor = np.cumsum(rng.normal(0, 1, n))
    X = pd.DataFrame({
        f"x{i}": (0.5 + 0.5 * rng.random()) * factor + rng.normal(0, 0.5, n)
        for i in range(4)
    })
    try:
        model = DynamicFactorModel(n_factors=1, method="auto")
        model.fit(X)
        extracted = model.transform().iloc[:, 0]
        corr = abs(np.corrcoef(extracted.values, factor)[0, 1])
        if corr > 0.9:
            s.ok("factor model recovers latent factor", f"corr={corr:.3f}, method={model._method_used}")
        else:
            s.fail("factor model", f"weak factor recovery, corr={corr:.3f}")
    except Exception as e:
        s.fail("factor model", str(e))

    # Composite normalization
    try:
        idx = pd.date_range("2020-01-03", periods=n, freq="W-FRI")
        combined = combine_factors(
            {"a": pd.Series(factor, index=idx), "b": pd.Series(-factor, index=idx)},
            weights={"a": 0.6, "b": 0.4},
        )
        if abs(combined.mean() - 100) < 1 and abs(combined.std() - 10) < 1:
            s.ok("composite normalizes to mean 100 / stdev 10")
        else:
            s.fail("composite normalization",
                   f"mean={combined.mean():.2f}, std={combined.std():.2f}")
    except Exception as e:
        s.fail("composite combination", str(e))

    # Fed Net Liquidity formula via the real Aggregator
    try:
        from src.indicators.aggregator import Aggregator

        dates = pd.date_range("2024-01-05", periods=12, freq="W-FRI")

        class _Stub:
            def __init__(self, frames):
                self.frames = frames

            def fetch_series(self, sid, start=None, end=None):
                return self.frames[sid].copy()

        def mk(vals):
            return pd.DataFrame({"date": dates, "value": vals})

        stub = _Stub({
            "fed_total_assets": mk([8_000_000.0] * 12),
            "fed_treasury_general_account": mk([700_000.0] * 12),
            "fed_reverse_repo": mk([500.0] * 12),  # billions
        })
        df = Aggregator(fetcher=stub).compute_index("fed_net_liquidity")
        expected = 8_000_000 - 700_000 - 500 * 1000
        actual = df["value"].iloc[-1]
        if abs(actual - expected) < 1e-6:
            s.ok("Fed Net Liquidity = assets - TGA - RRP", f"{actual:,.0f}M")
        else:
            s.fail("Fed Net Liquidity formula", f"got {actual:,.0f}, expected {expected:,.0f}")
    except Exception as e:
        s.fail("Fed Net Liquidity formula", str(e))


def check_local_artifacts(s: Smoke) -> None:
    print("\n[3/4] Local artifacts")
    from scripts.export_to_json import validate_required_exports

    export_dir = ROOT / "data" / "export" / "latest"
    probe = export_dir / "api" / "series" / "fed_total_assets" / "index.json"
    if not probe.is_file():
        s.warn("local export", "not present (expected: data/ is generated by the pipeline)")
        return

    errors = validate_required_exports(export_dir)
    if errors:
        for e in errors:
            s.fail("local export", e)
    else:
        s.ok("local export passes production validation", str(export_dir))


def check_live(s: Smoke, base_url: str) -> None:
    print(f"\n[4/4] Live endpoints ({base_url})")
    import requests

    for endpoint in LIVE_ENDPOINTS:
        url = f"{base_url}/{endpoint}"
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                s.fail(endpoint, f"HTTP {resp.status_code}")
                continue
            payload = resp.json()
        except json.JSONDecodeError:
            s.fail(endpoint, "invalid JSON")
            continue
        except Exception as e:
            s.fail(endpoint, str(e))
            continue
        s.ok(endpoint)

        if endpoint == "api/glci/latest/index.json":
            date_str = payload.get("date", "")
            try:
                age = (datetime.now(timezone.utc)
                       - datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc))
                if age > timedelta(days=MAX_LIVE_AGE_DAYS):
                    s.fail("GLCI freshness", f"latest data {date_str} is {age.days} days old")
                else:
                    s.ok("GLCI freshness", f"latest data {date_str}, {age.days} days old")
            except ValueError:
                s.fail("GLCI freshness", f"unparseable date '{date_str}'")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test (no API keys required)")
    parser.add_argument("--live", action="store_true",
                        help="Also check the published GitHub Pages endpoints")
    parser.add_argument("--base-url", default=DEFAULT_LIVE_BASE,
                        help="Base URL of the published data (with --live)")
    args = parser.parse_args()

    s = Smoke()
    print("Global Liquidity Tracker - smoke test")

    check_config(s)
    check_numerics(s)
    check_local_artifacts(s)
    if args.live:
        check_live(s, args.base_url.rstrip("/"))
    else:
        print("\n[4/4] Live endpoints: skipped (pass --live to enable)")

    print("\n" + "=" * 50)
    if s.failures:
        print(f"SMOKE FAILED: {len(s.failures)} failure(s)")
        for f in s.failures:
            print(f"  - {f}")
        return 1
    suffix = f", {len(s.warnings)} warning(s)" if s.warnings else ""
    print(f"SMOKE PASSED{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

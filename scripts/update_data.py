#!/usr/bin/env python3
"""
Scheduled data update script.
Run via cron or GitHub Actions to keep data fresh.

Example cron (daily at 6am):
0 6 * * * cd /path/to/global_liquidity_tracker && python scripts/update_data.py

Example GitHub Actions workflow:
  schedule:
    - cron: '0 6 * * *'
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import FRED_API_KEY, get_series_config
from src.data_quality import freshness_state
from src.etl import DataFetcher, DataStorage
from src.indicators import Aggregator, GLCIComputer


HISTORICAL_MODE = "reconstructed_current_vintage"


def _as_utc_iso(value=None) -> str:
    """Return an ISO-8601 UTC timestamp with an explicit zone."""
    timestamp = pd.Timestamp(value if value is not None else datetime.now(timezone.utc))
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")


def _snapshot_number(value):
    """Convert a pandas scalar to a JSON/parquet-safe number or null."""
    if value is None or pd.isna(value):
        return None
    return float(value)


def build_glci_snapshot(result) -> dict:
    """Build the append-only record of the latest published GLCI state."""
    if result.glci is None or result.glci.empty:
        raise ValueError("Cannot snapshot an empty GLCI result")

    glci = result.glci.sort_values("date")
    latest = glci.iloc[-1]
    signal_date = pd.Timestamp(latest["date"]).strftime("%Y-%m-%d")
    computed_at = _as_utc_iso(result.metadata.get("computed_at"))

    snapshot = {
        "computed_at": computed_at,
        "signal_date": signal_date,
        "historical_mode": HISTORICAL_MODE,
        "point_in_time": False,
        "frequency": "W-FRI",
        "model_revision": os.getenv("GITHUB_SHA") or "local",
        "factor_method": result.metadata.get("factor_method"),
        "glci": _snapshot_number(latest.get("value")),
        "zscore": _snapshot_number(latest.get("zscore")),
        "regime": (
            int(latest["regime"])
            if "regime" in latest and pd.notna(latest["regime"])
            else None
        ),
        "momentum": _snapshot_number(latest.get("momentum")),
        "prob_regime_change": _snapshot_number(
            latest.get("prob_regime_change")
        ),
    }

    pillar_weights = result.weights.get("pillar_weights", {})
    if isinstance(pillar_weights, dict):
        for pillar_name, weight in sorted(pillar_weights.items()):
            snapshot[f"weight_{pillar_name}"] = _snapshot_number(weight)

    if result.pillars is not None and not result.pillars.empty:
        pillars = result.pillars.sort_values("date")
        eligible = pillars[pd.to_datetime(pillars["date"]) <= pd.Timestamp(latest["date"])]
        if not eligible.empty:
            latest_pillars = eligible.iloc[-1]
            for pillar_name in pillars.columns:
                if pillar_name == "date":
                    continue
                snapshot[f"pillar_{pillar_name}"] = _snapshot_number(
                    latest_pillars[pillar_name]
                )

    return snapshot


def main():
    print(f"[{datetime.now().isoformat()}] Starting data update...")
    
    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set")
        sys.exit(1)
    
    fetcher = DataFetcher()
    storage = DataStorage()
    aggregator = Aggregator(fetcher)
    
    # Date range: full history (None = fetch all available from sources)
    start_date = None
    end_date = None
    
    # 1. Fetch all series
    print("\n[1/4] Fetching raw data...")
    
    # Series that production pages depend on directly. If any of these fail on
    # a clean CI runner, publishing would replace the last good static export
    # with 404s for visible dashboard routes.
    priority_series = [
        "fed_total_assets",
        "ecb_total_assets",
        "boj_total_assets",
        "fed_treasury_general_account",
        "fed_reverse_repo",
        "sofr",
        "fed_funds_rate",
        "ice_bofa_us_high_yield_spread",
        "ice_bofa_us_ig_spread",
        # Liquidity Monitor overlay + risk dashboard
        "sp500_price",
    ]
    
    results = fetcher.fetch_multiple(priority_series, start_date, end_date)
    missing_required = [
        series_id
        for series_id in priority_series
        if series_id not in results or results[series_id].empty
    ]
    if missing_required:
        print("\nERROR: Required production series failed to fetch:")
        for series_id in missing_required:
            print(f"  - {series_id}")
        print("Aborting before export so the existing published data stays intact.")
        sys.exit(1)
    
    for series_id, df in results.items():
        if not df.empty:
            source = df["source"].iloc[0]
            storage.append_raw(df, source, series_id)
            print(f"  ✓ {series_id}: {len(df)} obs")

    # Asset prices for the Playbook and Flows pages. Best effort: a failed
    # fetch here (e.g. Yahoo throttling the runner) skips that asset but
    # never blocks the publish, so these are kept out of priority_series.
    asset_series = [
        "gold_price",
        "silver_price",
        "russell2000_price",
        "bitcoin_price",
        "ethereum_price",
        "zcash_price",
        "long_bond_price",
        "semis_price",
        "nasdaq100",
    ]

    print("\n[1b/4] Fetching asset prices (best effort)...")
    asset_results = fetcher.fetch_multiple(asset_series, start_date, end_date)
    for series_id in asset_series:
        df = asset_results.get(series_id)
        if df is None or df.empty:
            print(f"  ✗ {series_id}: no data (skipped)")
            continue
        source = df["source"].iloc[0]
        storage.append_raw(df, source, series_id)
        print(f"  ✓ {series_id}: {len(df)} obs")

    # 2. Compute indices
    print("\n[2/4] Computing indices...")
    
    indices_to_compute = ["fed_net_liquidity", "usd_funding_stress"]
    
    for index_id in indices_to_compute:
        try:
            df = aggregator.compute_index(index_id, start_date, end_date)
            if not df.empty:
                storage.save_curated(
                    df, "indices", index_id,
                    metadata={
                        "computed_at": datetime.now().isoformat(),
                        "start_date": start_date,
                        "end_date": end_date,
                    }
                )
                print(f"  ✓ {index_id}: {len(df)} obs, latest={df['value'].iloc[-1]:,.0f}")
        except Exception as e:
            print(f"  ✗ {index_id}: {e}")
    
    # 3. Compute the GLCI and preserve exactly what this run will publish.
    print("\n[3/4] Computing GLCI and preserving signal snapshot...")
    try:
        glci_result = GLCIComputer(fetcher=fetcher, storage=storage).compute(
            start_date,
            end_date,
            target_freq="W",
            save_output=True,
            verbose=True,
        )
        snapshot_path = storage.append_signal_snapshot(
            build_glci_snapshot(glci_result)
        )
        latest_glci = glci_result.glci.sort_values("date").iloc[-1]
        print(
            "  ✓ GLCI: "
            f"{latest_glci['value']:.2f} as of "
            f"{pd.Timestamp(latest_glci['date']).strftime('%Y-%m-%d')}"
        )
        print(f"  ✓ Preserved signal vintage in {snapshot_path}")
    except Exception as exc:
        print(f"\nERROR: GLCI computation or snapshot failed: {exc}")
        print("Aborting before export so the existing published data stays intact.")
        raise SystemExit(1) from exc

    # 4. Health check
    print("\n[4/4] Health check...")
    
    errors = []
    
    # Check for stale data
    for series_id in priority_series:
        latest = storage.get_latest_date("fred", series_id)
        if latest:
            days_old, is_stale = freshness_state(
                latest,
                get_series_config(series_id).get("frequency"),
            )
            if is_stale:
                errors.append(f"{series_id}: data is {days_old} days old")

    # Asset prices are best effort, so a throttled or broken source never
    # fails the run; surface it here instead of letting the asset go stale
    # unnoticed across publishes.
    for series_id in asset_series:
        df = asset_results.get(series_id)
        if df is None or df.empty:
            errors.append(f"{series_id}: fetch returned no data this run")
            continue
        latest = pd.to_datetime(df["date"]).max()
        days_old, is_stale = freshness_state(
            latest,
            get_series_config(series_id).get("frequency"),
        )
        if is_stale:
            errors.append(f"{series_id}: data is {days_old} days old")
    
    if errors:
        print("\n⚠️  Warnings:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("  ✓ All data is fresh")
    
    print(f"\n[{datetime.now().isoformat()}] Update complete!")


if __name__ == "__main__":
    main()

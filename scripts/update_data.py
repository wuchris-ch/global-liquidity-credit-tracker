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
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import FRED_API_KEY
from src.etl import DataFetcher, DataStorage
from src.indicators import Aggregator


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
    print("\n[1/3] Fetching raw data...")
    
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
        "ted_spread",
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

    print("\n[1b/3] Fetching asset prices (best effort)...")
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
    print("\n[2/3] Computing indices...")
    
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
    
    # 3. Health check
    print("\n[3/3] Health check...")
    
    errors = []
    
    # Check for stale data
    for series_id in priority_series:
        latest = storage.get_latest_date("fred", series_id)
        if latest:
            # Compare on calendar dates so tz-aware series don't break the
            # subtraction against a tz-naive datetime.now().
            days_old = (datetime.now().date() - latest.date()).days
            if days_old > 7:
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
        days_old = (datetime.now().date() - latest.date()).days
        if days_old > 7:
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

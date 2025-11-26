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
    
    # Date range: last 3 years
    start_date = (datetime.now() - timedelta(days=365*3)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Fetch all series
    print("\n[1/3] Fetching raw data...")
    
    # Priority series (daily/weekly)
    priority_series = [
        "fed_total_assets",
        "fed_treasury_general_account", 
        "fed_reverse_repo",
        "sofr",
        "fed_funds_rate",
        "ted_spread",
        "ice_bofa_us_high_yield_spread",
        "ice_bofa_us_ig_spread",
    ]
    
    results = fetcher.fetch_multiple(priority_series, start_date, end_date)
    
    for series_id, df in results.items():
        if not df.empty:
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
            days_old = (datetime.now() - latest.to_pydatetime()).days
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

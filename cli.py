#!/usr/bin/env python3
"""CLI for Global Liquidity Tracker."""
import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd

from src.config import FRED_API_KEY, get_all_series, get_all_indices
from src.etl import DataFetcher, DataStorage
from src.indicators import Aggregator


def main():
    parser = argparse.ArgumentParser(
        description="Global Liquidity Tracker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch data from sources")
    fetch_parser.add_argument("--series", "-s", nargs="+", help="Series IDs to fetch")
    fetch_parser.add_argument("--source", help="Fetch all series from source (fred, bis, worldbank, nyfed)")
    fetch_parser.add_argument("--all", action="store_true", help="Fetch all configured series")
    fetch_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    fetch_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    fetch_parser.add_argument("--save", action="store_true", help="Save to storage")
    
    # Compute command
    compute_parser = subparsers.add_parser("compute", help="Compute composite indices")
    compute_parser.add_argument("--index", "-i", nargs="+", help="Index IDs to compute")
    compute_parser.add_argument("--all", action="store_true", help="Compute all indices")
    compute_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    compute_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    compute_parser.add_argument("--save", action="store_true", help="Save to storage")
    compute_parser.add_argument("--pillars", action="store_true", help="Output pillar subindices (GLCI only)")
    compute_parser.add_argument("--regime", action="store_true", help="Include regime classification (GLCI only)")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available series/indices")
    list_parser.add_argument("type", choices=["series", "indices", "stored"], help="What to list")
    
    # Show command
    show_parser = subparsers.add_parser("show", help="Show series data")
    show_parser.add_argument("series_id", help="Series ID to show")
    show_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    show_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    show_parser.add_argument("--tail", type=int, default=20, help="Number of rows to show")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Check API key for commands that need it
    if args.command in ["fetch", "compute", "show"] and not FRED_API_KEY:
        print("Error: FRED_API_KEY not set. Add it to your .env file.")
        print("Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        sys.exit(1)
    
    if args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "compute":
        cmd_compute(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)


def cmd_fetch(args):
    """Fetch data from sources."""
    fetcher = DataFetcher()
    storage = DataStorage()
    
    start = args.start or (datetime.now() - timedelta(days=365*3)).strftime("%Y-%m-%d")
    end = args.end or datetime.now().strftime("%Y-%m-%d")
    
    if args.all:
        print("Fetching all configured series...")
        results = fetcher.fetch_all(start, end)
    elif args.source:
        print(f"Fetching all {args.source} series...")
        results = fetcher.fetch_by_source(args.source, start, end)
    elif args.series:
        print(f"Fetching series: {args.series}")
        results = fetcher.fetch_multiple(args.series, start, end)
    else:
        print("Specify --series, --source, or --all")
        return
    
    for series_id, df in results.items():
        print(f"  {series_id}: {len(df)} observations")
        
        if args.save and not df.empty:
            source = df["source"].iloc[0] if "source" in df.columns else "unknown"
            storage.save_raw(df, source, series_id)
            print(f"    Saved to storage")
    
    print(f"\nFetched {len(results)} series")


def cmd_compute(args):
    """Compute composite indices."""
    aggregator = Aggregator()
    storage = DataStorage()
    
    start = args.start or (datetime.now() - timedelta(days=365*3)).strftime("%Y-%m-%d")
    end = args.end or datetime.now().strftime("%Y-%m-%d")
    
    if args.all:
        print("Computing all indices...")
        results = aggregator.compute_all_indices(start, end)
    elif args.index:
        print(f"Computing indices: {args.index}")
        results = {}
        for idx in args.index:
            try:
                # Special handling for GLCI with pillars/regime flags
                if idx == "global_liquidity_credit_index" and (args.pillars or args.regime):
                    full_result = aggregator.compute_glci(
                        start, end, 
                        save=args.save, 
                        include_pillars=True
                    )
                    results[idx] = full_result["glci"]
                    
                    # Print pillar info if requested
                    if args.pillars:
                        print(f"\n  Pillar breakdown:")
                        pillars_df = full_result["pillars"]
                        latest_pillars = pillars_df.iloc[-1]
                        for col in pillars_df.columns:
                            if col != "date":
                                weight = full_result["weights"]["pillar_weights"].get(col, 0)
                                print(f"    {col}: {latest_pillars[col]:.2f} (weight: {weight:.0%})")
                    
                    # Print regime info if requested
                    if args.regime:
                        regimes_df = full_result["regimes"]
                        latest_regime = regimes_df.iloc[-1]
                        print(f"\n  Current regime: {latest_regime['regime_label']} (zscore: {latest_regime['zscore']:.2f})")
                        
                        # Regime distribution
                        regime_counts = regimes_df["regime_label"].value_counts()
                        print(f"  Regime distribution:")
                        for regime, count in regime_counts.items():
                            pct = count / len(regimes_df) * 100
                            print(f"    {regime}: {count} periods ({pct:.1f}%)")
                else:
                    results[idx] = aggregator.compute_index(idx, start, end)
            except Exception as e:
                print(f"  Error computing {idx}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("Specify --index or --all")
        return
    
    for index_id, df in results.items():
        if not df.empty:
            latest = df.iloc[-1]["value"]
            print(f"  {index_id}: {len(df)} observations, latest={latest:,.2f}")
            
            if args.save and index_id != "global_liquidity_credit_index":
                # GLCI saves are handled separately with full results
                storage.save_curated(df, "indices", index_id)
                print(f"    Saved to storage")
    
    print(f"\nComputed {len(results)} indices")


def cmd_list(args):
    """List available series/indices."""
    if args.type == "series":
        all_series = get_all_series()
        print(f"\nConfigured Series ({len(all_series)}):\n")
        
        # Group by source
        by_source = {}
        for sid, cfg in all_series.items():
            source = cfg.get("source", "other")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append((sid, cfg))
        
        for source, items in sorted(by_source.items()):
            print(f"[{source.upper()}]")
            for sid, cfg in items:
                desc = cfg.get("description", "")[:50]
                freq = cfg.get("frequency", "?")
                print(f"  {sid:<30} {freq:<10} {desc}")
            print()
    
    elif args.type == "indices":
        all_indices = get_all_indices()
        print(f"\nConfigured Indices ({len(all_indices)}):\n")
        
        for idx, cfg in all_indices.items():
            desc = cfg.get("description", "")[:60]
            method = cfg.get("method", "arithmetic")
            n_comp = len(cfg.get("components", []))
            print(f"  {idx:<25} {method:<15} {n_comp} components")
            print(f"    {desc}")
            print()
    
    elif args.type == "stored":
        storage = DataStorage()
        
        print("\nStored Raw Data:")
        raw = storage.list_raw_series()
        for item in raw:
            print(f"  {item['source']}/{item['series_id']}")
        
        print("\nStored Curated Data:")
        curated = storage.list_curated()
        for item in curated:
            print(f"  {item['category']}/{item['name']}")


def cmd_show(args):
    """Show series data."""
    fetcher = DataFetcher()
    
    start = args.start or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    end = args.end or datetime.now().strftime("%Y-%m-%d")
    
    try:
        df = fetcher.fetch_series(args.series_id, start, end)
        
        if df.empty:
            print(f"No data for {args.series_id}")
            return
        
        print(f"\n{args.series_id}")
        print(f"Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"Observations: {len(df)}")
        print()
        
        # Show tail
        display_df = df[["date", "value"]].tail(args.tail)
        display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
        print(display_df.to_string(index=False))
        
        # Stats
        print(f"\nStats:")
        print(f"  Latest: {df['value'].iloc[-1]:,.4f}")
        print(f"  Min:    {df['value'].min():,.4f}")
        print(f"  Max:    {df['value'].max():,.4f}")
        print(f"  Mean:   {df['value'].mean():,.4f}")
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()

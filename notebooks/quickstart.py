#!/usr/bin/env python3
"""
Quick start script to test the Global Liquidity Tracker.
Run this to verify your setup is working.
"""
import sys
sys.path.insert(0, '..')

from datetime import datetime, timedelta

# Check environment
print("=" * 60)
print("Global Liquidity Tracker - Quick Start")
print("=" * 60)

# 1. Check config
print("\n1. Checking configuration...")
from src.config import FRED_API_KEY, get_all_series, get_all_indices

if not FRED_API_KEY:
    print("   ❌ FRED_API_KEY not set!")
    print("   Set it in your .env file or as environment variable")
    print("   Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
    sys.exit(1)
else:
    print(f"   ✓ FRED API key configured (ends with ...{FRED_API_KEY[-4:]})")

series = get_all_series()
indices = get_all_indices()
print(f"   ✓ {len(series)} series configured")
print(f"   ✓ {len(indices)} indices configured")

# 2. Test FRED connection
print("\n2. Testing FRED connection...")
from src.data_sources import FredClient

try:
    fred = FredClient()
    df = fred.get_series("WALCL", start_date="2024-01-01")
    print(f"   ✓ Fed Total Assets: {len(df)} observations")
    print(f"   Latest: ${df['value'].iloc[-1]/1e6:.2f} trillion ({df['date'].iloc[-1].strftime('%Y-%m-%d')})")
except Exception as e:
    print(f"   ❌ FRED error: {e}")

# 3. Test World Bank (no API key needed)
print("\n3. Testing World Bank connection...")
from src.data_sources import WorldBankClient

try:
    wb = WorldBankClient()
    df = wb.get_credit_to_gdp("US", start_date="2020")
    print(f"   ✓ US Credit-to-GDP: {len(df)} observations")
    if not df.empty:
        print(f"   Latest: {df['value'].iloc[-1]:.1f}%")
except Exception as e:
    print(f"   ❌ World Bank error: {e}")

# 4. Test NY Fed (no API key needed)
print("\n4. Testing NY Fed connection...")
from src.data_sources import NYFedClient

try:
    nyfed = NYFedClient()
    df = nyfed.get_sofr()
    print(f"   ✓ SOFR: {len(df)} observations")
    if not df.empty:
        print(f"   Latest: {df['value'].iloc[-1]:.2f}% ({df['date'].iloc[-1].strftime('%Y-%m-%d')})")
except Exception as e:
    print(f"   ❌ NY Fed error: {e}")

# 5. Test data fetcher
print("\n5. Testing unified data fetcher...")
from src.etl import DataFetcher

try:
    fetcher = DataFetcher()
    
    # Fetch a few key series
    start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    results = fetcher.fetch_multiple(
        ["fed_total_assets", "sofr", "us_m2"],
        start_date=start
    )
    
    for sid, df in results.items():
        print(f"   ✓ {sid}: {len(df)} observations")
        
except Exception as e:
    print(f"   ❌ Fetcher error: {e}")

# 6. Test index computation
print("\n6. Testing index computation...")
from src.indicators import Aggregator

try:
    agg = Aggregator(fetcher)
    
    # Compute Fed Net Liquidity
    df = agg.compute_fed_net_liquidity(start_date=start)
    print(f"   ✓ Fed Net Liquidity: {len(df)} observations")
    if not df.empty:
        latest = df['value'].iloc[-1]
        print(f"   Latest: ${latest/1e6:.2f} trillion")
        
except Exception as e:
    print(f"   ❌ Aggregator error: {e}")

# Summary
print("\n" + "=" * 60)
print("Setup complete! You can now:")
print("  • Run the frontend: cd frontend && npm run dev")
print("  • Use the CLI: python cli.py --help")
print("  • Explore in notebooks")
print("=" * 60)

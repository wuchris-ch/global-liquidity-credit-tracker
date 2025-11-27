# Global Liquidity Tracker

Track global liquidity and credit metrics from central banks, BIS, World Bank, and market data sources.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Set up your FRED API key
cp .env.example .env
# Edit .env and add your FRED API key (get one free at https://fred.stlouisfed.org/docs/api/api_key.html)

# Start the API server (required for frontend)
uvicorn src.api:app --reload --port 8000

# In another terminal, run the frontend
cd frontend && npm run dev
```

The frontend will be available at http://localhost:3000 and will fetch live data from the Python API.

### CLI Usage

```bash
python cli.py list series
python cli.py fetch --series fed_total_assets sofr --save
python cli.py compute --index fed_net_liquidity
```

## Data Sources

| Source | Data | API |
|--------|------|-----|
| FRED | US macro, CB balance sheets, spreads | Free API key required |
| BIS | Credit to non-financial sector | SDMX (no key) |
| World Bank | Credit-to-GDP ratios | REST (no key) |
| NY Fed | SOFR, repo operations | REST (no key) |

## Configured Series

### Central Bank Balance Sheets
- `fed_total_assets` - Federal Reserve Total Assets (weekly)
- `ecb_total_assets` - ECB Total Assets (weekly)
- `boj_total_assets` - Bank of Japan Total Assets (monthly)

### Funding Rates
- `sofr` - Secured Overnight Financing Rate (daily)
- `fed_funds_rate` - Effective Fed Funds Rate (daily)
- `euro_short_term_rate` - €STR (daily)

### Monetary Aggregates
- `us_m2`, `eu_m3`, `china_m2`, `japan_m2`

### Credit Spreads
- `ted_spread` - TED Spread
- `ice_bofa_us_high_yield_spread` - US HY Spread
- `ice_bofa_us_ig_spread` - US IG Spread

### BIS Credit Data
- `bis_credit_us`, `bis_credit_eu`, `bis_credit_cn`, `bis_credit_jp`

## Composite Indices

### Fed Net Liquidity
```
Fed Total Assets - Treasury General Account - Reverse Repo
```
A widely-used indicator of USD liquidity conditions.

### USD Funding Stress
Z-score average of TED spread, HY spread, and IG spread.

### Global CB Assets
Sum of major central bank balance sheets (USD-normalized).

## Project Structure

```
global_liquidity_tracker/
├── config/
│   └── series.yml          # Series and index definitions
├── src/
│   ├── data_sources/       # API clients (FRED, BIS, World Bank, NY Fed)
│   ├── etl/                # Data fetching and storage
│   └── indicators/         # Aggregation and transforms
├── data/
│   ├── raw/                # Raw fetched data (parquet)
│   └── curated/            # Computed indices (parquet)
├── frontend/               # Next.js dashboard
├── cli.py                  # Command-line interface
└── pyproject.toml
```

## CLI Usage

```bash
# List available series
python cli.py list series

# List available indices
python cli.py list indices

# Fetch specific series
python cli.py fetch --series fed_total_assets sofr us_m2 --save

# Fetch all FRED series
python cli.py fetch --source fred --save

# Compute an index
python cli.py compute --index fed_net_liquidity --save

# Show series data
python cli.py show fed_total_assets --tail 30
```

## Adding New Series

Edit `config/series.yml`:

```yaml
series:
  my_new_series:
    source: fred           # fred, bis, worldbank, nyfed
    source_id: SERIES_ID   # Source-specific ID
    country: US
    frequency: weekly      # daily, weekly, monthly, quarterly, annual
    type: stock            # stock, rate, ratio, spread
    unit: millions_usd
    description: "My new series description"
```

## Adding New Indices

```yaml
indices:
  my_custom_index:
    description: "My custom composite index"
    frequency: weekly
    method: arithmetic     # arithmetic, zscore_average, sum_normalized, weighted_average
    components:
      - series: series_1
        operation: add
        weight: 1.0
      - series: series_2
        operation: subtract
        weight: 1.0
```

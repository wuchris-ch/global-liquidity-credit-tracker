# Global Liquidity Tracker

Track global liquidity and credit metrics from central banks, BIS, World Bank, and market data sources.

## Live Demo

**[global-liquidity-credit-tracker.vercel.app](https://global-liquidity-credit-tracker.vercel.app)**

- [Dashboard](https://global-liquidity-credit-tracker.vercel.app/), overview of key liquidity metrics
- [GLCI Index](https://global-liquidity-credit-tracker.vercel.app/glci), Global Liquidity & Credit Index (tri-pillar composite)
- [Risk by Regime](https://global-liquidity-credit-tracker.vercel.app/risk), Sharpe ratios and returns by GLCI regime
- [Liquidity Monitor](https://global-liquidity-credit-tracker.vercel.app/liquidity), Fed balance sheet & net liquidity
- [Credit Spreads](https://global-liquidity-credit-tracker.vercel.app/spreads), HY/IG spread analysis
- [Data Explorer](https://global-liquidity-credit-tracker.vercel.app/explorer), compare multiple series

## Architecture

Static-first architecture with a scheduled data pipeline:

| Layer | Stack | Hosting |
|-------|-------|---------|
| **Frontend** | Next.js, React, Tailwind, shadcn/ui, Recharts | Vercel |
| **Data Pipeline** | Python, pandas, statsmodels, scipy | GitHub Actions (scheduled) |
| **Data Storage** | Pre-computed JSON | GitHub Pages |
| **Data Sources** | FRED, BIS, World Bank, NY Fed, Yahoo Finance | External APIs |

**How it works:**
1. GitHub Actions runs every 12 hours.
2. Python scripts fetch data from all sources and compute indices (GLCI, Fed Net Liquidity, risk metrics, etc.).
3. Results are exported as static JSON and published to GitHub Pages.
4. Frontend fetches pre-built JSON instantly, no backend computation at request time.

> **Important:** Do not delete the `gh-pages` branch! It stores the pre-computed JSON data served by GitHub Pages. Deleting it will break the production frontend. The branch is protected, but if you must modify branch settings, ensure `gh-pages` remains intact.

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
| Yahoo Finance | Asset prices (ETFs, crypto) | yfinance (no key) |

## Configured Series

### Central Bank Balance Sheets
- `fed_total_assets` - Federal Reserve Total Assets (weekly)
- `ecb_total_assets` - ECB Total Assets (weekly)
- `boj_total_assets` - Bank of Japan Total Assets (monthly)

### Funding Rates
- `sofr` - Secured Overnight Financing Rate (daily)
- `fed_funds_rate` - Effective Fed Funds Rate (daily)
- `euro_short_term_rate` - Euro Short-Term Rate (daily)

### Monetary Aggregates
- `us_m2`, `eu_m3`, `china_m2`, `japan_m2`

### Credit Spreads
- `ted_spread` - TED Spread
- `ice_bofa_us_high_yield_spread` - US HY Spread
- `ice_bofa_us_ig_spread` - US IG Spread

### BIS Credit Data
- `bis_credit_us`, `bis_credit_eu`, `bis_credit_cn`, `bis_credit_jp`

### Asset Prices (for Risk Dashboard)
- `sp500_price` - S&P 500 Index (FRED)
- `russell2000_price` - Russell 2000 ETF (IWM)
- `gold_price` - Gold ETF (GLD)
- `silver_price` - Silver ETF (SLV)
- `bitcoin_price` - Bitcoin (BTC-USD)
- `ethereum_price` - Ethereum (ETH-USD)
- `long_bond_price` - 20+ Year Treasury Bond ETF (TLT)

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

### Global Liquidity & Credit Index (GLCI)
Tri-pillar composite index combining:
- **Liquidity** (40%): Central bank balance sheets, reserve balances, M2
- **Credit** (35%): Bank credit, consumer credit, BIS credit data
- **Stress** (25%, inverted): Credit spreads, VIX, funding rates

Regime classification: Tight (z-score < -1), Neutral (-1 to +1), Loose (> +1)

## Risk by Regime Dashboard

The Risk by Regime dashboard shows how different asset classes perform under various GLCI liquidity regimes.

**Metrics computed:**
- Sharpe ratios (overall and by regime)
- Annualized returns and volatility
- Maximum drawdown
- Correlation with GLCI
- Rolling 252-day Sharpe ratio time series

**Assets tracked:**
- Large Cap Equities: S&P 500
- Small Cap Equities: Russell 2000
- Commodities: Gold, Silver
- Crypto: Bitcoin, Ethereum
- Fixed Income: Long Bonds (TLT)

## Project Structure

```
global_liquidity_tracker/
├── config/
│   └── series.yml          # Series and index definitions
├── src/
│   ├── data_sources/       # API clients (FRED, BIS, World Bank, NY Fed, yfinance)
│   ├── etl/                # Data fetching and storage
│   └── indicators/         # Aggregation, transforms, risk metrics
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

# Compute risk metrics
python -c "from src.indicators.risk_metrics import compute_risk_metrics; compute_risk_metrics(save=True)"
```

## Adding New Series

Edit `config/series.yml`:

```yaml
series:
  my_new_series:
    source: fred           # fred, bis, worldbank, nyfed, yfinance
    source_id: SERIES_ID   # Source-specific ID
    country: US
    frequency: weekly      # daily, weekly, monthly, quarterly, annual
    type: stock            # stock, rate, ratio, spread, price
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

## Learnings

### Why I moved away from Render

The original architecture used a **Render backend** running FastAPI to serve data on-demand:

```
User Request → Vercel Frontend → Render Backend (Python) → Fetch from APIs → Compute → Return JSON
```

**Problems with this approach:**

1. **Cold starts are brutal.** Render's free tier spins down after 15 minutes of inactivity. First request after idle would take 30-60+ seconds while the container spun up, dependencies loaded, and data was fetched/computed.

2. **Every request re-computed everything.** Even with caching, computing indices like GLCI (which involves fetching from multiple APIs, resampling, factor models, etc.) took 10-20 seconds per request.

3. **Unreliable for a dashboard.** Users expect dashboards to load instantly. Waiting a minute for charts to appear is a terrible experience.

4. **Cost creep.** To avoid cold starts, you need a paid tier with "always on" instances. For a side project, that's unnecessary spend.

### Why the new architecture is better

The new architecture **pre-computes everything on a schedule**:

```
GitHub Actions (every 12h) → Fetch + Compute → Export JSON → GitHub Pages (static)
User Request → Vercel Frontend → GitHub Pages (static JSON) → Instant response
```

**Benefits:**

1. **Instant loads.** JSON is pre-built and served from GitHub Pages CDN. No computation at request time.

2. **Free forever.** GitHub Actions (free for public repos), GitHub Pages (free), Vercel (free hobby tier). No payment info required.

3. **Simpler mental model.** Data updates on a schedule. Frontend is just a static site that fetches JSON. No server to manage.

4. **Resilient.** If an API is down during the scheduled run, you still have the previous data. Users aren't blocked by upstream failures.

5. **Scalable.** Static files scale infinitely. Whether 1 user or 10,000, GitHub Pages handles it.

**Trade-off:** Data is only as fresh as the last scheduled run (every 12 hours). For a macro liquidity tracker where most series update daily/weekly, this is perfectly fine.

### Key design principle

> **Do expensive work once, serve cheap results many times.**

If your data doesn't change on every request, don't compute it on every request. Pre-compute, cache aggressively, and serve static assets whenever possible.

---

## Deployment

### Static pipeline (GitHub Actions + GitHub Pages + static frontend)

For a free, low-maintenance setup, the app can publish precomputed JSON to a `gh-pages`
branch and serve a static frontend (Vercel or GitHub Pages) without any external storage.

> Quick sanity: the scheduled job runs every 12h and publishes to `gh-pages`; the frontend reads from `latest/` on GitHub Pages.

1) Set secrets in GitHub:
   - `FRED_API_KEY` (for fetching data)
   - `GITHUB_TOKEN` is provided automatically by GitHub Actions.

2) GitHub Actions (`.github/workflows/update-data.yml`) runs every 12h:
   - `python scripts/update_data.py` (fetch + indices)
   - `python - <<'PY' ... compute_glci(save=True)` (GLCI)
   - `python - <<'PY' ... compute_risk_metrics(save=True)` (Risk metrics)
   - `python scripts/export_to_json.py --output data/export/latest --snapshot` (API-shaped JSON)
   - Force-publishes `latest/` and a few `snapshots/` to the `gh-pages` branch.

3) Frontend configuration:
   - Point to static JSON: `NEXT_PUBLIC_DATA_BASE_URL=https://<user>.github.io/<repo>/latest`
   - Local/dev API fallback still works via `NEXT_PUBLIC_API_URL`.

4) Artifacts structure (relative to the published root):
   - `latest/api/series/index.json`, `latest/api/series/{id}/index.json`, `latest/api/series/{id}/latest/index.json`
   - `latest/api/indices/index.json`, `latest/api/indices/{id}/index.json`
   - `latest/api/glci/index.json`, `latest/api/glci/latest/index.json`, `latest/api/glci/pillars/index.json`, `latest/api/glci/freshness/index.json`, `latest/api/glci/regime-history/index.json`
   - `latest/api/risk/index.json`, `latest/api/risk/{asset_id}/index.json`
   - Snapshots mirror the same layout under `snapshots/YYYY-MM-DD/`.

### Local development (optional live backend)

For local development, you can still run the FastAPI server:

```bash
uvicorn src.api:app --reload --port 8000
```

Then set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` to fetch from the live backend instead of static JSON.

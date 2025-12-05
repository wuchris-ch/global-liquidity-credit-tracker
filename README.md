# Global Liquidity Tracker

Track global liquidity and credit metrics from central banks, BIS, World Bank, and market data sources.

## 🌐 Live Demo

**[global-liquidity-credit-tracker.vercel.app](https://global-liquidity-credit-tracker.vercel.app)**

- [Dashboard](https://global-liquidity-credit-tracker.vercel.app/) — Overview of key liquidity metrics
- [GLCI Index](https://global-liquidity-credit-tracker.vercel.app/glci) — Global Liquidity & Credit Index (tri-pillar composite)
- [Liquidity Monitor](https://global-liquidity-credit-tracker.vercel.app/liquidity) — Fed balance sheet & net liquidity
- [Credit Spreads](https://global-liquidity-credit-tracker.vercel.app/spreads) — HY/IG spread analysis
- [Data Explorer](https://global-liquidity-credit-tracker.vercel.app/explorer) — Compare multiple series

## 🏗️ Architecture

Full-stack application with separated frontend and backend:

| Layer | Stack | Hosting |
|-------|-------|---------|
| **Frontend** | Next.js 16, React, Tailwind, shadcn/ui, Recharts | [Vercel](https://vercel.com) |
| **Backend** | FastAPI, pandas, statsmodels, scipy | [Render](https://render.com) |
| **Data** | FRED, BIS, World Bank, NY Fed APIs → Parquet | Render disk |

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

## Deployment

### Recommended: Vercel (frontend) + Render (backend)

#### 1. Deploy Backend to Render

1. Push your code to GitHub
2. Go to [render.com](https://render.com) and create a new **Web Service**
3. Connect your GitHub repo
4. Configure:
   - **Build Command:** `pip install -e .`
   - **Start Command:** `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
5. Add environment variables:
   - `FRED_API_KEY` = your FRED API key
   - `CORS_ORIGINS` = your Vercel URL (add after frontend deploy)
6. (Optional) Add a **Disk** mounted at `/opt/render/project/src/data` for data persistence

#### 2. Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) and import your repo
2. Set **Root Directory** to `frontend`
3. Add environment variables:
   - `NEXT_PUBLIC_API_URL` = your Render backend URL (e.g., `https://glci-api.onrender.com`)
   - `PYTHON_BACKEND_URL` = same as above
4. Deploy!

#### 3. Connect Them

After both are deployed:
1. Copy your Vercel frontend URL (e.g., `https://your-app.vercel.app`)
2. Go to Render dashboard → your backend → Environment
3. Set `CORS_ORIGINS` to your Vercel URL
4. Redeploy the backend

### Alternative: Everything on Render

Use the included `render.yaml` blueprint for one-click deployment of the backend.
For the frontend, create a second Render service as a **Static Site** or **Node** service.

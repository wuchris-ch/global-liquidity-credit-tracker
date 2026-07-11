# Global Liquidity Tracker

[![CI](https://github.com/wuchris-ch/global-liquidity-credit-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/wuchris-ch/global-liquidity-credit-tracker/actions/workflows/ci.yml)
[![Data pipeline](https://github.com/wuchris-ch/global-liquidity-credit-tracker/actions/workflows/update-data.yml/badge.svg)](https://github.com/wuchris-ch/global-liquidity-credit-tracker/actions/workflows/update-data.yml)

Track global liquidity and credit metrics from central banks, BIS, World Bank, and market data sources.

**Docs:** [Methodology & formulas](docs/METHODOLOGY.md) · [Data sources](docs/SOURCES.md) · [Operations runbook](docs/OPERATIONS.md) · [Sample output](docs/SAMPLE_OUTPUT.md) · [Claim → evidence map](docs/PROOF.md)

## Live Demo

**[global-liquidity-credit-tracker.vercel.app](https://global-liquidity-credit-tracker.vercel.app)**

The frontend is organized as a daily research note in six sections:

- [Today](https://global-liquidity-credit-tracker.vercel.app/), the 30-second brief: regime verdict, what changed, what it has meant, plumbing vitals
- [Index](https://global-liquidity-credit-tracker.vercel.app/glci), the GLCI deep dive: pillar decomposition, regime history, methodology
- [Flows](https://global-liquidity-credit-tracker.vercel.app/flows), a price-leadership gauge for AI/semis vs crypto vs gold vs small caps vs duration, each scored against its own norm, plus bitcoin priced in semiconductors
- [Playbook](https://global-liquidity-credit-tracker.vercel.app/playbook), forward returns by reconstructed regime with expanding thresholds, explicit timing, and confidence intervals
- [Plumbing](https://global-liquidity-credit-tracker.vercel.app/plumbing), net liquidity vs S&P 500, TGA/RRP components, credit spreads, central banks
- [Explorer](https://global-liquidity-credit-tracker.vercel.app/explorer), chart any series against any other, with preset overlays

(Old routes `/risk`, `/track-record`, `/liquidity`, `/spreads` redirect to the merged pages.)

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
2. Python scripts fetch data from all sources and compute indices (GLCI, Fed Net Liquidity, risk metrics, backtest track record, etc.).
3. Results are exported as static JSON and published to GitHub Pages.
4. Frontend fetches pre-built JSON instantly, no backend computation at request time.

All dashboard pages display data freshness indicators showing when the data was last updated. If the pipeline hasn't run recently or an upstream source is lagging, the freshness status will reflect that.

> **Important:** Do not delete the `gh-pages` branch! It stores the pre-computed JSON data served by GitHub Pages. Deleting it will break the production frontend. The branch is protected, but if you must modify branch settings, ensure `gh-pages` remains intact.

## Quick Start

```bash
# Install dependencies (incl. pytest/dev tools)
pip install -e ".[dev]"

# Verify the install without any API keys
python cli.py smoke

# Run the frontend against the published production data
cd frontend && npm install && npm run dev
```

The frontend will be available at http://localhost:3000. With
`NEXT_PUBLIC_DATA_BASE_URL` set (see `frontend/.env.example`) it reads the
pre-computed JSON from GitHub Pages — no local backend needed. To fetch and
compute data yourself, add a free FRED API key:

```bash
cp .env.example .env   # add FRED_API_KEY
python cli.py fetch --series fed_total_assets sofr --save
python cli.py compute --index fed_net_liquidity
python cli.py backtest --save
```

## Testing & Verification

Everything below runs offline (no API keys, no network):

```bash
make test    # 80+ unit tests: transforms, GLCI factor model, Sharpe/regime
             # metrics, backtest timing controls, export validation, and
             # shell-syntax checks on the GitHub Actions workflows
make smoke   # config integrity + numerics + local artifact validation
```

Network smoke against the published site:

```bash
make smoke-live   # validates the live GitHub Pages JSON and its freshness
```

CI runs the test suite and smoke checks on every push
([`ci.yml`](.github/workflows/ci.yml)), and the scheduled pipeline runs them
again as a gate before anything is published to `gh-pages`
([`update-data.yml`](.github/workflows/update-data.yml)).

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

### Exchange Rates & Inflation (for normalization)
- `fx_eurusd`, `fx_usdjpy`, `fx_gbpusd`, `fx_usdcny` - Major FX pairs
- `us_cpi`, `eu_hicp`, `jp_cpi` - Inflation indices

### Asset Prices (for the Flows page, Playbook and Risk dashboards)
- `sp500_price` - S&P 500 Index (FRED)
- `nasdaq100` - Nasdaq-100 Index (FRED)
- `semis_price` - Semiconductor ETF (SMH), AI-hardware proxy
- `russell2000_price` - Russell 2000 ETF (IWM)
- `gold_price` - Gold ETF (GLD)
- `silver_price` - Silver ETF (SLV)
- `bitcoin_price` - Bitcoin (FRED, Coinbase CBBTCUSD)
- `ethereum_price` - Ethereum (FRED, Coinbase CBETHUSD)
- `zcash_price` - Zcash (Yahoo Finance, ZEC-USD)
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

All three pillars are required. If any pillar cannot be fitted, the update
fails before saving or publishing instead of redistributing its weight. Pillar
scores are standardized to a common unit-variance scale before the fixed
40/35/25 weights are applied.

Regime classification: Tight (z-score < -1), Neutral (-1 to +1), Loose (> +1)

The displayed history is a reconstruction using the current source-data
vintage and factor estimates. It is not a point-in-time vintage history.
Append-only publication snapshots preserve what the model said on each run
from the snapshot feature's introduction onward.

## Risk by Regime Dashboard

The Risk by Regime dashboard shows how different asset classes perform under various GLCI liquidity regimes.

**Metrics computed:**
- Sharpe ratios (overall and by regime)
- Annualized returns and volatility
- Maximum drawdown
- Correlation with GLCI
- Rolling 252-day Sharpe ratio time series

**Assets tracked:**
- Large Cap Equities: S&P 500, Nasdaq 100
- AI Trade: Semiconductors (SMH)
- Small Cap Equities: Russell 2000
- Commodities: Gold, Silver
- Crypto: Bitcoin, Ethereum, Zcash
- Fixed Income: Long Bonds (TLT)

## Flows (Price Leadership)

The Flows page shows where liquidity-sensitive prices are leading by ranking
destinations (AI/semis, megacap tech, crypto, gold, small caps, long Treasuries,
broad equities) by how unusual their trailing 13-week return is against their own
trailing three-year history.

**Methodology (`src/indicators/flows.py`):**
- Prices collapse to weekly (Friday) closes; crypto's seven-day data and
  equities' five-day data land on the same grid
- Flow score = current 13-week return as a z-score against the asset's own
  trailing 156 weeks of overlapping 13-week returns (so a volatile asset has to
  rally harder to rank)
- 52-week correlation of weekly returns with weekly GLCI changes measures how
  liquidity-sensitive each destination has recently been
- Headline pair: bitcoin / SMH ratio, indexed to 100 three years back, i.e.
  "crypto priced in the AI trade"

This is a bid gauge built from prices, not flow-of-funds accounting; the page
says so explicitly.

## Track Record Dashboard

The Track Record dashboard backtests the GLCI regime classifier against forward asset returns to measure its predictive value.

**Methodology:**
- Expanding-window regime thresholds with a 52-week burn-in period
- Friday-to-Friday data grid, next-week entry, and 4, 13, and 26-week forward return horizons
- Compares GLCI regime classifier against an NFCI baseline
- Paired moving-block 95% confidence intervals over the full weekly row sequence

The expanding classifier prevents future composite observations from changing
past threshold labels. It does not make the upstream GLCI point-in-time: source
revisions and factor re-estimation can still change reconstructed history.

**Metrics shown:**
- Hit rate and median forward return within each reconstructed regime
- Edge: regime-subgroup hit rate minus the unconditional hit rate
- Subgroup hit-rate CIs and paired edge CIs computed separately in each resample
- An edge is highlighted only when its paired 95% CI excludes zero

## Project Structure

```
global_liquidity_tracker/
├── config/
│   └── series.yml              # Series and index definitions
├── src/
│   ├── data_sources/           # API clients (FRED, BIS, World Bank, NY Fed, yfinance)
│   ├── etl/                    # Data fetching and storage
│   └── indicators/
│       ├── glci.py             # GLCI index computation
│       ├── risk_metrics.py     # Risk by Regime metrics
│       ├── backtest.py         # Track Record expanding-window backtest
│       ├── dynamic_factor.py   # DFM latent factor extraction
│       ├── factors.py          # Feature engineering (FX, real, GDP scaling)
│       ├── transforms.py       # Data transforms (zscore, growth, impulse, gap)
│       └── aggregator.py       # Index aggregation dispatcher
├── data/
│   ├── raw/                    # Raw fetched data (parquet)
│   └── curated/                # Computed indices (parquet + JSON)
├── docs/                       # Methodology, sources, proof map, samples
├── tests/                      # Offline test suite (pytest): calculations + workflow syntax
├── scripts/
│   ├── update_data.py          # Scheduled fetch + compute
│   ├── export_to_json.py       # Static JSON export + validation
│   └── smoke.py                # No-key smoke checks (config/numerics/artifacts)
├── frontend/                   # Next.js dashboard
├── cli.py                      # Command-line interface
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

# Compute backtest track record (expanding-window, 52-week burn-in)
python cli.py backtest --save
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
   - `python scripts/update_data.py` (fetch + indices + GLCI publication snapshot)
   - `python - <<'PY' ... compute_risk_metrics(save=True)` (Risk metrics)
   - `python - <<'PY' ... compute_backtest(save=True)` (Track record backtest)
   - `python scripts/export_to_json.py --output data/export/latest --snapshot` (API-shaped JSON)
   - Publishes `latest/`, a few daily snapshots, and the durable GLCI vintage ledger to `gh-pages` with recoverable commit history.

3) Frontend configuration:
   - Point to static JSON: `NEXT_PUBLIC_DATA_BASE_URL=https://<user>.github.io/<repo>/latest`
   - Local/dev API fallback still works via `NEXT_PUBLIC_API_URL`.

4) Artifacts structure (relative to the published root):
   - `latest/api/series/index.json`, `latest/api/series/{id}/index.json`, `latest/api/series/{id}/latest/index.json`
   - `latest/api/indices/index.json`, `latest/api/indices/{id}/index.json`
   - `latest/api/glci/index.json`, `latest/api/glci/latest/index.json`, `latest/api/glci/pillars/index.json`, `latest/api/glci/trust/index.json`, `latest/api/glci/freshness/index.json`, `latest/api/glci/regime-history/index.json`
   - `latest/api/risk/index.json`, `latest/api/risk/{asset_id}/index.json`
   - `latest/api/backtest/track_record/index.json`
   - Snapshots mirror the same layout under `snapshots/YYYY-MM-DD/`.

### Local development (optional live backend)

For local development, you can still run the FastAPI server:

```bash
uvicorn src.api:app --reload --port 8000
```

Then set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` to fetch from the live backend instead of static JSON.

# Data Sources

Every series the pipeline ingests, where it comes from, and how it is
accessed. Client implementations live in `src/data_sources/`; the series →
source mapping is [`config/series.yml`](../config/series.yml).

## Access summary

| Source | Client | Auth | Rate limits | Used for |
|--------|--------|------|-------------|----------|
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | `fred.py` (fredapi) | free API key (`FRED_API_KEY`) | 120 req/min | US macro, CB balance sheets, spreads, rates, S&P 500 |
| [BIS SDMX](https://stats.bis.org/api-doc/v1/) | `bis.py` | none | be polite | Credit to non-financial sector (quarterly) |
| [World Bank](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392) | `worldbank.py` | none | none documented | Credit-to-GDP ratios (annual) |
| [NY Fed Markets API](https://markets.newyorkfed.org/static/docs/markets-api.html) | `nyfed.py` | none | none documented | SOFR, repo operations |
| Yahoo Finance | `yfinance_client.py` (yfinance) | none | unofficial, throttled | ETF & crypto prices |

## Series inventory

### Central bank balance sheets (FRED, liquidity pillar)

| Series ID | FRED ID | Frequency | Notes |
|-----------|---------|-----------|-------|
| `fed_total_assets` | WALCL | weekly | millions USD |
| `fed_treasury_general_account` | WTREGEN | weekly | millions USD |
| `fed_reverse_repo` | RRPONTSYD | daily | **billions** USD — converted ×1000 in the net-liquidity formula |
| `fed_reserve_balances` | WRBWFRBL | weekly | millions USD |
| `ecb_total_assets` | ECBASSETSW | weekly | millions EUR |
| `boj_total_assets` | JPNASSETS | monthly | millions JPY |
| `boe_total_assets` | BOGZ1FL714090005Q | quarterly | millions GBP |

### Funding rates & stress (FRED)

| Series ID | FRED ID | Frequency |
|-----------|---------|-----------|
| `sofr` | SOFR | daily |
| `fed_funds_rate` | DFF | daily |
| `euro_short_term_rate` | ECBESTRVOLWGTTRMDMNRT | daily |
| `ted_spread` | TEDRATE | daily (discontinued in 2022; historical context only, not a live model component) |
| `ice_bofa_us_high_yield_spread` | BAMLH0A0HYM2 | daily |
| `ice_bofa_us_ig_spread` | BAMLC0A0CM | daily |
| `vix` | VIXCLS | daily |
| `nfci` | NFCI | weekly (also the backtest baseline classifier) |
| `treasury_3m` | DGS3MO | daily (risk-free rate for Sharpe ratios) |
| `treasury_2y` / `treasury_10y` | DGS2 / DGS10 | daily |

The live GLCI stress pillar uses SOFR, the effective federal funds rate, HY OAS,
IG OAS, VIX, and NFCI. The separate USD Credit Stress composite uses HY OAS
(weight 1.0) and IG OAS (weight 0.5); its API ID remains
`usd_funding_stress` for compatibility.

### Money & credit (FRED + BIS + World Bank, liquidity/credit pillars)

| Series ID | Source ID | Frequency |
|-----------|-----------|-----------|
| `us_m2` | M2SL | monthly |
| `eu_m3` | MYAGM3EZM196N | monthly |
| `china_m2` / `japan_m2` | MYAGM2CNM189N / MYAGM2JPM189N | monthly |
| `us_bank_credit_total` | TOTBKCR | weekly |
| `us_bank_loans_leases` | TOTLL | weekly |
| `us_consumer_credit` | TOTALSL | monthly |
| `us_commercial_paper` | COMPOUT | weekly |
| `bis_credit_us/eu/cn/jp` | `Q.{cc}.P.A.M.XDC.A` (BIS SDMX) | quarterly |
| `wb_credit_gdp_us/eu/cn/jp` | FS.AST.PRVT.GD.ZS (World Bank) | annual |

### FX & inflation (FRED, normalization)

`fx_eurusd` (DEXUSEU), `fx_usdjpy` (DEXJPUS), `fx_gbpusd` (DEXUSUK),
`fx_usdcny` (DEXCHUS) — daily; `us_cpi` (CPIAUCSL), `eu_hicp`
(CP0000EZ19M086NEST), `jp_cpi` (JPNCPIALLMINMEI) — monthly.

### Asset prices (risk & track-record dashboards)

| Series ID | Source | Ticker/ID |
|-----------|--------|-----------|
| `sp500_price` | FRED | SP500 |
| `russell2000_price` | Yahoo | IWM |
| `gold_price` | Yahoo | GLD |
| `silver_price` | Yahoo | SLV |
| `bitcoin_price` | Yahoo | BTC-USD |
| `ethereum_price` | Yahoo | ETH-USD |
| `long_bond_price` | Yahoo | TLT |

## Failure handling

The scheduled pipeline **fails closed**: if any production-critical series
(the `priority_series` list in
[`scripts/update_data.py`](../scripts/update_data.py)) cannot be fetched, the
run aborts *before* exporting, so the previously published data stays live on
GitHub Pages rather than being replaced with gaps. Export completeness is
additionally enforced by `--require-production` in
[`scripts/export_to_json.py`](../scripts/export_to_json.py) and by the smoke
gate in the workflow.

Each dashboard page shows per-series freshness (`api/glci/freshness`);
sources that publish on a lag (BIS quarterly, World Bank annual) are expected
to show as older without being errors.

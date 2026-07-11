# Claim → Evidence Map

Each claim about this project, mapped to the code, configuration, and live
artifacts that substantiate it. Every "verify" command runs offline except
`smoke-live`.

| # | Claim | Evidence | Verify |
|---|-------|----------|--------|
| 1 | Central-bank liquidity dashboard with a **Next.js frontend** | [`frontend/`](../frontend) — Next.js App Router, React, Tailwind, shadcn/ui, Recharts; 7 pages under [`frontend/src/app/`](../frontend/src/app) | `make frontend-build` |
| 2 | **Scheduled Python pipeline** ingesting FRED, BIS, World Bank and NY Fed data | Clients in [`src/data_sources/`](../src/data_sources) (`fred.py`, `bis.py`, `worldbank.py`, `nyfed.py`, `yfinance_client.py`); orchestration in [`scripts/update_data.py`](../scripts/update_data.py); inventory in [SOURCES.md](SOURCES.md) | `python cli.py list series` |
| 3 | **Refreshed pre-computed JSON every 12 hours via GitHub Actions** | [`update-data.yml`](../.github/workflows/update-data.yml) — `cron: "0 */12 * * *"`, publishes to the `gh-pages` branch; [run history](https://github.com/wuchris-ch/global-liquidity-credit-tracker/actions/workflows/update-data.yml) | `make smoke-live` (checks published JSON is < 30 days old) |
| 4 | **Eliminates runtime compute** (static-first) | Export layer [`scripts/export_to_json.py`](../scripts/export_to_json.py) writes API-shaped JSON; frontend fetches static files via `NEXT_PUBLIC_DATA_BASE_URL` ([`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts)); design rationale in [README "Learnings"](../README.md#learnings) | open the [live site](https://global-liquidity-credit-tracker.vercel.app) — no backend round-trip |
| 5 | Deployed on **Vercel** | [live site](https://global-liquidity-credit-tracker.vercel.app); [`frontend/vercel.json`](../frontend/vercel.json) | — |
| 6 | **Composite GLCI index** | Tri-pillar latent-factor model: [`src/indicators/glci.py`](../src/indicators/glci.py) + [`dynamic_factor.py`](../src/indicators/dynamic_factor.py); pillar definitions in [`config/series.yml`](../config/series.yml); formulas in [METHODOLOGY.md §3](METHODOLOGY.md#3-global-liquidity--credit-index-glci) | `pytest tests/test_dynamic_factor.py` |
| 7 | **Fed net liquidity index** | `WALCL − WTREGEN − 1000·RRPONTSYD`: config in [`config/series.yml`](../config/series.yml), engine in [`src/indicators/aggregator.py`](../src/indicators/aggregator.py) | `pytest tests/test_aggregator.py` |
| 8 | **Risk-by-regime Sharpe ratios** | [`src/indicators/risk_metrics.py`](../src/indicators/risk_metrics.py) — Sharpe/return/vol/drawdown conditioned on GLCI regime, 7 asset classes; formulas in [METHODOLOGY.md §4](METHODOLOGY.md#4-risk-by-regime) | `pytest tests/test_risk_metrics.py` |
| 9 | Built with **pandas, statsmodels, scipy** | pandas throughout `src/indicators/`; statsmodels `DynamicFactor` + HP filter in [`dynamic_factor.py`](../src/indicators/dynamic_factor.py) / [`transforms.py`](../src/indicators/transforms.py); scipy via statsmodels & declared in [`pyproject.toml`](../pyproject.toml) | `python cli.py smoke` |
| 10 | Backtest with **explicit weekly timing controls** and paired edge CIs | Friday weekly grid, next-bar entry, the production 104-week rolling GLCI classifier, an expanding NFCI benchmark, and a full-calendar paired moving-block bootstrap in [`src/indicators/backtest.py`](../src/indicators/backtest.py); the methodology separately discloses current-vintage reconstruction | `pytest tests/test_backtest.py` |
| 11 | Calculation correctness is **tested** | [`tests/`](../tests) — 80+ offline unit tests over every published formula; gated in CI before any publish ([`ci.yml`](../.github/workflows/ci.yml), [`update-data.yml`](../.github/workflows/update-data.yml)) | `make test` |

Sample payloads from the live system are archived in
[SAMPLE_OUTPUT.md](SAMPLE_OUTPUT.md).

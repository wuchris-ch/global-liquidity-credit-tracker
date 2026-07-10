# Operations Runbook

How data gets to production, how to force a refresh, and how to verify what is
actually being served. For formulas and methodology see
[METHODOLOGY.md](METHODOLOGY.md).

## How a change reaches the site

There are two independent deploy paths, and both must run for a data-affecting
change to appear:

1. **Code** (frontend and pipeline): merging to `main` triggers a Vercel deploy
   of the frontend. This does **not** recompute any data.
2. **Data**: the `update-data.yml` workflow fetches sources, recomputes all
   indices, and publishes a normal commit with static JSON to the `gh-pages` branch. It runs
   every 12 hours on a schedule, or on demand.

The practical consequence: after merging a PR that adds or changes a series,
the site keeps serving the previous JSON until the next pipeline run. Trigger
one manually:

```bash
gh workflow run update-data.yml
gh run watch        # or: gh run list --workflow=update-data.yml
```

## Caching: why the site can lag a publish by up to 10 minutes

GitHub Pages serves the JSON with `cache-control: max-age=600`, so both the
CDN edge and the visitor's browser may hold a pre-publish payload for up to
10 minutes. The frontend revalidates its cached copies on load
(`cache: "no-cache"` in `frontend/src/lib/api.ts`), but third-party curls and
the CDN itself still honor the TTL. To see the truly current payload, bust the
cache:

```bash
curl -s "https://wuchris-ch.github.io/global-liquidity-credit-tracker/latest/api/glci/index.json?cb=$(date +%s)" | head -c 400
```

## Endpoint layout

Static JSON lives under `latest/` on `gh-pages` and mirrors the API routes,
with one directory per endpoint containing `index.json`:

| Page | Endpoint |
|------|----------|
| Today / Index | `/api/glci/index.json`, `/api/glci/latest/index.json`, `/api/glci/pillars/index.json`, `/api/glci/trust/index.json` |
| Flows | `/api/flows/index.json` |
| Playbook (risk) | `/api/risk/index.json` |
| Playbook (backtest) | `/api/backtest/track_record/index.json` |
| Plumbing | `/api/indices/fed_net_liquidity/index.json` etc. |

Note the backtest path: it is `/api/backtest/track_record/index.json`, not
`/api/backtest/index.json` (which 404s).

## Adding a new asset

1. `config/series.yml`: register the series (FRED has Coinbase series for BTC
   and ETH only; other crypto comes from Yahoo via `yfinance`).
2. `src/indicators/risk_metrics.py`: add to `ASSET_CONFIG` (drives the risk
   dashboard and the Playbook backtest).
3. `src/indicators/flows.py`: add to `FLOW_DESTINATIONS` (drives Flows).
4. `scripts/update_data.py`: add to `asset_series`.
5. `scripts/export_to_json.py` and `src/api/server.py`: add to `CATEGORY_MAP`.
6. Optional prose: `frontend/src/lib/flows-brief.ts` (`PROSE_NAMES`).

The frontend renders asset lists dynamically, so no UI changes are needed.
After merging, run the data workflow (see above).

## Verifying a publish

```bash
# Offline checks against a local export
python scripts/smoke.py

# Live checks against the published gh-pages JSON
python scripts/smoke.py --live
```

The pipeline aborts before publishing if any production-critical series fails
to fetch, so a bad upstream day leaves the last good publish intact. Asset
prices (gold, crypto, ETFs) are best effort: a failed fetch skips that asset
and prints a warning in the run log instead of blocking the publish.
All three configured GLCI pillars are also required. A pillar-model failure
aborts before save or publication; the pipeline never substitutes a partial,
reweighted composite.

`scripts/update_data.py` also computes the GLCI and appends its latest state to
`data/curated/indices/glci_vintages.parquet`. Snapshot identity includes both
the computation timestamp and signal date, so a later revision of the same
signal date is retained rather than replacing the earlier publication. The
workflow restores that ledger from `gh-pages/state/`, verifies its row count
against the prior trust payload, and refuses to publish if established state is
missing or regresses. The first publish is the only automatic bootstrap.

## Things that will break production

- Deleting the `gh-pages` branch. It holds every published payload; the
  frontend reads it directly.
- Renaming endpoint directories without updating `frontend/src/lib/api.ts`.
- Removing a priority series from `config/series.yml` while
  `scripts/update_data.py` still lists it: the publish gate will fail every
  scheduled run until they agree.

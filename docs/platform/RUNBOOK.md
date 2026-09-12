# Research workbench runbook

The research service is separate from the published static dashboard. It writes under `data/research`; it does not read or overwrite the production raw series or export directory. Current implementation status and measured limits are in [STATUS.md](STATUS.md).

## Start locally

From the repository root:

```sh
make research-setup
make research-demo
make research-api
```

In another terminal:

```sh
cd frontend
npm run dev
```

Open `http://localhost:3000/research`. The API binds only to `127.0.0.1:8000`. Its interactive contract is at `http://127.0.0.1:8000/docs`. Local mode accepts loopback clients and the configured local browser origins. It does not require a token.

The five numbered controls import the authentic GDP evidence, save April, save May, compare, and explain. The period is January 1, 2024, FRED's observation date for Q1. Information dates are April 25 and May 30. The values are 1.6 and 1.3 percent at an annualized quarterly rate; their difference is -0.3 percentage points. A 1.5 threshold changes from true to false. These are source estimates imported now, not historical predictions or platform publications.

Use Sources to acquire another series or register recurring collection. Use Workbench to select its information date, period and transformation. Opening a saved result never updates its inputs. Choose a different date and save another version to compare. Notes stay on their run. Changes compares saved inputs to the newest captured source information date, including backfills imported out of order.

## Dates, units and coverage

- A source query requires an explicitly captured FRED information date and a single complete partition covering the requested observation range. Two checked dates do not prove coverage between them. Unknown coverage returns HTTP 422 without a current-data fallback.
- Platform queries require a timezone-qualified timestamp. Only manifests committed by that timestamp qualify. Adding source vintages now cannot produce platform evidence for 2024.
- BIS, World Bank and NY Fed support forward capture. Their older observations are historical observations retrieved now, not verified historical vintages. World Bank archive editions are not admitted until an actual archive contract is implemented and verified.
- Missing or retracted values remain null. Calculations do not silently fill gaps or resample different calendars. Window lengths are observation rows. Annualization uses the explicit periods-per-year input.
- FRED metadata is fetched for the requested information date. Units and frequency must match. Units belong to snapshots: WTREGEN's May 2024 vintage uses billions of U.S. dollars, while the current series uses millions. Net liquidity converts each USD input to millions before subtraction.
- BIS verifies the complete dimension key, unit measure and unit multiplier. World Bank admits the reviewed annual GDP/credit/money indicator unit contracts in `ingestion.py`. A new indicator requires extending that registry after source review.
- A partition cannot exceed 200,000 observations; a query cannot exceed 100,000 rows. The UI chart shows at most 1,000 points. Full results remain in exports. This release does not merge adjoining partitions into an invented complete history.

## Acquisition and jobs

Provide `FRED_API_KEY` only in the service environment or a local, ignored `.env`. Do not put it in recipes, checked-in files or a browser form.

```sh
uv run macro-research ingest config/research/fred-assets.json
uv run macro-research worker --once
uv run macro-research backfill config/research/fred-assets.json --from-date 2024-04-01 --to-date 2024-06-01
uv run macro-research worker
```

Edit the example's observation range and information date before using it for a different partition. Backfills enumerate source dates and create an idempotent job per partition. Complete jobs are not re-fetched by restarting the worker. Scope or unit changes create distinct requests. A vintage spanning a historical unit change may need separate, correctly declared requests.

The API runs one embedded worker by default. Set `RESEARCH_WORKER=0` if using the separate worker command. `RESEARCH_WORKSPACES` lists shared workspaces for the embedded worker. Schedules reconcile missed collection slots on restart and preserve the requested historical observation start for full-history revision comparisons. This deliberately trades more bandwidth for simple, verifiable reconciliation. It does not claim incremental source change feeds.

Jobs move through planned, running, succeeded, retry_wait, quarantined, exhausted or cancelled. Cancel from the job details or `POST /jobs/{id}/cancel`; the commit fence prevents cancelled work from publishing. A generation and expiry fence guards final manifest/model/run commits in the same database transaction. A killed worker can leave unreferenced immutable objects; it cannot make them visible through a committed head. HTTP retry ownership stays in the transport, with bounded attempts, timeouts and Retry-After handling. The durable job retries a failed partition up to four attempts. Request spacing is per collector process, so use one acquisition worker per provider budget.

Inspect failures in Jobs or `/api/v1/research/jobs`. Source schema/unit failures are quarantined. Fix the declaration and create a new request. Worker diagnostics log error classes and job IDs, not raw exception text or credential-bearing URLs. Never repair evidence in place.

Release dates are registered through `PUT /releases/{id}`. Scheduled, late, released and cancelled are distinct states. This release has no automatic provider holiday-calendar integration. A schedule continues bounded collection if no release calendar is registered.

## Models and outcomes

`POST /models` accepts `cutoff`, `start`, `interpretation` and an `inputs` mapping from every configured GLCI component ID to a research Query. The API pins manifests before queuing. The model fetcher has no network or mutable-store fallback. It validates source identity/frequency and explicitly normalizes reviewed historical unit changes to the existing model's unit convention.

Use `interpretation: reconstruction` for current-vintage historical calculations. `source_vintage` requires every query to use verified source coverage no later than the training cutoff. Today's forward-captured BIS data cannot satisfy that historical claim. The existing public GLCI is unchanged.

Each pillar stores prepared training values, original feature matrix, fitted scaler, PCA components, constrained loadings, factor orientation and projection normalization as JSON. `replay_factor` verifies the saved numerical projection at absolute and relative tolerances of 1e-8. There are no executable pickle artifacts. Code, config, package and lock hashes accompany the complete model run. The runner uses the explicit PCA path and refuses unsupported fit artifacts.

An opt-in end-to-end reconstruction check collects its own isolated inputs:

```sh
uv run python -m scripts.research_model_check --as-of 2026-09-10 --cutoff 2024-05-31
```

This contacts the configured providers and needs a FRED key. It writes only `data/research-model-check`. It is not a historical forecasting evaluation.

`POST /outcomes` references a saved model, signal date, entry/exit dates and a price capture. Accepted price evidence is JSON with `schema_version: adjusted-close/1`, `target`, and `prices: [{date, value}]`. The record must mature before acceptance, match the captured prices, and use the first captured close strictly after the signal. The system cannot prove that a manually prepared price file contains every trading session; the capture producer is responsible for complete session coverage. An automatic adjusted-price provider adapter is not included. Corrections append versions; the first matured outcome remains fixed. Counts distinguish unique signal dates from recomputations.

No forecast-accuracy claim is made. Target-specific predictions, non-overlapping evaluation splits, baselines and uncertainty are required before publishing such a claim. The outcome summary states this gate explicitly.

## Exports, replay and recovery

JSON bundles include source captures, pinned inputs, recipe, numerical result and environment hashes. CSV includes units, run and manifest IDs; download the JSON bundle alongside CSV for full evidence and date semantics. Parquet includes a manifest in its metadata. HTML is a deterministic report. Exporting requires reviewed redistribution rights for every input. `POST /publications` freezes a private workspace report with its actual creation time; it does not publish to the public internet.

```sh
uv run macro-research replay /absolute/path/to/analysis.json
uv run macro-research backup /absolute/path/to/new-backup-directory
uv run macro-research --data data/research-restored restore /absolute/path/to/new-backup-directory
uv run macro-research --data data/research-restored catalog
uv run macro-research retention
```

Backups include a transactionally read control snapshot, immutable objects and a file-hash manifest. Verification checks referenced capture and partition dependencies. Restore requires an empty destination and verifies hashes first. A backup is sensitive because it contains all workspaces; keep access restricted. PostgreSQL backups through this command use a single SELECT snapshot of the control table. Both SQLite and PostgreSQL use the same object layout. Retention is a dry-run only and deliberately deletes nothing.

A different calculator hash stops replay. Restore the recorded implementation/environment rather than relabeling a changed calculation as a successful replay. Hashes detect corruption; they are not cryptographic signatures from a provider.

## Shared operation

The database adapter supports PostgreSQL using `RESEARCH_DATABASE_URL=postgresql+psycopg://...`. For a private shared service, configure `RESEARCH_AUTH_MODE=oidc`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `RESEARCH_ORIGINS` and `RESEARCH_WORKSPACES`. Issuer/JWKS require HTTPS, tokens require RS256 and verified issuer/audience/expiry, and an active database membership is required for the requested workspace. Viewer, editor and owner roles are enforced by the API. Revocation applies on the next request.

Provision memberships from the trusted service environment:

```sh
uv run macro-research --workspace team-one member AUTHENTICATED_SUBJECT --role viewer
uv run macro-research --workspace team-one member AUTHENTICATED_SUBJECT --revoke
```

The container recipe defaults to OIDC and a non-root user. Mount persistent object storage and use a durable PostgreSQL service. TLS termination, an actual OIDC login experience, secrets management, provider budgets and hosted backups require deployment-specific configuration. Do not expose local anonymous mode through a proxy. Database access itself is trusted service access; workspace isolation is implemented in scoped repository operations and API authorization, not PostgreSQL row-level security.

No hosted service, OIDC tenant or paid resource has been provisioned. Local signed-token and PostgreSQL isolation tests do not establish production readiness. Keep the existing public static dashboard deployment separate until a deliberate release.

The public frontend presents the Research Atlas at `/research` when no `NEXT_PUBLIC_RESEARCH_API_URL` is configured. Its three fixed historical studies use nine explicit FRED vintage captures, bundled public observations and browser calculations. It never contacts a private research API. `/research/atlas` exposes the same published collection in development. Development mode and an explicitly configured research API retain the private workbench at `/research`. Only configure a hosted private service after verifying authentication, the allowed browser origin and persistent storage. No production database migration is required.

The atlas collector, `python -m scripts.publish_research_atlas`, requires `FRED_API_KEY` in its environment. It reads no private workspace data. Review new captures before committing: `frontend/src/lib/research-atlas.json` must match `frontend/public/research/evidence/atlas.json`, and all original response hashes must pass `npm run test:research`. Raw source responses, their retrieval times and allowlisted request parameters are published deliberately. Updating the collection is a separate reviewed action, not part of the scheduled dashboard feed.

## Verification commands

```sh
uv run pytest tests
make research-types
cd frontend && npm run test:research && npm run lint && npm run build
uv run macro-research evaluate
make research-benchmark
```

Run the final two commands from the repository root. The assistant is a bounded deterministic interpreter, with no external model calls or API costs. Its 40-case corpus is a regression suite, not independent held-out proof of agent quality. The benchmark reports workload, environment, logical query hash, memory and latency. It does not manufacture cold-cache or hosted results.

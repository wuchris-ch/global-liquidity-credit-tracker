# Research and current-state assessment

[Plan entry point](README.md) | [Architecture](ARCHITECTURE.md) | [Implementation](IMPLEMENTATION.md)

Evidence checked September 11, 2026. Source documentation describes a provider's contract; the observations below describe what was actually checked. No production ingestion workflow, deployment, paid service, or model evaluation was started.

## 1. What exists and should be preserved

The planning worktree and `/Users/chris/Projects/global-liquidity-credit-tracker` both resolved to `c72abdad8dacc346aaa277ae4e54c3f3c546e853`, the merge of PR 24. Both were initially clean. Recent mainline changes include sector flows and rotation, source-identity hardening and model-integrity fixes. Local environments and ignored datasets need not be identical; the original Python environment was reused to run tests against this worktree, with a temporary `DATA_PATH`. No ignored data were migrated.

| Area | Inspected implementation | Gap or implication |
|---|---|---|
| Frontend | Next.js App Router, React, TanStack Query, Recharts, Tailwind. Lockfile resolves Next 16.0.7, React 19.2.1, TypeScript 5.9.3. [API client](../../frontend/src/lib/api.ts) supports static and backend modes; static mode filters full-history payloads client-side | Preserve the working static path. Historical queries need a separate contract because the static URL builder strips query parameters |
| Product | Today, Index, Leadership, Playbook, Plumbing and Explorer are navigation labels. Additional legacy route files exist | Avoid describing route count as product breadth. Make Research and Changes discoverable, with redirects for existing links |
| Ingestion | [Updater](../../scripts/update_data.py) fetches priority series and assets; GLCI computation can fetch further inputs. Full history requested with `start_date=None`. [Fetcher](../../src/etl/fetcher.py) retries series and validates declared FRED metadata contracts | No durable per-partition checkpoint or shared run manifest. Repeated fetches can represent different upstream states within one computation |
| Storage | [Storage](../../src/etl/storage.py) rewrites raw Parquet; `append_raw` deduplicates by observation date, keeping last. Curated files are overwritten | Neither immutable transport data nor revision history. A country dimension cannot safely share a date-only key |
| Signal ledger | `append_signal_snapshot` keeps the first row per `(computed_at, signal_date)`, writes a temporary file and replaces the ledger. [Workflow](../../.github/workflows/update-data.yml) restores the previous ledger and guards missing/regressed state | Logically append-only rows, physically a replaced file. No multiwriter lock, object hashes, dependency manifest or independently observed publication timestamp. Retain the ledger as legacy evidence |
| FRED | [Client](../../src/data_sources/fred.py) calls `Fred.get_series` with observation start/end only | Historical observation dates do not select historical vintages. Missing values are dropped, so a later retraction is not represented explicitly |
| Other sources | [BIS](../../src/data_sources/bis.py) hardcodes the credit dataflow; its parser collapses dimensions into date/value. [World Bank](../../src/data_sources/worldbank.py) requests one page of 1,000 records and defaults end year to 2025 if start is supplied. [Base client](../../src/data_sources/base.py) returns five columns, discarding country and operation fields | Preserve full source keys, country, units, observation status and metadata versions. Pagination and period-range correctness are foundational fixes, not optional enterprise features |
| NY Fed | [Client](../../src/data_sources/nyfed.py) fetches SOFR via `last/365`, then filters dates; no unrestricted backfill. It drops the provider's `revisionIndicator`. Several operation fields default missing amounts to zero | History coverage can silently truncate. Distinguish zero, missing, retracted and no activity |
| Reliability | [Shared HTTP session](../../src/data_sources/http.py) handles GET retry/backoff and Retry-After for clients using it. BIS, World Bank and NY Fed inspected clients use plain sessions. Fetcher adds another retry layer | Standardize retry budgets and timeouts without multiplying retries across layers; do not retry schema/identity violations indefinitely |
| Calculations | Deterministic net liquidity with explicit unit conversion. Three-pillar GLCI, constrained factor loadings, completed weekly grids and availability lags. [Factors](../../src/indicators/factors.py), [factor model](../../src/indicators/dynamic_factor.py), [GLCI](../../src/indicators/glci.py) | Preserve formulas and tests. Full-sample fitting/scaling still means vintage selection alone will not create a historical walk-forward model |
| Quality | [Quality helpers](../../src/data_quality.py) expose coverage, stale and excluded inputs. Frequency-specific age allowances: daily 10, weekly 21, monthly 62, quarterly 150, annual 450 days | Useful existing guardrails. Observation age is not release lateness: quarterly data may correctly remain unchanged for months |
| Evidence | [Backtest](../../src/indicators/backtest.py) has timing, bootstrap, multiplicity and readiness controls. [Live evaluation](../../src/indicators/live_evaluation.py) selects first computation per signal date and later weekly price bars | Keep descriptive and evidence-ready labels. Current adjusted prices can change historical outcomes. Computation time is not proof of public availability |
| Serving | [FastAPI server](../../src/api/server.py) already exists with local CORS and an in-memory GLCI cache. Static exports mirror API-shaped endpoints | Reuse service modules, but new read-only research GET routes should read committed data and never fetch upstream or fit a model implicitly |
| Delivery | Actions every 12 hours; tests, strict export validation and smoke precede gh-pages publication. Vercel frontend is independent; gh-pages deployments disabled in Vercel config | Last-good publication behavior is valuable. Mixed frontend/data versions and cache propagation need release manifests and compatibility checks |
| Retention | Workflow copies only the new export aside, then clears gh-pages working files; old dated export directories are not explicitly restored before the three-snapshot pruning block | The code does not establish a durable three-release archive. Git history may retain older public JSON, but this is not raw source provenance or a retention guarantee |

### Tests, records and live observation are different evidence

The existing suite passed here: **209 passed, one skipped in 47.50s**. The skipped test is `TestValidateRequiredExports.test_valid_local_export_passes` in `tests/test_export.py` when a full export is absent. No full production data refresh was run to satisfy it. No new frontend build was necessary for planning-only changes; earlier tasks recorded passing frontend checks, but that is not a fresh measurement.

The live Today page was opened in the in-app Browser. It rendered the brief, neutral/softening conditions, stale-input disclosures and revision history. The public [trust endpoint](https://wuchris-ch.github.io/global-liquidity-credit-tracker/latest/api/glci/trust/index.json) returned HTTP 200, `point_in_time=false`, 108 snapshots, nine distinct weekly dates and 99 later computations. Last computation was `2026-09-11T01:57:04.222698Z`. For September 4, the first stored GLCI was 108.17683369929921 and the latest 108.63969003825642, a difference of about 0.463 points, with neutral classification unchanged. [Saved evidence](evidence/live-trust.json).

This demonstrates changing recorded model output. It does **not** identify whether a particular raw series revision, a newly released observation, or factor refitting caused the difference. That missing attribution is a strong real-world reason for the proposed platform. A single page visit is not a full usability, accessibility or production-health audit.

### Relevant project task history

Read via task tools after locating project-specific tasks in the local task index:

- **Harden institutional tooling**, July 14, 2026 (`019f5ff3-7abd-7fa2-8983-a50fc2f728c1`): corrected a mislabeled central-bank series and BoJ units; added source contracts, availability lags and evidence gates. Its recorded conclusion explicitly identified historical source vintages, model refits and immutable outcomes as unfinished. Treat the historical test/performance counts in that task as recorded results only.
- **Research sector rotation flows**, July 14 (`019f61c7-36d0-74b1-a98f-cf4522c7e4c1`): the user asked why the merged feature was absent in production, then asked which tab contained it. The task documented separate frontend/data release paths and later verified 11 sectors. This motivates release compatibility checks and clearer navigation, not just more charts.
- **Find UI and UX improvements**, September 4 (`01a06de8-6db1-7152-8e0e-bbc59c38a2f0`): interrupted scan, without a completed recommendation or verified change. Do not treat it as an approved redesign.

## 2. Source constraints and recommended acquisition policy

### FRED and ALFRED: first historical adapter

[Real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) separate when an observation applies from when it was known. Use explicit as-of dates. [Vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html) list changes or new observations, excluding releases with no change. Paginate their 10,000-item maximum.

[Observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) support real-time ranges, selected vintage dates, initial releases, and new/revised observations. Start with single-date snapshots and paginated observations, then optimize to change feeds after equivalence tests. Preserve original value strings and missing markers. The observation limit is 100,000 per request; selected-vintage limits depend on format/output type. Do not mistake an API response's query-clipped real-time end for the actual lifetime of a value.

[ALFRED help](https://alfred.stlouisfed.org/help) says source release dates are preferred, then provider dates, then first availability in FRED when neither is known; updates are typically added within one business day. Therefore a vintage date is evidence at day precision, not a guaranteed original 08:30 release timestamp or proof the application had ingested it then. Verify historical coverage per series, not globally.

[Release dates API](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html) is useful for expected releases, including dates without available data when requested. Store schedules separately from observed releases. Recheck revisions to schedules and holidays. A calendar event alone never unlocks a value.

[API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html) preserve third-party data rights and allow adjustable usage limits. No stable numeric request-rate entitlement was verified in these documents. Start at a configurable, deliberately conservative 30 requests/minute with concurrency one; that is our policy, not a provider promise. [Key documentation](https://fred.stlouisfed.org/docs/api/api_key.html) requires application users to use their own keys. Use Chris's key locally; review the intended server-side redistribution and application model before a shared commercial service. Never ship a key in browser code or exported manifests.

### BIS: global credit, with honest historical gaps

The [API specification](https://stats.bis.org/api-doc/v2/) and [portal tools](https://data.bis.org/help/tools) provide SDMX data/metadata access and release monitoring. The current repository's v1 route returned HTTP 200 for US private credit, Q1 2024, with dataflow `BIS:WS_TC(2.0)` and value `41167.637`. [Probe](evidence/source-probes.json). A documentation URL containing v2 is not evidence that the existing v1 route is broken.

Persist full dataflow, agency/version, dimension key, unit multiplier, status flags and DSD/codelist hashes. A dataflow version is a structure version, not automatically an observation vintage. No comprehensive arbitrary-date historical vintage service for this configured credit series was verified. Treat today's download as current data; collect immutable snapshots going forward. Archived releases can be admitted individually after their timestamp, values and coverage are validated.

Use the [release calendar](https://data.bis.org/release-calendar?view=list) and RSS described in portal help. Release dates are upper bounds in the calendar, so allow early observations. Retain the current 90-day lag only as a labeled approximation for reconstruction, never as proof of actual historical availability. Use one request at a time and a configurable request budget until actual limits are established. [BIS terms](https://www.bis.org/about/terms-conditions) direct statistical reuse to the [About BIS statistics](https://www.bis.org/statistics) terms; maintain dataset-specific attribution and verify permitted redistribution before public raw exports.

### World Bank: annual context and archival versions

[Basic calls](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581) document pagination, dates, source selection and footnotes. The live one-row probe returned `pages=265` for all-country 2024 GDP and included an aggregate region, not a country. Admit only intended country/aggregate identities and persist footnotes and nulls. Fix the hardcoded end year and preserve country through standardization.

[WDI resources](https://datatopics.worldbank.org/world-development-indicators/user-guide.html) describe archived database editions from 1989 onward. A live metadata request confirmed source 57 as `WDI Database Archives`, with four concepts and `lastupdated=2025-10-29`. This verifies archive discovery, **not** that every desired indicator/country/version is retrievable or has precise release times. Use [advanced API discovery](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries) to inspect its concepts and versions before promising coverage. A database's `lastupdated` field is not a row-level release date.

Use low-frequency metadata checks, fetch changed releases, and reconcile full history after updates because annual values can be revised far back. No universal numeric rate limit was verified. [Dataset terms](https://www.worldbank.org/ext/en/legal/terms-conditions/datasets) default to CC BY 4.0 with additional terms and third-party exceptions; store indicator-level license metadata. Do not assume every World Bank-hosted observation has identical rights.

### NY Fed: publication timing matters

The [Markets API](https://markets.newyorkfed.org/static/docs/markets-api.html) is the source interface; its JavaScript documentation was not extractable by the text browser. A direct live SOFR request succeeded and returned `effectiveDate`, `percentRate`, volume, percentiles and `revisionIndicator`. Preserve these fields. The date labels the rate's reference period, not ingestion or publication time.

[Reference-rate methodology](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) describes morning publication and possible same-day revisions around 14:30 ET. Capture both scheduled windows if intraday history becomes a requirement. A twice-daily collector cannot guarantee seeing every intermediate value. Verify date-search limits and inclusive boundaries in adapter contract tests; the current `last/365` client cannot fulfill an unrestricted backfill. No all-vintage archive or universal numeric API rate limit was established. Apply the [NY Fed terms](https://www.newyorkfed.org/privacy/termsofuse), with dataset-specific review before redistribution.

### Existing market and flows inputs

Keep Yahoo prices, State Street issuance estimates and OCC activity as separate evidence types. [Existing source and methodology inventory](../MARKET_FLOWS.md) already distinguishes adjusted prices, estimated net issuance and non-directional cleared options activity. No archived initial versions or complete redistribution rights for those inputs were verified in this task. Mark their imported historical data as current reconstruction; forward captures establish only collected versions. Keep new public raw-data export disabled for unreviewed licenses. Do not infer money entering an asset from price appreciation or buy/sell intent from cleared option volume.

## 3. Design research and alternatives

| Reference | Relevant documented idea | Adoption decision |
|---|---|---|
| [Macrobond revision history](https://help.macrobond.com/tag/vintage/) and [revision columns](https://help.macrobond.com/technical-information/product-versions/macrobond-1-26/) | Visible vintages and start/end history coverage | Use this interaction pattern: first-release versus revised chart, availability badge and saved analysis. Do not claim comparable dataset coverage or buy a license for this task |
| [OpenBB custom backends](https://docs.openbb.co/workspace/developers/data-integration) | An API and widget contracts connect research data to reusable UI | Keep a documented API boundary and consider an optional widget adapter later. Do not replace the current frontend or proxy every vendor through OpenBB |
| [DuckDB Parquet access](https://duckdb.org/docs/stable/data/parquet/overview) | Query columnar files directly | Add embedded analytical reads over immutable partitions. SQLite manages small mutable app/job state locally |
| [DuckDB concurrency](https://duckdb.org/docs/lts/connect/concurrency) | Single-process writer model and explicit multi-process coordination | Do not share a writable DuckDB file across a scheduler and API processes. Each reader opens immutable committed files; one coordinator publishes manifests |
| [OpenLineage object model](https://openlineage.io/docs/spec/object-model/) | Dataset, job and run identity, with extensible facets | Adopt compatible identifiers and input/output run references. A separate lineage server is unnecessary initially |
| [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) | Scheduled jobs may be delayed or dropped | Retain Actions for coarse refresh; an exact release-time guarantee needs a different scheduler and measured reliability |
| [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) | 1 GB published-site limit and restrictions on commercial SaaS hosting | Keep compact public derived artifacts there for the personal project; move durable raw history to object storage and team hosting to an appropriate service |

The pattern is immutable files plus a small transactional control plane, not a miniature distributed warehouse. Begin with Parquet and a manifest; consider an established table format only after measured concurrent writers, schema evolution or file-count problems justify its operational cost. Storage time travel does not create economic release-time history.

### Ideas from Chris's other repositories

Read-only inspection, no tests or deployments in those projects:

| Repository / inspected revision | Concrete inspected area | Useful transfer and boundary |
|---|---|---|
| `distributed-task-scheduler` / `71af5c7` | `internal/worker/processor.go`, queue interface, README | Leases, retries with jitter, dead-letter handling and run audit. Borrow state-machine principles; do not add Go/Redis/Postgres merely to call a dozen daily APIs. The inspected ACK and database writes are separate, so do not cite it as proof of exactly-once execution |
| `databricks-like` / `72f14cc` | `minidelta/transaction.py`, README | Read-version checks and file commit manifests help explain atomic publication. Educational MiniDelta is a learning reference, not a recommended production dependency or verified ACID implementation for this system |
| `DSPy-Supabase-RAG` / `85a5d7e` | `retriever.py`, `evaluation.py`, README | Separate lexical/semantic retrieval, reranking and judging. Start with exact series identifiers and keyword retrieval; add vector retrieval only after a measured retrieval benchmark. Its medical-domain scores do not transfer to macro research |
| `agent-eval-k3s` / `9b68ab5` | `docs/blackbox-evaluation.md`, `src/agent_eval/blackbox/scoring.py` | CLI/HTTP or recorded-response evaluation with exact/subset checks and optional judging. Reuse a black-box adapter; Kubernetes is not required. Add macro-specific numeric tolerance checks outside its current exact/subset scorer or through an explicit extension |

## 4. Authentic revision demo

Use **2024 Q1 US real GDP annualized quarter-over-quarter growth**, FRED `A191RL1Q225SBEA`, observation date `2024-01-01`. This is a new research-demo series, not an existing GLCI input.

Two read-only calls made with an existing local FRED credential returned:

| Information date requested | Observation | Value | Result |
|---|---|---:|---|
| 2024-04-25 | 2024 Q1 | 1.6% SAAR | HTTP 200 |
| 2024-05-30 | 2024 Q1 | 1.3% SAAR | HTTP 200 |

Requests set `realtime_start=realtime_end` to each date and constrain the observation to January 1. [Saved requests, response bodies and transport hashes](evidence/fred-gdp-vintages.json) omit the credential. Independent corroboration: BEA's [advance estimate](https://www.bea.gov/news/2024/gross-domestic-product-first-quarter-2024-advance-estimate) and [second estimate](https://www.bea.gov/news/2024/gross-domestic-product-first-quarter-2024-second-estimate-and-corporate-profits). The latter attributes the downward revision primarily to consumer spending. That is a sourced explanation; a numerical component attribution would require the corresponding vintage component tables.

Proposed demo sequence:

1. Create a saved analysis **“US growth revision notebook”** today with information date April 25, 2024. Display original estimate 1.6%, unit, observation period and archived-source coverage. The save timestamp is today.
2. Add an illustrative, explicitly user-defined `growth >= 1.5%` threshold. The deterministic result is `true`. This threshold is a UI demonstration, not an economic regime or trading rule.
3. Compare with May 30. Result is 1.3%; revision is `1.3 - 1.6 = -0.3` percentage points and threshold result becomes `false`. Show both saved versions; do not overwrite the original.
4. Keep the recipe fixed to attribute this change to the data revision. Link the exact API evidence and BEA release. Ask the assistant why the displayed conclusion changed; it must cite these inputs and the deterministic difference.
5. Ask “What did our platform say in April 2024?” Answer: **No recorded platform publication is available for that date. This is a historical source reconstruction performed now.**

Do not treat the query-clipped real-time intervals in these two responses as a complete vintage timeline. A full backfill must enumerate all relevant changes and verify missingness between them. For this demo, the two directly verified dates are enough. Intraday timing remains unavailable from these FRED responses.

## 5. Methodological requirements that change engineering

Historical research has two independent leakage risks: revised inputs and transformations trained using later data. For each evaluation cutoff, select permitted vintages, apply release eligibility, then fit scaling, missing-data rules, factor loadings and thresholds only on training data. Preserve the fitted artifact and its training cutoff. Merely shifting a full-sample factor by one week does not repair future information in its fitted parameters.

Use walk-forward or expanding-window evaluation with frozen specifications and an untouched final period. Compare against no-change/last-value and simple expanding historical-average baselines for forecasts; retain NFCI and unconditional/regime-matched comparisons where they answer the current descriptive question. Outcomes need an explicit choice of initial-release or revised target, and a separately versioned market-price basis. Purge overlapping target windows across validation boundaries. Include transaction costs only if evaluating an executable strategy, which is outside the initial product scope.

Preserve moving-block uncertainty and hypothesis-family corrections; report sample counts, effective dependence and coverage by regime. Never turn nine signal dates into 108 independent observations. Correlation, factor contribution and revision attribution are not causal economic effects. Probabilities need calibration and proper scoring against held-out outcomes before being presented as reliable probabilities. A two-sided HP filter is descriptive unless a causal, cutoff-fitted alternative is explicitly selected.

Open uncertainties are deliberate milestones: BIS historical archives, World Bank archive version coverage, provider-specific redistribution, exact NY Fed search limits, old publication timestamps, and whether all existing formulas can replay within the chosen numeric tolerance. These do not prevent the first GDP slice; they prevent unsupported claims of complete historical or enterprise coverage.

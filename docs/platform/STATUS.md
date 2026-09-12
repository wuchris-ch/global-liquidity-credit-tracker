# Implementation status

Implemented locally on September 11, 2026. [Run the workbench](RUNBOOK.md). The original proposal remains in [IMPLEMENTATION.md](IMPLEMENTATION.md); the table below distinguishes shipped code from unperformed operational or empirical validation.

| Area | Implemented | Validation and limits |
|---|---|---|
| Evidence and time | Immutable raw responses and Parquet, versioned workspace manifests, source and platform dates, strict coverage, metadata/unit validation | GDP revision fixture; source paging and null tests; duplicate/conflict and crash-boundary tests; live FRED, BIS, World Bank and NY Fed checks |
| Research workspace | Next.js Research page, catalog, transformations, two-run chart/table, saved versions, notes, watchlists, revision inbox, acquisition form, jobs, release status and exports | Browser GDP workflow and annotation checked at desktop and 390 px width; frontend lint/build pass. This was an automated walkthrough, not Chris's independent usability trial |
| Reproducibility | Pinned recipes, Decimal calculations, environment hashes, JSON replay bundles, CSV/Parquet/HTML, private report records | Exact 1.6 to 1.3 revision and -0.3 difference; changed implementation/data cannot masquerade as the original run; network-disabled container demo passes |
| Collection and recovery | Durable idempotent jobs, lease generations and commit fencing, cancellation, bounded retry, quarantine, recurring reconciliation, backups and restore | Expired-worker and rollback tests; source failure tests; backup dependency checks; PostgreSQL-to-SQLite restore verified |
| Model research | Strict pinned GLCI fetcher, cutoff fit, source/unit checks, saved fitted numerical state, replay, immutable matured/corrected outcomes | 21 captured inputs, 136 weekly outputs, 3 pillar artifacts. Two complete reconstructions matched. Future-data perturbation and model-state tamper tests pass. Automatic price acquisition and a forecasting-skill evaluation are not included |
| Assistant | Bounded deterministic explanations of selected runs, numerical facts, source citations, scope refusal and publication-history checks | 40 regression cases pass, with no external model calls. This is not an independent held-out agent benchmark or a free-form LLM agent |
| Shared backend | PostgreSQL adapter, verified OIDC tokens, workspace membership, viewer/editor/owner roles, revocation and audit records; non-root container | Local signed-token tests and real temporary PostgreSQL tests pass. No hosted OIDC login, production tenancy/RLS, paid resources or team pilot was configured |

## Changes made while implementing

The implementation follows the research intent rather than reproducing every proposed module or adding services without a demonstrated need. A separate research API keeps the existing dashboard and publishing pipeline independent. A deterministic assistant supplies useful, auditable explanations without a model service. Scheduled full-history partitions provide verifiable reconciliation before introducing provider-specific incremental feeds. Unknown historical coverage is an error rather than a revised-data substitute.

Live checks revealed that WTREGEN's May 2024 vintage reports billions of U.S. dollars, while the current source reports millions. Units now live with each snapshot. The net-liquidity operation converts each input to millions before subtraction. The existing dashboard's current TGA convention remains valid.

A May 2024 GLCI reconstruction also exposed only 18 common observations after the currently available spread history and feature preparation. The configured 104-row rolling regime uses a 20-row minimum, so that cutoff cannot support a current regime. Research results preserve an unavailable regime; the production computation fails explicitly if its latest regime is unavailable. A September 4, 2026 cutoff had sufficient common history and produced the verified 136-row reconstruction. Neither calculation is relabeled as a historical platform prediction.

World Bank pagination and country preservation were repaired in the existing adapter. The research adapter adds explicit forward-capture semantics and reviewed unit contracts. BIS's working v1 data endpoint was retained after direct verification. Historic World Bank archive editions and historic BIS publication coverage remain unverified and are not offered as capabilities.

## Measured checks

The machine was an Apple M1 Max Mac with 64 GiB RAM, macOS 26.5, using the pinned native Python 3.11.14 runtime. The frontend lock resolves Next.js 16.3.5. Updating compatible frontend packages removed the vulnerabilities reported by the prior lock; the final npm audit reported zero.

A synthetic workload of 100 series and 1,000,000 rows, spanning January 1990 through May 2017, took 6.93 seconds to ingest. One hundred single-series, 365-row queries had median 8.04 ms and p95 9.44 ms. Peak process memory was 176,766,976 bytes. The benchmark uses mixed OS caching and one reader. It is not a cold-cache or hosted-concurrency measurement, and its date span differs from the original proposed benchmark.

The complete 21-input GLCI reconstruction and replay took 7.30 seconds for two runs. The dataset and result identities are recorded in [the verification receipt](evidence/implementation-verification.json). Source bytes, model artifacts, additional live checks and the local catalog remain under ignored `data/` directories. The receipt contains hashes and measurements rather than redistributing unreviewed provider data.

The full offline suite has 236 passing tests: the existing 209 plus 27 research tests. Eight additional client checks verify safe network retries, idempotency and hosted availability. One existing test remains skipped because it requires a complete local production export. No production pipeline was run merely to satisfy that skip. The final test count is recorded in the verification receipt.

For release, Research is available in development and in deployments with an explicitly configured research API. Unconfigured public deployments hide its navigation entry and show an unavailable page without calling localhost. CI and scheduled data publication use the same pinned Python runtime and dependency lock.

## Remaining validation gates

These are not represented as completed implementation outcomes:

- A real hosted deployment and OIDC login experience, scoped sharing/entitlement review, external security review, production recovery objectives and a user team pilot.
- Independent user usability and independent held-out assistant evaluation, including any future retrieval or generated prose.
- An automatic adjusted-price capture adapter, provider holiday calendars, verified historical archive support and source-specific incremental change feeds.
- Target-specific forecast definitions, purged evaluation splits, non-overlapping horizons, comparison baselines, uncertainty and sample-size requirements. There is no forecast-superiority or investment-performance claim.
- Object-store hosting, PostgreSQL row-level security, controlled cold-cache tests and hosted concurrency/cost measurements.

The implemented service is a working local research platform with a tested shared-backend foundation. The public frontend and data pipeline can be released independently of hosting this service. No production database migration is required. Deployment verification belongs to the release record, separate from the implementation measurements above.

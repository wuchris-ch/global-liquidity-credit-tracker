# Implementation status

Updated September 12, 2026 UTC. [Open the public laboratory](https://global-liquidity-credit-tracker.vercel.app/research/lab) or [run the workbench](RUNBOOK.md). The original proposal remains in [IMPLEMENTATION.md](IMPLEMENTATION.md); the table below records implemented behavior and its validation scope.

| Area | Implemented | Validation and limits |
|---|---|---|
| Evidence and time | Immutable raw responses and Parquet, versioned workspace manifests, source and platform dates, strict coverage, metadata/unit validation | GDP revision fixture; source paging and null tests; duplicate/conflict and crash-boundary tests; live FRED, BIS, World Bank and NY Fed checks |
| Research workspace | Next.js Research page, catalog, transformations, two-run chart/table, saved versions, notes, watchlists, revision inbox, acquisition form, jobs, release status and exports | Browser GDP workflow and annotation checked at desktop and 390 px width; frontend lint/build pass |
| Public release laboratory | Three release tracks, missed-run reconciliation, completeness checks, immutable publication archives, explainable inbox, saved/shared typed comparisons, changed-input attribution and offline replay | Actual FRED collection and backup/restore exercise; recorded failures, unit drift, duplicate captures and source outages; browser save/share/reload/import and source verification |
| Revision study | Complete 24-month payroll cohort, verified first estimates, fixed comparison date, all planned outcomes, year splits and 3-/6-month block resampling intervals | All first estimates cross-checked against BLS; 25 snapshots and 51 original responses independently replayed; explicit missing-history exclusions and incomplete-study publication hold |
| Reproducibility | Pinned recipes, Decimal calculations, environment hashes, JSON replay bundles, CSV/Parquet/HTML, private report records | Exact 1.6 to 1.3 revision and -0.3 difference; changed implementation/data cannot masquerade as the original run; network-disabled container demo passes |
| Collection and recovery | Durable idempotent jobs, lease generations and commit fencing, cancellation, bounded retry, quarantine, recurring reconciliation, backups and restore | Expired-worker and rollback tests; source failure tests; backup dependency checks; PostgreSQL-to-SQLite restore verified |
| Model research | Strict pinned GLCI fetcher, cutoff fit, source/unit checks, saved fitted numerical state, replay, immutable matured/corrected outcomes | 21 captured inputs, 136 weekly outputs, 3 pillar artifacts. Two complete reconstructions matched. Future-data perturbation and model-state tamper tests pass. Automatic price acquisition and a forecasting-skill evaluation are not included |
| Research planner and assistant | Inspectable typed recipes from a finite comparison grammar, deterministic calculations, exact source citations, scope refusal and publication-history checks | 36 reserved planner prompts: 14 factual comparisons, 54 exact input citations, 22 refusals; existing assistant has 40 regression cases. No external model service |
| Shared backend | PostgreSQL adapter, verified OIDC tokens, workspace membership, viewer/editor/owner roles, revocation and audit records; non-root container | Local signed-token tests and real temporary PostgreSQL tests pass. No hosted OIDC login, production tenancy/RLS, paid resources or team pilot was configured |

## Changes made while implementing

The private research API and public publishing pipeline operate independently. The public laboratory shares the source adapters, immutable store, deterministic calculations, leased jobs and recovery tools through the existing GitHub/Vercel deployment. Its three government release tracks reconcile provider calendars against archived vintage inventories every 12 hours. Unknown historical coverage is an explicit missing input. Full methodology and operating contracts are in [RELEASE_LAB.md](RELEASE_LAB.md).

Live checks revealed that WTREGEN's May 2024 vintage reports billions of U.S. dollars, while the current source reports millions. Units now live with each snapshot. The net-liquidity operation converts each input to millions before subtraction. The existing dashboard's current TGA convention remains valid.

A May 2024 GLCI reconstruction also exposed only 18 common observations after the currently available spread history and feature preparation. The configured 104-row rolling regime uses a 20-row minimum, so that cutoff cannot support a current regime. Research results preserve an unavailable regime; the production computation fails explicitly if its latest regime is unavailable. A September 4, 2026 cutoff had sufficient common history and produced the verified 136-row reconstruction. Neither calculation is relabeled as a historical platform prediction.

World Bank pagination and country preservation were repaired in the existing adapter. The research adapter adds explicit forward-capture semantics and reviewed unit contracts. BIS's working v1 data endpoint was retained after direct verification. Historic World Bank archive editions and historic BIS publication coverage remain unverified and are not offered as capabilities.

## Measured checks

The machine was an Apple M1 Max Mac with 64 GiB RAM, macOS 26.5, using the pinned native Python 3.11.14 runtime. The frontend lock resolves Next.js 16.3.5. Updating compatible frontend packages removed the vulnerabilities reported by the prior lock; the final npm audit reported zero.

A synthetic workload of 100 series and 1,000,000 rows, spanning January 1990 through May 2017, took 6.93 seconds to ingest. One hundred single-series, 365-row queries had median 8.04 ms and p95 9.44 ms. Peak process memory was 176,766,976 bytes. The benchmark uses mixed OS caching and one reader. It is not a cold-cache or hosted-concurrency measurement, and its date span differs from the original proposed benchmark.

The complete 21-input GLCI reconstruction and replay took 7.30 seconds for two runs. The dataset and result identities are recorded in [the verification receipt](evidence/implementation-verification.json). Source bytes, model artifacts, additional live checks and the local catalog remain under ignored `data/` directories. The receipt contains hashes and measurements rather than redistributing unreviewed provider data.

The full offline suite has 261 passing tests. One existing test requires a complete local production export and is skipped in the offline suite. Client checks cover safe retries, idempotency, hosted availability, nine Atlas source captures, the reserved planner cases, publication hashes, typed sharing, attribution, unit drift, missing history and exact threshold classification. The [planner receipt](evidence/release-planner-evaluation.json) includes two complete question-to-recipe-to-result examples.

Four leased workers also completed 24 real payroll calculations against 13 captured snapshots, with every result checked against the study. The [concurrency receipt](evidence/release-lab-benchmark.json) records elapsed time, per-job latency, memory, environment and code hashes. This workload excludes network collection and fixture loading and measures the durable claim/query/calculation/commit path.

The public Research Atlas now provides three historical studies, nine FRED source vintages, interactive release comparisons, a reference-level calculation, historical charts, revision charts, calculation tables, share links, CSV/JSON exports and browser SHA-256 verification. It uses public captures only and has no connection to the local research service. The private workbench remains available in development or when an authenticated research API is explicitly configured. CI and scheduled data publication use the same pinned Python runtime and dependency lock. Release preflight reproduced the existing Friday OCC failure: the date-only cutoff requested an unfinished weekly report. Weekly selection now starts with a Friday strictly before the cutoff; Friday and Saturday boundaries are covered by regression tests, and the corrected Friday query succeeded against the live provider.

## Remaining validation gates

These are not represented as completed implementation outcomes:

- A real hosted deployment and OIDC login experience, scoped sharing/entitlement review, external security review, production recovery objectives and a user team pilot.
- Broader user usability studies and evaluation of any future free-form model, retrieval or generated prose. The implemented finite-language planner has a reserved evaluation over its supported grammar.
- An automatic adjusted-price capture adapter and release/archive integrations beyond the three public government tracks. Historic BIS and World Bank archive editions remain unverified.
- Target-specific forecast definitions, purged evaluation splits, non-overlapping horizons, comparison baselines, uncertainty and sample-size requirements. There is no forecast-superiority or investment-performance claim.
- Object-store hosting, PostgreSQL row-level security, controlled cold-cache tests and hosted concurrency/cost measurements.

The public frontend and data pipeline operate without hosting the private workbench or exposing a local computer. No production database migration is required. Deployment verification belongs to the release record, separate from the implementation measurements above.

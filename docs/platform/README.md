# Global Macro Data & Research Platform

Planning began September 11, 2026. The subsequent implementation is documented in [Status and measured results](STATUS.md) and [Local setup and operations](RUNBOOK.md). The proposal below is retained as design context; its acceptance targets are not claims of completed validation.

**Recommendation:** evolve this repository into a personal macro research workbench built around verifiable data history. Keep the Next.js dashboard and precomputed JSON delivery. Add immutable source captures, explicit historical coverage, reproducible analyses and a small local query service before adding a research assistant or team hosting.

The defining question is: **What information was available on a date, what did this platform actually conclude, and why does the answer differ now?** These are three separate queries. A historical source vintage is not a historical platform prediction. A current-data reconstruction is useful, but must remain visibly labeled.

## Read this plan

| Document | Purpose |
|---|---|
| [Research and current state](RESEARCH.md) | Inspected implementation, live observations, source constraints, comparisons and authentic revision demo |
| [Architecture and contracts](ARCHITECTURE.md) | Data flow, temporal semantics, storage, API, ingestion state machine, deployment and security decisions |
| [Implementation and verification](IMPLEMENTATION.md) | Prioritized milestones, acceptance tests, learning exercises, benchmarks and first implementation task |
| [Evidence](evidence/) | Small public API responses and verification record collected during planning |

## The product Chris should use

Open **Today** for the existing brief, a watchlist and releases due next. Open **Research** to compare series, transformations and two historical information dates. Save an analysis as a versioned recipe with frozen input references. Later, open **Changes** to see new observations, source revisions, metadata changes and model changes separately. Add an annotation explaining a hypothesis, export the exact table and chart, and reopen the same analysis without silently refreshing it.

Keep Index, Leadership, Playbook and Plumbing as useful domain views. Make the existing Explorer the starting point for Research rather than replacing its charts. Add clear links to sector flows, because a prior user task explicitly asked where the new feature was located. Maintain the current restrained typography, large readable charts and evidence disclosures. Put source and computation details in a persistent inspector beside the analysis, not in a wall of introductory text.

### Priorities

| Priority | Scope | Why |
|---|---|---|
| P0 | Temporal source contract, immutable captures, known coverage gaps, deterministic replay, corrected pagination and source dimensions | All subsequent research depends on these |
| P1 | Comparison UI, saved recipes, revision inbox, annotations, CSV/JSON/Parquet exports, release-aware freshness and documented local API | Makes this a daily research tool |
| P2 | Historical model refits, reproducible reports, frozen matured outcomes, bounded data-grounded research assistant | Adds analytical depth after provenance works |
| P3 | Private hosted workspaces, authentication, team permissions, audited sharing, quotas, recovery objectives | Earn complexity through actual collaboration needs |

Initial research universe: a reviewed subset of the existing US liquidity and credit series, GDP for the revision demo, BIS US/EU/JP/CN credit with explicit snapshot-only gaps, and selected World Bank annual context. Reuse configured identities, but admit each series to historical mode only after its coverage is verified. A global catalog does not imply globally complete historical vintages.

Do not prioritize streaming, Kubernetes, an always-on feature store, a new forecasting model, automatic trading, an unrestricted SQL agent, or a wholesale dashboard rewrite. The existing project already demonstrates useful full-stack work; the strongest upgrade is trustworthy data engineering that users can inspect.

## Evidence at a glance

- Both checkouts were clean at `c72abdad8dacc346aaa277ae4e54c3f3c546e853`. No material revision divergence was found. The original checkout was read only.
- This task ran the existing suite: **209 passed, one skipped, 47.50 seconds**. The skipped case needs a full local production export. This is a measured local result, not a new benchmark or a claim that all source integrations are correct.
- The live trust payload showed **108 computations across nine signal dates**, with `point_in_time: false`. Its latest signal date was September 4, 2026. The browser showed the same disclosures. See [captured response](evidence/live-trust.json).
- Two read-only FRED calls verified 2024 Q1 real GDP growth at **1.6% on April 25** and **1.3% on May 30**. See [authentic vintage responses](evidence/fred-gdp-vintages.json). The proposed saved-analysis demo uses this change.

## Success and boundaries

The first useful release is a local workbench where Chris can save the GDP analysis, reopen its original answer, explain the revision using source evidence, and repeat the computation from an exported bundle. It should also answer honestly that the old platform has no recorded conclusion for April 2024.

The broader release succeeds when it preserves the existing dashboard, survives interrupted ingestion, explains stale or incomplete data, and supports multiple useful saved macro analyses without manual data repair. Team features come after a sustained personal-use period. Performance and service targets in the implementation plan are **proposed acceptance targets**, not achieved results.

The first coding task is [a narrowly scoped vintage capture and replay slice](IMPLEMENTATION.md#first-implementation-task). It starts the data foundation without changing production calculations or triggering a publication.

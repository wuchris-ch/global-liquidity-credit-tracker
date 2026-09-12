# Planning verification record

Checked September 11, 2026. This directory contains bounded research evidence, not production source storage or an implemented historical data platform.

## Repository inspection

- Planning worktree: `/Users/chris/.codex/worktrees/e995/global-liquidity-credit-tracker`.
- Original checkout, inspected read only: `/Users/chris/Projects/global-liquidity-credit-tracker`.
- Both HEADs: `c72abdad8dacc346aaa277ae4e54c3f3c546e853`.
- Both initially clean; original remained clean when rechecked after documentation authoring.
- Applicable user conventions read from `/Users/chris/.codex/AGENTS.md`; no project-specific AGENTS.md found in this repository. The separate agent-eval repository's instructions were read before inspecting it.

## Existing tests

Executed against this worktree using the original checkout's existing Python environment, with isolated data and no bytecode/cache writes:

```sh
DATA_PATH=/tmp/macro-planning-tests PYTHONDONTWRITEBYTECODE=1 \
  /Users/chris/Projects/global-liquidity-credit-tracker/.venv/bin/python \
  -m pytest -p no:cacheprovider tests/
```

Result: `209 passed, 1 skipped in 47.50s`, exit 0.

The skipped case is `TestValidateRequiredExports.test_valid_local_export_passes`, which requires a full local export. No production workflow was run to generate it. This run does not establish all live adapter behavior, frontend build health, historical coverage, forecast quality or proposed performance targets.

## Bounded live observations

- [FRED GDP vintages](fred-gdp-vintages.json): two authenticated read-only source requests, both HTTP 200; credentials omitted. 2024 Q1 observation is 1.6 for information date April 25 and 1.3 for May 30. The response intervals are query-clipped, not proof of a complete timeline.
- [Live trust](live-trust.json) and [live latest](live-latest.json): read-only public published JSON requests, HTTP 200. Their timestamps and response hashes are retained. These are snapshots of a mutable public endpoint, not ongoing health monitoring.
- [Source probes](source-probes.json): current BIS US credit route, World Bank pagination and archive metadata, NY Fed latest SOFR. Each successful response is preserved with request parameters and retrieval timestamp. World Bank source 57 metadata is not proof of retrievable complete archive data. The BIS response is current data for an old observation period, not a historical vintage.
- In-app Browser: loaded the public Today page and inspected accessibility content and rendered screenshot. Observed the current brief, navigation, evidence warnings, 108 computations and nine distinct signal dates. No forms submitted; no full E2E/accessibility audit claimed.

Hashes labeled `body_sha256` identify the original HTTP body bytes as received by the client, before JSON pretty printing into these envelopes. The envelopes are not exact-byte copies of those transport bodies. Production immutable capture storage remains future work.

## Scope

Only planning documents and small public data-evidence envelopes were added in this worktree. No application implementation, commit, push, deployment, production ingestion run, source data rewrite, external message or paid service was performed. Future commands and modules in the plan are explicitly proposed. Documentation references were checked online on the research date, with documented versus observed behavior distinguished in the assessment.

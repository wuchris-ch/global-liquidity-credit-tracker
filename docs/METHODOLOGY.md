# Methodology

Formal definitions of every computed quantity in the tracker, with pointers
to the implementing code. All computations live in `src/indicators/` and are
covered by the test suite in `tests/`.

## Notation

- `x_t` — value of a series at time *t* (weekly unless stated otherwise)
- `μ`, `σ` — mean and standard deviation over the stated window
- All z-scores use the sample standard deviation (ddof = 1, pandas default)

---

## 1. Fed Net Liquidity

**Code:** [`src/indicators/aggregator.py`](../src/indicators/aggregator.py) (`_compute_arithmetic`), config in [`config/series.yml`](../config/series.yml)

```
NetLiquidity_t = WALCL_t − WTREGEN_t − 1000 · RRPONTSYD_t
```

| Term | FRED ID | Unit |
|------|---------|------|
| Fed Total Assets | WALCL | millions USD |
| Treasury General Account | WTREGEN | millions USD |
| Overnight Reverse Repo | RRPONTSYD | **billions** USD (hence the ×1000) |

All components are resampled to weekly (Friday, last observation) and
inner-joined before the subtraction. The ×1000 unit conversion is asserted by
`tests/test_config_integrity.py::test_fed_net_liquidity_unit_conversion`.

## 2. USD Credit Stress

**Code:** `_compute_zscore_average` in [`src/indicators/aggregator.py`](../src/indicators/aggregator.py)

Weighted average of rolling z-scores (252-day window, min 20 obs):

```
Stress_t = Σ_i w_i · z_i,t / Σ_i w_i
z_i,t   = (x_i,t − μ_i,[t−252,t]) / σ_i,[t−252,t]
```

Components: ICE BofA HY OAS (w=1) and ICE BofA IG OAS (w=0.5). The API ID
remains `usd_funding_stress` for compatibility. TED is discontinued and is
retained as historical source data only; it is not part of this live composite
or the GLCI stress pillar.

## 3. Global Liquidity & Credit Index (GLCI)

**Code:** [`src/indicators/glci.py`](../src/indicators/glci.py),
[`src/indicators/dynamic_factor.py`](../src/indicators/dynamic_factor.py),
[`src/indicators/factors.py`](../src/indicators/factors.py)

The GLCI is a tri-pillar latent-factor composite computed at weekly frequency.

### 3.1 Pillar construction

For each pillar *p* ∈ {liquidity, credit, stress}:

1. **Feature matrix.** Each component series is resampled to weekly,
   transformed per the pillar config (z-score with 104-week window and/or
   52-week growth rate), and component-sign-adjusted so its expected loading
   is positive (e.g. reverse repo enters the liquidity pillar with sign -1
   because it drains liquidity). A pillar-level economic sign is applied only
   after factor extraction.
2. **Factor extraction.** The production `method="auto"` path uses a
   one-factor, sign-constrained PCA model. The first principal component
   initializes the common score, then Ridge regression (`α = 0.1`) shrinks
   the loadings. Coefficient bounds enforce each input's configured economic
   direction. The factor and loadings are solved jointly until convergence. A
   component that moves against the fitted factor receives zero loading and is
   disclosed in `constraint_excluded_features`; it cannot silently reverse the
   pillar. Plain PCA and DFM remain explicit diagnostic options, but their
   output must pass the same post-fit loading audit.
3. **Orientation and scale.** Factor scores and loadings share one global
   orientation (factor up = oriented components up). After the three factors
   are restricted to their common history, each is standardized to mean zero
   and unit variance before the 40/35/25 weights are applied. This keeps
   estimator scale from changing the effective pillar weights. Asserted by
   `tests/test_dynamic_factor.py` sign-constraint tests.

BIS quarterly and World Bank annual periods are dated at period end. Inside the
feature matrix, every configured monthly, quarterly, or annual observation is
also normalized to its period end before it can reach a signal. This prevents
first-of-period source labels, including FRED monthly labels, from making an
end-of-period value appear early. It establishes the earliest possible
availability, not the source's actual historical release timestamp.

A configured `availability_lag_days` then moves an observation onto a more
conservative release clock before weekly resampling. BIS quarterly credit uses
a 90-calendar-day lag, so a quarter-end value cannot affect a signal during the
quarter it describes. Annual World Bank credit-to-GDP series remain available
for contextual exploration but are not predictive GLCI inputs because the
pipeline does not yet retain their historical releases. Critical FRED inputs
may also declare a `source_contract`; a title, unit, or frequency mismatch
fails the fetch rather than silently accepting a semantically different series.
W-FRI labels are emitted only after the Friday period is complete. A pipeline
run on Friday uses the prior Friday; the new Friday becomes eligible on
Saturday, preventing a Thursday observation from acquiring a future close date.

### 3.2 Composite

```
GLCI_raw,t = Σ_p w_p · f_p,t        w = {liquidity: 0.40, credit: 0.35, stress: 0.25}
```

These are fixed policy weights, not weights calibrated or optimized against
asset returns. Requests for dynamic weight optimization are rejected rather
than silently ignored.

The stress pillar uses HY OAS, IG OAS, SOFR, the effective federal funds rate,
VIX, and NFCI. The stress factor enters **inverted** (pillar sign -1: higher
stress lowers the index). The composite is then normalized to mean 100, stdev
10:

```
GLCI_t = 100 + 10 · (GLCI_raw,t − μ) / σ
```

All three configured pillars are required. If any pillar cannot be computed,
the run fails before a partial or reweighted composite can be saved or
published.

Each fitted pillar must retain at least two distinct source series, may exclude
at most 50% of its fitted features through binding sign constraints, and may
assign at most 60% of absolute loading mass to one source series. The run fails
if any gate is breached. Metadata reports the exclusions, exclusion share, and
source-level loading shares.

### 3.3 Regime classification

A rolling z-score of the composite (104-week window) is bucketed:

```
z_t < −1   →  tight  (−1)
−1 ≤ z_t ≤ 1 →  neutral (0)
z_t > +1   →  loose  (+1)
```

Rows without a finite z-score, including the rolling-window burn-in, remain
unclassified rather than being treated as neutral observations.

The dashboard also reports 4-week momentum and a heuristic boundary-pressure
score based on distance to the nearest threshold and the z-score trend
(`compute_regime_probability` in
[`src/indicators/transforms.py`](../src/indicators/transforms.py)). Despite the
legacy field name `prob_regime_change`, this is not a calibrated probability.

### 3.4 Historical reconstruction and publication snapshots

The displayed GLCI history is recomputed using the latest available source
values and the current factor estimate. The project does not retain historical
FRED, BIS, or World Bank release vintages for the period before publication
snapshots were introduced. Consequently, the historical series is a
**current-vintage reconstruction**, not a point-in-time record of signals that
were available to an investor on each date.

Each scheduled computation now appends the latest published state to a signal
snapshot ledger, keyed by both computation time and signal date. Those records
preserve future revisions and live decisions without rewriting earlier
snapshots. They do not retroactively create missing source vintages.

## 4. Risk by Regime

**Code:** [`src/indicators/risk_metrics.py`](../src/indicators/risk_metrics.py)

Daily asset returns `r_t = P_t / P_{t−1} − 1` are merged with the GLCI regime
(as-of backward join: each day gets the most recent weekly regime) and the
3-month T-bill rate (DGS3MO) as the risk-free rate. Let `N_a` be the asset's
observation clock: 252 for trading-day assets and 365 for calendar-daily crypto.
The annual T-bill rate is de-annualized by `N_a`.

For the full sample and for each regime bucket with > 20 observations:

```
Sharpe      = mean(r_t − rf_t) / std(r_t − rf_t) · √N_a
AnnReturn   = mean(r_t) · N_a · 100
AnnVol      = std(r_t) · √N_a · 100
MaxDrawdown = min_t (P_t − max_{s≤t} P_s) / max_{s≤t} P_s · 100
```

Rolling Sharpe uses one year on the same clock: 252 observations for
trading-day assets and 365 for crypto. Correlation with GLCI is computed on a
common W-FRI grid between weekly asset returns and weekly GLCI level changes,
with at least 20 aligned weeks; unavailable correlations remain null rather
than being reported as zero. The Sharpe calculation has an epsilon guard
(σ < 1e-12 → 0) so constant series do not produce astronomically large ratios
(`tests/test_risk_metrics.py::test_zero_volatility_returns_zero`).

Assets: S&P 500, Nasdaq 100, Semiconductors (SMH), Russell 2000 (IWM),
Gold (GLD), Silver (SLV), Bitcoin, Ethereum, Zcash, Long Bonds (TLT).
Bitcoin and Ethereum prices come from FRED's Coinbase series (CBBTCUSD,
CBETHUSD); Zcash comes from Yahoo Finance (ZEC-USD).

## 5. Track Record backtest

**Code:** [`src/indicators/backtest.py`](../src/indicators/backtest.py)

Tests whether the GLCI regime has predictive value for forward returns,
against an NFCI-based classifier (inverted to match orientation) and the
unconditional base rate.

### 5.1 Production classifier and vintage limitation

The backtest re-classifies the reconstructed GLCI with the same **rolling
104-week window** used by the live index:

```
z_t = (x_t − μ_{[t−103,t]}) / σ_{[t−103,t]}
```

The first 19 observations are unclassified, and the first label is emitted at
20 observations, matching the production minimum. Conditional on a fixed GLCI
input series, changing later composite observations does not change earlier
classifications. NFCI retains an expanding 52-week classifier as an independent
baseline.

That invariant is narrower than a fully point-in-time backtest. Upstream source
revisions and full-sample factor estimation can change the reconstructed GLCI
history supplied to the classifier. Results must therefore be read as a
historical conditional study of the current model, not a simulated live track
record.

### 5.2 Forward returns and statistics

GLCI observations and asset prices are placed on a Friday weekly grid. Every
GLCI Friday must be present; missing index weeks fail the backtest rather than
being filled with synthetic carried values. A regime observed at week `t` is
entered on the next weekly bar, then held for horizons `h` in {4, 13, 26}
calendar weeks:

```
fwd_{t,h} = P_{t+1+h} / P_{t+1} - 1
```

The one-week execution lag prevents using the same weekly close both to form a
signal and to enter the hypothetical position.

Per asset × classifier × regime × horizon (min 20 observations):

- **median**, **p25/p75** of forward returns
- **hit rate** = share of positive forward returns
- **edge** = hit rate − unconditional base rate at the same horizon, over the
  same weeks for which that classifier emits a regime

### 5.3 Confidence intervals

Forward returns at overlapping horizons are strongly autocorrelated, so a
plain row bootstrap would understate uncertainty. CIs use a **paired moving
block bootstrap** (block size = horizon, 5,000 iterations, seeded RNG for
reproducibility):

1. Keep the full Friday row sequence between the first and last finite forward
   return. Internal missing-return and unclassified weeks remain in place.
2. Resample blocks of `h` contiguous calendar rows with replacement and
   concatenate them to the original sequence length.
3. Within each draw, compute the regime-subgroup median and hit rate. Compute
   the unconditional hit rate from the same sampled rows that have a finite
   label for that classifier, then compute the paired edge as subgroup hit
   rate minus unconditional hit rate.
4. Discard a cell's draw when it contains fewer than 20 finite subgroup
   observations. Report a CI only when at least 4,000 of 5,000 draws are
   finite, using their 2.5th and 97.5th percentiles.

This preserves weekly adjacency before regime filtering. The hit-rate CI is a
subgroup interval and the edge CI is a separate paired interval. These nominal
intervals are retained for estimation context, but are not used by the product
to declare support across a table containing many comparisons.

### 5.4 Multiple-testing control

For every cell with enough finite bootstrap draws, the sample standard
deviation of the paired edge draws is reported as the bootstrap standard error.
A two-sided normal approximation converts the point edge and that standard
error to a p-value. This approximation is disclosed in the payload rather than
presented as an exact finite-sample test.

All finite p-values across classifier x asset x regime x horizon form one
family. The Benjamini-Yekutieli procedure adjusts that complete family at a
10% false-discovery-rate threshold. It is deliberately conservative because
the horizons, regimes, assets, and classifiers are dependent. The product
calls an edge supported only when its adjusted q-value is at or below 0.10;
otherwise the result remains descriptive even when its nominal 95% interval
excludes zero.

A q-value is necessary but not sufficient for the product's supported label.
The historical input must be point-in-time, and the primary GLCI classifier
must have at least 260 classified weekly observations and at least 20
observations in each of tight, neutral, and loose. Until every policy check
passes, q-values remain visible but all directional claims are marked
descriptive. The five-year weekly floor is an explicit model-governance
minimum; it is not represented as proof that the sample contains a complete
liquidity or business cycle.

Implementation and deterministic null, effect, and multiplicity tests are in
[`src/indicators/backtest.py`](../src/indicators/backtest.py) and
[`tests/test_backtest.py`](../tests/test_backtest.py).

### 5.5 Observed live record

The backtest payload also contains a forward-only record sourced from the
append-only publication ledger. For each weekly signal date it selects the
earliest recorded `computed_at` vintage. Entry is the first complete W-FRI bar
whose date is strictly after that computation date; exit is exactly 4, 13, or
26 weekly bars later. No reconstructed pre-ledger signal is admitted.

Issued, matured, pending, and unavailable outcomes are reported separately.
The evidence unit is asset x horizon x published regime. Regime-conditioned
return summaries remain null until at least 20 outcomes mature in that exact
cell; all-signal counts are operational context, not evidence that the regime
classifier predicts returns. The clock is forward-safe because signals are
fixed before evaluated outcomes. Realized returns are still recomputed from
the current adjusted-price files, however, rather than read from an immutable
outcome ledger. The record therefore does not make source or outcome history
vintage-complete, and it begins with the introduction of the signal ledger
rather than backfilling simulated history.

## 6. Price leadership (liquidity-sensitive destinations)

**Code:** [`src/indicators/flows.py`](../src/indicators/flows.py)

Ranks liquidity-sensitive destinations by how unusual their trailing bid is
relative to their own history. All prices collapse to weekly Friday closes
(`resample("W-FRI").last()`), which puts crypto's seven-day calendar and
equities' five-day calendar on the same grid.

Per destination, with weekly closes `P_w`:

```
ret_kw   = P_w / P_{w−k} − 1                      for k ∈ {4, 13, 26}
flow_z   = (R_now − mean(R)) / std(R)
           where R = trailing 156 weeks of overlapping 13-week returns
corr_52w = corr(weekly returns, ΔGLCI) over the trailing 52 weeks
```

`flow_z` normalizes each asset against itself, so a volatile asset must rally
harder to score. It is a relative price-leadership measure, not evidence of
capital flows or simply a ranking of raw returns. A z-score is only emitted with ≥ 52 weeks of
13-week-return history; degenerate dispersion (σ < 1e-12) yields none.
Because consecutive 13-week windows overlap, the score is slow-moving by
construction and readings beyond ±2σ are rare.

The headline pair is bitcoin / SMH (crypto priced in the AI trade), indexed
to 100 at the start of a 156-week window. This is a **bid gauge built from
prices**, not flow-of-funds accounting (Z.1 data is quarterly and lagged);
the page discloses that limitation.

Tests: `tests/test_flows.py` (return arithmetic, z-score vs a manual
computation, weekly collapse of seven-day data, missing-series resilience).

## 7. Sector rotation, ETF net issuance, and options activity

**Code:** [`src/indicators/sector_rotation.py`](../src/indicators/sector_rotation.py),
[`src/data_sources/state_street.py`](../src/data_sources/state_street.py), and
[`src/data_sources/occ.py`](../src/data_sources/occ.py)

The sector feature deliberately separates three evidence layers. The rank is
price-only; State Street net issuance and OCC cleared options activity are
context and cannot change the ordering.

For sector adjusted close `P_i`, SPY adjusted close `P_m`, and horizon `h`:

```text
rs_i,h = ln(P_i,t / P_i,t-h) - ln(P_m,t / P_m,t-h)
relative_strength_i = 0.5 * rs_i,63 + 0.5 * rs_i,126
absolute_trend_i = ln(P_i,t / P_i,t-126) / (sigma_i,63 * sqrt(126))
price_score_i = 0.65 * percentile(relative_strength_i)
              + 0.35 * percentile(absolute_trend_i)
```

Complete adjusted-close histories for SPY and all 11 Select Sector SPDRs are
required. Missing or incomplete Yahoo Finance data fails the price computation
closed. Sponsor NAV is not substituted because it is not a dividend-adjusted
total-return series.

Daily Select Sector SPDR issuance uses sponsor-reported NAV and shares
outstanding, with explicit share-split factor `S`:

```text
issuance_usd_i,t = (shares_i,t - S_i,t * shares_i,t-1) * NAV_i,t
```

The output includes 5-session and 20-session sums and a robust 20-session
issuance z-score against the prior 252 observations. OCC call and put volumes
are labelled cleared activity. They do not expose aggressor side or open/close
position and therefore are not described as directional options flow.

Definitions, split handling, source links, limitations, and the research
survey are in [MARKET_FLOWS.md](MARKET_FLOWS.md). Research sources were checked
on 2026-07-14. The signal remains `descriptive_not_backtested`.

Tests: [`tests/test_sector_rotation.py`](../tests/test_sector_rotation.py)
(source parsing, split-adjusted issuance, robust z-score history, complete
ranking, and proof that fund and options context does not change the score).

---

## Verification

```bash
make test    # 80+ unit tests over every formula above (offline)
make smoke   # config + numerics + artifact validation (offline)
make smoke-live  # additionally validates the published JSON endpoints
```

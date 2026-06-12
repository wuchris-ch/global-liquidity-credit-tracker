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

## 2. USD Funding Stress

**Code:** `_compute_zscore_average` in [`src/indicators/aggregator.py`](../src/indicators/aggregator.py)

Weighted average of rolling z-scores (252-day window, min 20 obs):

```
Stress_t = Σ_i w_i · z_i,t / Σ_i w_i
z_i,t   = (x_i,t − μ_i,[t−252,t]) / σ_i,[t−252,t]
```

Components: TED spread (w=1), ICE BofA HY OAS (w=1), ICE BofA IG OAS (w=0.5).

## 3. Global Liquidity & Credit Index (GLCI)

**Code:** [`src/indicators/glci.py`](../src/indicators/glci.py),
[`src/indicators/dynamic_factor.py`](../src/indicators/dynamic_factor.py),
[`src/indicators/factors.py`](../src/indicators/factors.py)

The GLCI is a tri-pillar latent-factor composite computed at weekly frequency.

### 3.1 Pillar construction

For each pillar *p* ∈ {liquidity, credit, stress}:

1. **Feature matrix.** Each component series is resampled to weekly,
   transformed per the pillar config (z-score with 104-week window and/or
   52-week growth rate), and sign-flipped so its expected loading is
   positive (e.g. reverse repo enters the liquidity pillar with sign −1
   because it drains liquidity).
2. **Factor extraction.** A single latent factor is extracted with, in
   order of preference (`method="auto"`):
   - **DFM** — statsmodels `DynamicFactor`, EM estimation, when ≥50% of
     rows are complete and missingness ≤ 30%;
   - **PCA with shrinkage** — first principal component, loadings
     re-estimated by Ridge regression (`α = 0.1`) for stability under
     collinearity;
   - **plain PCA** (numpy SVD fallback if scikit-learn is unavailable).
3. **Orientation.** The factor is flipped, if necessary, so its average
   loading is positive (factor up = components up). Asserted by
   `tests/test_dynamic_factor.py::test_positive_average_loading_orientation`.

### 3.2 Composite

```
GLCI_raw,t = Σ_p w_p · f_p,t        w = {liquidity: 0.40, credit: 0.35, stress: 0.25}
```

The stress factor enters **inverted** (pillar sign −1: higher stress lowers
the index). The composite is then normalized to mean 100, stdev 10:

```
GLCI_t = 100 + 10 · (GLCI_raw,t − μ) / σ
```

If a pillar cannot be computed (data outage), its weight is redistributed
proportionally across the remaining pillars rather than failing the run.

### 3.3 Regime classification

A rolling z-score of the composite (104-week window) is bucketed:

```
z_t < −1   →  tight  (−1)
−1 ≤ z_t ≤ 1 →  neutral (0)
z_t > +1   →  loose  (+1)
```

The dashboard also reports 4-week momentum and a heuristic
probability-of-regime-change based on distance to the nearest threshold and
the z-score trend (`compute_regime_probability` in
[`src/indicators/transforms.py`](../src/indicators/transforms.py)).

## 4. Risk by Regime

**Code:** [`src/indicators/risk_metrics.py`](../src/indicators/risk_metrics.py)

Daily asset returns `r_t = P_t / P_{t−1} − 1` are merged with the GLCI regime
(as-of backward join: each day gets the most recent weekly regime) and the
3-month T-bill rate (DGS3MO, de-annualized by /252) as the risk-free rate.

For the full sample and for each regime bucket with > 20 observations:

```
Sharpe      = mean(r_t − rf_t) / std(r_t − rf_t) · √252
AnnReturn   = mean(r_t) · 252 · 100
AnnVol      = std(r_t) · √252 · 100
MaxDrawdown = min_t (P_t − max_{s≤t} P_s) / max_{s≤t} P_s · 100
```

Rolling Sharpe uses a 252-day window of excess returns. The Sharpe
calculation has an epsilon guard (σ < 1e-12 → 0) so constant series do not
produce astronomically large ratios
(`tests/test_risk_metrics.py::test_zero_volatility_returns_zero`).

Assets: S&P 500, Russell 2000 (IWM), Gold (GLD), Silver (SLV), Bitcoin,
Ethereum, Long Bonds (TLT).

## 5. Track Record backtest

**Code:** [`src/indicators/backtest.py`](../src/indicators/backtest.py)

Tests whether the GLCI regime has predictive value for forward returns,
against an NFCI-based classifier (inverted to match orientation) and the
unconditional base rate.

### 5.1 No look-ahead

The live GLCI z-score uses a rolling window, which is fine for *describing*
conditions but would leak future information into a backtest. The backtest
therefore re-classifies regimes with an **expanding window**:

```
z_t = (x_t − μ_{[0,t]}) / σ_{[0,t]}
```

with a 52-week burn-in (first year unclassified). The property "changing
future observations never changes past classifications" is asserted directly
by `tests/test_backtest.py::test_no_lookahead_bias`.

### 5.2 Forward returns and statistics

For horizons h ∈ {4, 13, 26} weeks:

```
fwd_{t,h} = P_{t+h} / P_t − 1
```

Per asset × classifier × regime × horizon (min 20 observations):

- **median**, **p25/p75** of forward returns
- **hit rate** = share of positive forward returns
- **edge** = hit rate − unconditional base rate at the same horizon

### 5.3 Confidence intervals

Forward returns at overlapping horizons are strongly autocorrelated, so a
plain bootstrap would understate uncertainty. CIs use a **moving block
bootstrap** (block size = horizon, 5,000 iterations, seeded RNG for
reproducibility):

1. Resample blocks of `h` consecutive observations with replacement,
2. concatenate to original length, compute the statistic,
3. report the 2.5th and 97.5th percentiles.

Implementation: `block_bootstrap_ci` in
[`src/indicators/backtest.py`](../src/indicators/backtest.py); determinism is
asserted by `tests/test_backtest.py::test_deterministic_with_seeded_rng`.

---

## Verification

```bash
make test    # 80+ unit tests over every formula above (offline)
make smoke   # config + numerics + artifact validation (offline)
make smoke-live  # additionally validates the published JSON endpoints
```

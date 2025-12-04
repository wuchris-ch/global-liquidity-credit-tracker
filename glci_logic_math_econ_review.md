# GLCI Logic/Math/Economics Review Plan (Iteration 3)

Goal: pressure-test the Global Liquidity & Credit Index design and decide if material math/logic/econ improvements are needed. Focus on evidence-based upgrades, not feature creep.

## Quick Read of Current State
- Architecture: tri-pillar latent factor (liquidity, credit, stress) via `DynamicFactorModel` (auto → PCA/shrunk PCA fallback), weekly target frequency, pre-flipped signs, rolling z-scores, simple regime bands.
- Config: pillars defined in `config/series.yml`; transforms mostly `zscore`/`growth`. Currency/real/GDP scaling not yet implemented in feature builder.
- Data quality: latest `glci_meta.json` shows `credit` pillar explained variance = NaN and loadings degenerate to China only → likely coverage/missingness problem in credit features.
- Output scaling: composite normalized to mean 100/stdev 10; pillar weights fixed (0.4/0.35/0.25) without current optimization.

## Key Risk Areas to Investigate
- **Data comparability:** No USD/real/GDP normalization in the pipeline; mixed currencies and price levels will distort loadings and cross-country credit comparisons.
- **Mixed-frequency handling:** Current approach resamples + ffill/bfill; DFMs default to PCA when missingness is high. Ragged edges may be biasing factors and killing the credit pillar.
- **Credit pillar weakness:** Degenerate loadings and NaN variance suggest insufficient observations or near-constant/empty series after transforms; impulse/gap transforms may be dropping too much.
- **Sign discipline:** Pre-flips occur, but no post-estimation sign audit beyond average-loading check; stress pillar inversion applied globally—needs per-component validation.
- **Weighting/econ priors:** Pillar weights fixed, not tied to GDP/market size or predictive power; no cap on single-series dominance; no prior on relative liquidity vs stress importance through the cycle.
- **Regime logic:** Static ±1 z-score thresholds; no asymmetric bands or probability-based regimes tied to macro states.
- **Validation depth:** Evaluation script stops at summary stats and simple correlations; no out-of-sample predictive tests, stability/robustness checks, or economic face-validity scorecard.

## Targeted Improvement Experiments (ranked)
P0 = must fix before trusting outputs; P1 = high-value enhancement; P2 = nice-to-have.

### P0: Make inputs economically comparable
- Add FX normalization for non-USD series (use `normalize_to_usd_dynamic` with EUR/USD, JPY/USD, GBP/USD, CNY/USD).
- Add real deflation (CPI/HICP/CPI-JP) for stocks/flows; store both nominal and real variants.
- Apply GDP scaling for credit levels and flows; use `country_weights` as priors but also compute credit/GDP gaps.
- Rebuild feature matrices with these normalizations and re-check coverage.

### P0: Repair credit pillar
- Audit which credit features survive after transforms; lower min data thresholds for impulse/gap or add fallbacks (level zscore, YoY growth) when impulse data are too sparse.
- Enforce minimum variable/observation counts per pillar; fail fast with a clear report when thresholds not met.
- Investigate BIS/World Bank series freshness (stale >30d) and add proxies (e.g., bank credit weekly) where needed.

### P1: Mixed-frequency state-space
- Enable `DynamicFactorMQ` (mixed-frequency DFM) when statsmodels is present; supply per-column frequency info to avoid aggressive forward-fills.
- For PCA paths, switch to EM imputation with frequency-aware decay (weekly ≠ quarterly).

### P1: Weighting and dominance control
- Cap per-series loading contribution (e.g., L1/L2 shrinkage or max |loading|) to prevent single-country dominance.
- Re-estimate pillar weights quarterly using predictive score vs. risk assets (MSCI ACWI, EM FX basket, HY spreads) with ridge regularization; constrain weights to stay near GDP priors.
- Track and publish effective weights + Herfindahl index for transparency.

### P1: Sign and regime discipline
- Post-fit sign audit: verify that stress-series loadings are positive after pre-flip; if not, flip factor and log the violation.
- Move from fixed ±1 bands to percentile or asymmetric thresholds (e.g., 35/65 or 25/75) and compare regime stability; add smoothed transition probabilities (already scaffolded).

### P1: Robustness tests
- Leave-one-country-out and leave-one-family-out (spreads vs rates) sensitivity on factors and composite.
- Jackknife loadings to detect instability; report drift over rolling windows.
- Stress-episode replay (2008, 2020, 2022 QT) with expected sign/magnitude checks and timing (lead/lag vs HY spreads).

### P2: Economics depth adds
- Add policy-stance metrics (policy rate minus neutral proxy; use Laubach-Williams/Holston estimates or term-structure neutral rate proxies).
- Include cross-currency basis and GC/Special repo spreads in stress pillar; add global reserve accumulation/net FX intervention as liquidity proxy.
- Consider equity/credit risk-appetite proxies (e.g., carry-to-vol, credit risk appetite) but only if they improve predictive tests.

## Measurement & Decision Gates
- **Coverage gate:** each pillar must have ≥4 active series and ≥104 obs at target frequency after normalization; else fail and report.
- **Explained variance gate:** first factor per pillar ≥40% variance or fallback to DFM/shrunk PCA with shrinkage tuned; if still <25%, flag as unstable.
- **Dominance gate:** max absolute loading share per pillar <35%; if breached, rescale or drop outlier series.
- **Predictive gate:** rolling 3–6m forward return IC vs. ACWI/HY > 0.05 and stable sign; otherwise revert to prior weights.
- **Face-validity gate:** sign checks on liquidity (+), credit (+), stress (−) during known episodes; deviations trigger review.

## External References to Anchor Decisions
- BIS “Global Liquidity: Drivers and Policy Implications” (Drehmann/Tsatsaronis).
- Bruno & Shin (2015) global liquidity and cross-border banking.
- Rey (2013/2015) “Dilemma not Trilemma” (global financial cycle) for regime framing.
- Adrian et al. (Fed GFCI/FCI) for factor construction and smoothing choices.
- Claessens/Mian/Sufi credit cycle and credit impulse literature for transform choices.

## Fast Checks to Run Now
- Recompute with verbose data-quality logs; inspect `glci_weights.json` for loadings degeneracy.
- Add a temporary diagnostic notebook: histogram of per-feature coverage, loading distributions, and dominance metrics per pillar.
- Compare PCA vs shrunk PCA vs DFM on current matrices; record explained variance and sign violations.
- Quick backtest: rolling correlation of GLCI with Fed Net Liquidity, USD funding stress, and HY spreads; check if correlations move in expected direction after fixes.

## If Time-Constrained (minimum viable improvement)
1) Implement USD/real/GDP normalization; 2) relax/drop brittle transforms to revive the credit pillar; 3) run shrunk-PCA with dominance cap; 4) reissue weights and regenerate metadata for frontend.


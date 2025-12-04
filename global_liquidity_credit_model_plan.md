# Global Liquidity & Credit Meta-Index Plan

## Objective
- Build a proprietary, single-number Global Liquidity & Credit Index (GLCI) that summarizes the joint stance of central bank liquidity, private credit creation, and funding stress across major economies.
- Use all configured sources (FRED, NY Fed, BIS, World Bank) plus extendable add-ons (FX, CPI, equity/credit benchmarks) while fitting cleanly into the existing `config/series.yml` + `DataFetcher` + `Aggregator` architecture.

## Design Principles
- **Tri-pillar structure:** (1) Central bank/monetary liquidity, (2) Private-credit cycle, (3) Market/funding stress. Each pillar becomes a latent factor; final index is a weighted blend of the three factors.
- **Currency- and price-consistency:** Convert to USD where relevant, deflate to real terms when comparing stocks/flows, normalize by GDP where structural comparability is needed.
- **Time-alignment:** Collapse everything to a common weekly cadence (Friday) with forward-fill for lower-frequency series and minimal look-ahead leakage.
- **Shrinkage & robustness:** Favor regularized estimators (ridge/elastic-net) and state-space smoothing (Kalman) to dampen noise and survive missing data.
- **Transparency:** Store pillar-level subindices and component weights for interpretability and audit.

## Data & Features (by pillar)
- **Liquidity pillar:** CB total assets (Fed/ECB/BoJ/BoE/PBoC if added), reserve balances, reverse repo, TGA, major M-aggregates (M2/M3), policy rate stance (level and policy-rate minus neutral proxy), FX-normalized USD equivalents, YoY and 3m/3m annualized growth, level z-scores.
- **Credit pillar:** BIS credit to private non-financial sector (levels and %GDP gaps), World Bank credit/GDP, bank lending growth if added, credit impulse (first-difference of credit/GDP), leverage ratios. Include country GDP weights from `country_weights` as priors.
- **Funding-stress pillar:** SOFR, fed funds, €STR, TED spread, IG/HY OAS, cross-currency basis if added, term-premia proxies; z-score transforms and slope measures (e.g., 3m vs policy rate).
- **Common transforms:** Real-adjusted (CPI/GDP deflator), FX to USD, detrended gaps (HP filter optional but prefer rolling mean), rolling z-scores, regime flags from `detect_regime`, missing-data masks for the model.

## Modeling Blueprint
1. **Feature assembly**
   - Implement `build_feature_matrix` (new module, e.g., `src/indicators/factors.py`) that:
     - Fetches components via `DataFetcher`.
     - Resamples to weekly via `resample_to_frequency`.
     - Applies FX/GDP normalization and growth-rate transforms.
     - Produces a wide feature frame + metadata (pillar tag, country, type, unit).
2. **Pillar latent factors**
   - For each pillar, standardize features and estimate a latent factor:
     - Start with PCA on standardized columns per pillar.
     - Upgrade to Dynamic Factor Model (state-space + Kalman filter) for smoother, time-varying loadings; impose sign constraints (e.g., higher liquidity lowers stress).
     - Handle mixed frequencies with mixed-frequency Kalman update (ragged edges allowed via mask).
3. **Global aggregation**
   - Combine pillar factors into final GLCI:
     - Initial weights: inverse-variance of factor innovations with GDP priors (e.g., liquidity factor 0.4, credit 0.35, stress 0.25, re-estimated quarterly).
     - Optional Bayesian model averaging: sample weights proportional to out-of-sample predictive score for risk assets (e.g., MSCI ACWI 3–6m forward returns).
   - Normalize final index to mean 100 / stdev 10 for readability; publish z-score and percentile.
4. **Regime overlay**
   - Markov-switching or thresholded z-score regimes (loose/neutral/tight) for both pillar factors and the composite; expose regime series.
5. **Stability & drift control**
   - Rolling-retrain with expanding window, use shrinkage on loadings, cap single-series contribution via max weight constraints.

## Weighting Logic
- **Country weights:** Start with `country_weights` GDP shares; adjust quarterly using rolling GDP or market-cap proxies. For credit features, weight by country GDP; for funding stress, equal-weight U.S. + Europe + Asia if available.
- **Series weights inside pillars:** Begin equal after standardization; re-weight by signal-to-noise (|mean/vol|) and recency (half-life ~1 year). Penalize high missingness.
- **Pillar weights:** Calibrate on predictive power for risk/vol assets; update semiannually to avoid overfitting.

## Validation & Backtesting
- **Economic face validity:** Signs (e.g., rising CB assets should lift liquidity factor), correlation with known indices (e.g., Fed net liquidity, FCI).
- **Predictive tests:** Rolling regressions of 3–6m forward returns of MSCI ACWI, EM FX basket, HY spreads; information coefficients; hit rates on drawdowns.
- **Stability tests:** Loading drift, variance of factor innovations, sensitivity to leaving-one-country-out.
- **Nowcast robustness:** Performance during sparse data (e.g., early months) using Kalman smoothing vs. simple fill.
- **Stress episodes:** 2008, 2020, 2022 QT—ensure index reacts with expected magnitude and lead/lag.

## Implementation Steps in This Repo
- **S1: Data audit & additions**
  - Verify coverage for ECB/BoJ/BoE/PBoC assets; add missing series in `config/series.yml`.
  - Add CPI/deflator and FX series (FRED DEX) for real and USD normalization.
  - Add credit/banking flow series (e.g., bank loans, shadow banking proxies) as optional inputs.
- **S2: Feature engineering layer**
  - New module `src/indicators/factors.py` with `build_feature_matrix`, `make_pillar_view`, and normalization utilities (FX, real, GDP scaling, growth rates, z-scores, masks).
  - Extend `transforms.py` with helpers for growth/impulse and HP/rolling gap (optional).
- **S3: Modeling layer**
  - Add `DynamicFactorModel` wrapper (statsmodels state-space) with configurable priors and sign constraints; fallback to PCA if statsmodels unavailable.
  - Implement `compute_glci` orchestrator returning pillar factors, composite, regimes, and weights metadata; store to `data/curated/glci.parquet`.
- **S4: Config & CLI wiring**
  - Add a new index entry (e.g., `global_liquidity_credit_index`) in `config/series.yml` with `method: latent_factor`.
  - Extend `Aggregator` to route `method: latent_factor` to the new modeling pipeline.
  - Add CLI command alias `python cli.py compute --index global_liquidity_credit_index --save` and optional `--pillars` flag to dump subseries.
- **S5: Evaluation tooling**
  - Notebook/script `notebooks/glci_eval.py` that runs backtests, plots pillar contributions, and exports scorecards.
  - Unit tests: feature construction, factor sign, deterministic PCA snapshot with fixed seed.
- **S6: Deployment**
  - Schedule weekly recompute (GitHub Action or cron) writing to `data/curated`; version outputs with timestamped parquet.
  - Publish a compact metadata JSON (latest value, regime, pillar scores) for the frontend.

## Deliverables
- Code modules: `src/indicators/factors.py`, `src/indicators/dynamic_factor.py` (or similar), `Aggregator` method hook.
- Data outputs: `data/curated/glci.parquet` plus `..._pillars.parquet`.
- Docs: short README section describing interpretation, update cadence, and caveats (subject to revisions).

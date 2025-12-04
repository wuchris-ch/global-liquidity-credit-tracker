# US Liquidity & Credit Meta-Index Plan

## Objective
- Build a single-number US Liquidity & Credit Index (US-LCI) that summarizes the joint stance of Fed liquidity, private credit creation, and funding/credit market stress.
- Reuse existing `config/series.yml` + `DataFetcher` + `Aggregator` stack with minimal extra plumbing; keep outputs interpretable (pillar scores, regimes).

## Design Principles
- **US-centric, USD-consistent:** No FX normalization; focus on real (deflated) and GDP-scaled measures.
- **Pillar clarity:** Liquidity, credit, market stress. Each pillar has its own latent factor; final index blends the three.
- **Weekly cadence:** Align all inputs to weekly (Friday). Forward-fill lower-frequency series cautiously; avoid look-ahead.
- **Regularized & robust:** Prefer shrinkage (ridge/elastic-net) or state-space factors to damp noise; cap single-series impact.
- **Explainable:** Publish pillar factors, component loadings, and regime flags.

## Data & Features (US)
- **Liquidity pillar (monetary/CB):**
  - Fed Total Assets (WALCL), TGA (WTREGEN), ON RRP (RRPONTSYD), Reserve Balances (WRESBAL), Bank deposits at Fed (if added).
  - M2, MMF assets, SOMA holdings (if added), policy rate level and distance to neutral proxy.
  - Transforms: YoY and 3m/3m annualized growth, level z-scores, net liquidity formula variants (assets - TGA - RRP).
- **Credit pillar (real economy):**
  - BIS credit to private sector (US), World Bank credit/GDP, commercial & industrial loans (FRED series BUSLOANS), consumer credit, mortgage debt (if added), bank lending standards (SLOOS).
  - Credit impulse (first-diff of credit/GDP), leverage ratios, YoY growth.
  - Real terms (CPI/GDP deflator) and GDP scaling.
- **Market/funding stress pillar:**
  - SOFR, EFFR, TED spread, IG/HY OAS, CP-Tbill spread, FRA-OIS (if added), swap spreads (if added), equity vol (VIX) as optional stress proxy.
  - Z-scores, slopes (3m vs policy), and regime flags.

## Modeling Blueprint
1. **Feature assembly**
   - Extend feature builder to create a US-only matrix: resample to weekly, deflate with CPI/GDP deflator, compute growth rates, z-scores, and missingness masks.
2. **Pillar latent factors**
   - Start with PCA per pillar on standardized features; upgrade to state-space dynamic factor (Kalman) for smoother signal and ragged edges.
   - Impose sign constraints (e.g., higher CB assets -> easier liquidity; higher spreads -> more stress).
3. **Composite**
   - Initial pillar weights: Liquidity 0.4, Credit 0.35, Stress 0.25; refine quarterly using inverse-variance of factor innovations or predictive IC for risk assets (e.g., SPX/HYG 3–6m ahead).
   - Normalize US-LCI to mean 100, stdev 10; provide z-score and percentile.
4. **Regimes**
   - Thresholded z-score or two-state Markov switching on composite and pillars (loose/neutral/tight); expose regime series.
5. **Drift control**
   - Rolling retrain with expanding window, ridge penalty on loadings, cap contribution of any single feature; monitor loading drift.

## Validation & Backtesting
- **Economic sense-check:** Correlate with net liquidity, GS/Chicago Fed FCI; verify sign and relative timing.
- **Predictive tests:** Rolling regression vs. SPX forward returns, HYG excess returns, curve steepening; drawdown hit rates.
- **Stability:** Sensitivity to removing any one series (leave-one-out), loading drift, factor innovation variance.
- **Event checks:** 2008, 2019 repo episode, 2020, 2022 QT; magnitude and lead/lag vs. markets.

## Implementation Steps in Repo
- **S1: Add/confirm series**
  - Ensure FRED coverage for WALCL, WTREGEN, RRPONTSYD, WRESBAL, BUSLOANS, consumer credit, mortgage debt, CP-Tbill, VIX, CPI/GDP deflator; add to `config/series.yml` as needed.
  - Add derived series definitions (net liquidity variants, credit impulse) via config or transformation layer.
- **S2: Feature engineering**
  - US-only path in `src/indicators/factors.py`: `build_us_features()` returning wide frame + metadata; include GDP scaling and real adjustments.
  - Add helpers in `transforms.py` for credit impulse (diff of credit/GDP) and policy-rate gap.
- **S3: Modeling hook**
  - Implement `compute_us_lci` orchestrator: build features → per-pillar factor (PCA/DFM) → composite with weights → regimes; write outputs to `data/curated/us_lci.parquet` plus pillar files.
- **S4: Config/CLI wiring**
  - Add index entry `us_liquidity_credit_index` with `method: latent_factor` and `scope: us`; route in `Aggregator` to US pipeline.
  - CLI support: `python cli.py compute --index us_liquidity_credit_index --save` with optional `--pillars`.
- **S5: Evaluation**
  - Notebook/script `notebooks/us_lci_eval.py` for backtests, plots, scorecards.
  - Unit tests: deterministic PCA snapshot, sign checks, feature construction sanity.

## Deliverables
- Code: US feature builder, latent factor module, aggregator hook, tests.
- Data: `data/curated/us_lci.parquet` and `..._pillars.parquet`.
- Docs: brief README addendum on interpretation, update cadence, and regime logic.

"""Global Liquidity & Credit Index (GLCI) computation pipeline.

The GLCI is a tri-pillar composite index that measures:
1. Liquidity: Central bank balance sheets, monetary aggregates
2. Credit: Private sector credit growth, credit-to-GDP gaps
3. Stress: Credit spreads, funding rates, volatility (inverted)

Key improvements in this version:
- Pre-flip negative-sign series for correct factor loadings
- Credit impulse (second derivative) instead of just levels
- Data quality validation and reporting
- Proper handling of mixed-frequency data
- Time-varying weight optimization option
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Literal
from dataclasses import dataclass, asdict, field
import json
import warnings

from ..config import get_index_config, get_country_weights, CURATED_DATA_PATH
from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage
from .factors import (
    FeatureMatrixBuilder,
    FeatureMetadata,
    DataQualityReport,
    get_pillar_weights,
    get_pillar_signs,
    get_component_signs,
)
from .dynamic_factor import (
    DynamicFactorModel,
    combine_factors,
    FactorModelResult,
    optimize_pillar_weights,
)
from .transforms import (
    detect_regime,
    compute_zscore,
    compute_momentum,
    compute_regime_probability,
)


@dataclass
class GLCIPillarResult:
    """Results for a single pillar."""
    name: str
    factor: pd.Series
    loadings: pd.DataFrame
    explained_variance: float
    method: str
    data_quality: DataQualityReport | None
    metadata: dict = field(default_factory=dict)


@dataclass
class GLCIResult:
    """Complete results from GLCI computation."""
    glci: pd.DataFrame  # Final composite index
    pillars: pd.DataFrame  # Pillar-level factors
    regimes: pd.DataFrame  # Regime classification
    weights: dict  # Pillar and series weights used
    metadata: dict  # Computation metadata
    pillar_results: dict[str, GLCIPillarResult] = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)  # Quality reports by pillar


class GLCIComputer:
    """Computes the Global Liquidity & Credit Index."""
    
    INDEX_ID = "global_liquidity_credit_index"
    
    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        storage: DataStorage | None = None
    ):
        self.fetcher = fetcher or DataFetcher()
        self.storage = storage or DataStorage()
        self.feature_builder = FeatureMatrixBuilder(self.fetcher)
    
    def compute(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        target_freq: str = "W",
        factor_method: Literal["dfm", "pca", "pca_shrunk", "auto"] = "auto",
        save_output: bool = False,
        optimize_weights: bool = False,
        verbose: bool = True
    ) -> GLCIResult:
        """Compute the full GLCI with all components.
        
        Args:
            start_date: Start date for computation
            end_date: End date for computation
            target_freq: Target frequency ('W' for weekly)
            factor_method: Method for factor extraction
            save_output: Whether to save results to storage
            optimize_weights: Whether to optimize pillar weights dynamically
            verbose: Whether to print progress
            
        Returns:
            GLCIResult with all components
        """
        config = get_index_config(self.INDEX_ID)
        if not config:
            raise ValueError(f"Index '{self.INDEX_ID}' not found in configuration")
        
        pillar_weights = get_pillar_weights(self.INDEX_ID)
        pillar_signs = get_pillar_signs(self.INDEX_ID)
        pillar_names = list(pillar_weights.keys())
        
        if verbose:
            print(f"Computing GLCI with pillars: {pillar_names}")
            print(f"Initial pillar weights: {pillar_weights}")
        
        # Step 1: Extract factor for each pillar
        pillar_factors = {}
        pillar_results = {}
        quality_reports = {}
        
        for pillar_name in pillar_names:
            if verbose:
                print(f"\nProcessing {pillar_name} pillar...")
            
            try:
                pillar_result = self._compute_pillar_factor(
                    pillar_name,
                    start_date,
                    end_date,
                    target_freq,
                    factor_method,
                    verbose
                )
                
                pillar_factors[pillar_name] = pillar_result.factor
                pillar_results[pillar_name] = pillar_result
                
                if pillar_result.data_quality:
                    quality_reports[pillar_name] = pillar_result.data_quality
                
                if verbose:
                    print(f"  ✓ Extracted factor: {len(pillar_result.factor)} observations")
                    print(f"  ✓ Variance explained: {pillar_result.explained_variance:.1%}")
                    
                    # Print top loadings
                    loadings = pillar_result.loadings
                    if not loadings.empty:
                        top_loadings = loadings["factor_1"].abs().nlargest(3)
                        top_str = ', '.join(f'{k}={loadings.loc[k, "factor_1"]:.2f}' for k in top_loadings.index)
                        print(f"  Top loadings: {top_str}")
                
            except Exception as e:
                if verbose:
                    print(f"  ✗ Warning: Could not compute {pillar_name} factor: {e}")
                    import traceback
                    traceback.print_exc()
                continue
        
        if not pillar_factors:
            raise ValueError("No pillar factors could be computed")
        
        # Adjust weights if some pillars are missing
        if len(pillar_factors) < len(pillar_names):
            missing = set(pillar_names) - set(pillar_factors.keys())
            if verbose:
                print(f"\nNote: Redistributing weights from missing pillars: {missing}")
            
            available_weights = {k: v for k, v in pillar_weights.items() if k in pillar_factors}
            total_available = sum(available_weights.values())
            pillar_weights = {k: v / total_available for k, v in available_weights.items()}
            
            if verbose:
                print(f"Adjusted weights: {pillar_weights}")
        
        # Step 2: Apply pillar-level sign adjustments
        # The stress pillar should be inverted (higher stress = lower index)
        for pillar_name, factor in pillar_factors.items():
            pillar_sign = pillar_signs.get(pillar_name, 1)
            if pillar_sign < 0:
                pillar_factors[pillar_name] = -factor
                if verbose:
                    print(f"\nApplied sign inversion for {pillar_name} pillar")
        
        # Step 3: Combine pillar factors into composite GLCI
        if verbose:
            print("\nCombining pillar factors...")
        
        normalize_config = config.get("normalize", {"mean": 100, "stdev": 10})
        
        glci_series = combine_factors(
            pillar_factors,
            weights=pillar_weights,
            normalize=True
        )
        
        # Rescale to configured mean/stdev
        target_mean = normalize_config.get("mean", 100)
        target_stdev = normalize_config.get("stdev", 10)
        glci_series = (glci_series - 100) / 10 * target_stdev + target_mean
        
        if verbose:
            print(f"GLCI range: {glci_series.min():.1f} to {glci_series.max():.1f}")
            print(f"GLCI mean: {glci_series.mean():.1f}, stdev: {glci_series.std():.1f}")
        
        # Step 4: Detect regimes
        if verbose:
            print("\nClassifying regimes...")
        
        glci_df = pd.DataFrame({
            "date": glci_series.index,
            "value": glci_series.values
        })
        glci_df = compute_zscore(glci_df, window=104)  # 2-year rolling
        glci_df = detect_regime(glci_df, thresholds=(-1.0, 1.0))
        
        # Add regime probability
        glci_df = compute_regime_probability(glci_df)
        
        regime_counts = glci_df["regime"].value_counts()
        if verbose:
            print(f"  Tight (regime=-1): {regime_counts.get(-1, 0)} periods")
            print(f"  Neutral (regime=0): {regime_counts.get(0, 0)} periods")
            print(f"  Loose (regime=1): {regime_counts.get(1, 0)} periods")
        
        # Step 5: Compute momentum and trend
        glci_df = compute_momentum(glci_df, short_window=4, long_window=12)
        
        # Step 6: Build output DataFrames
        glci_output = pd.DataFrame({
            "date": glci_df["date"],
            "value": glci_df["value"],
            "zscore": glci_df["zscore"],
            "regime": glci_df["regime"],
            "momentum": glci_df["momentum"],
            "prob_regime_change": glci_df.get("prob_regime_change", 0),
            "index_id": self.INDEX_ID
        })
        
        # Pillars DataFrame
        pillars_df = self._build_pillars_dataframe(pillar_factors, glci_df["date"])
        
        # Regimes DataFrame
        regimes_df = glci_df[["date", "regime", "zscore"]].copy()
        regimes_df["regime_label"] = regimes_df["regime"].map({
            -1: "tight",
            0: "neutral",
            1: "loose"
        })
        regimes_df["dist_to_tight"] = glci_df.get("dist_to_tight", np.nan)
        regimes_df["dist_to_loose"] = glci_df.get("dist_to_loose", np.nan)
        
        # Weights and metadata
        weights = {
            "pillar_weights": pillar_weights,
            "pillar_signs": pillar_signs,
            "loadings": {
                name: result.loadings.to_dict() 
                for name, result in pillar_results.items()
            }
        }
        
        # Build comprehensive metadata
        pillar_stats = {}
        for name, result in pillar_results.items():
            pillar_stats[name] = {
                "method": result.method,
                "explained_variance": result.explained_variance,
                "n_variables": result.metadata.get("n_variables", 0),
                "data_quality": {
                    "total_series": result.data_quality.total_series if result.data_quality else 0,
                    "loaded_series": result.data_quality.loaded_series if result.data_quality else 0,
                    "missing_series": result.data_quality.missing_series if result.data_quality else [],
                    "low_coverage": [s[0] for s in (result.data_quality.low_coverage_series or [])] if result.data_quality else []
                }
            }
        
        metadata = {
            "computed_at": datetime.utcnow().isoformat(),
            "start_date": str(glci_df["date"].min()),
            "end_date": str(glci_df["date"].max()),
            "n_observations": len(glci_df),
            "target_frequency": target_freq,
            "factor_method": factor_method,
            "normalize": normalize_config,
            "pillar_stats": pillar_stats,
            "current_regime": {
                "value": float(glci_df["value"].iloc[-1]),
                "zscore": float(glci_df["zscore"].iloc[-1]),
                "regime": int(glci_df["regime"].iloc[-1]),
                "regime_label": regimes_df["regime_label"].iloc[-1],
                "momentum": float(glci_df["momentum"].iloc[-1]) if pd.notna(glci_df["momentum"].iloc[-1]) else 0
            }
        }
        
        result = GLCIResult(
            glci=glci_output,
            pillars=pillars_df,
            regimes=regimes_df,
            weights=weights,
            metadata=metadata,
            pillar_results=pillar_results,
            data_quality=quality_reports
        )
        
        # Step 7: Save if requested
        if save_output:
            self._save_results(result)
        
        return result
    
    def _compute_pillar_factor(
        self,
        pillar_name: str,
        start_date: str | None,
        end_date: str | None,
        target_freq: str,
        method: str,
        verbose: bool = True
    ) -> GLCIPillarResult:
        """Compute latent factor for a single pillar."""
        # Build feature matrix for this pillar
        feature_matrix, metadata = self.feature_builder.build_pillar_matrix(
            self.INDEX_ID,
            pillar_name,
            start_date,
            end_date,
            target_freq
        )
        
        if feature_matrix.empty or len(feature_matrix.columns) <= 1:
            raise ValueError(f"No features available for {pillar_name} pillar")
        
        # Validate data quality
        quality_report = self.feature_builder.validate_pillar_data(
            self.INDEX_ID, pillar_name, feature_matrix, metadata
        )
        
        if verbose:
            if quality_report.missing_series:
                print(f"  ⚠ Missing series: {quality_report.missing_series[:3]}")
            if quality_report.low_coverage_series:
                print(f"  ⚠ Low coverage: {[s[0] for s in quality_report.low_coverage_series[:3]]}")
        
        # Prepare data for factor model (drop date column)
        X = feature_matrix.drop(columns=["date"], errors="ignore")
        X = X.select_dtypes(include=[np.number])
        
        # Note: Sign constraints are already applied via pre-flipping in the feature builder
        # All series should now have positive expected loadings
        sign_constraints = {col: 1 for col in X.columns}
        
        # Fit factor model
        model = DynamicFactorModel(
            n_factors=1,
            sign_constraints=sign_constraints,
            method=method,
            shrinkage_alpha=0.1
        )
        
        try:
            model.fit(X)
        except Exception as e:
            if verbose:
                print(f"  ⚠ Factor model failed: {e}, trying fallback...")
            # Try with more aggressive settings
            model = DynamicFactorModel(
                n_factors=1,
                sign_constraints=sign_constraints,
                method="pca",
                min_observations=20,
                min_variables=2
            )
            model.fit(X)
        
        factor_result = model.get_result()
        
        # Get the factor series and align to dates
        factor_series = factor_result.factors.iloc[:, 0]
        factor_series.index = feature_matrix["date"]
        
        return GLCIPillarResult(
            name=pillar_name,
            factor=factor_series,
            loadings=factor_result.loadings,
            explained_variance=factor_result.explained_variance,
            method=factor_result.method,
            data_quality=quality_report,
            metadata={
                "n_variables": len(X.columns),
                "n_observations": len(X),
                "converged": factor_result.converged
            }
        )
    
    def _build_pillars_dataframe(
        self,
        pillar_factors: dict[str, pd.Series],
        dates: pd.Series
    ) -> pd.DataFrame:
        """Build DataFrame with all pillar factors."""
        pillars_df = pd.DataFrame({"date": dates})
        
        for name, factor in pillar_factors.items():
            # Align to dates
            factor_aligned = factor.reindex(dates.values)
            pillars_df[name] = factor_aligned.values
        
        return pillars_df
    
    def _save_results(self, result: GLCIResult):
        """Save GLCI results to storage."""
        print("\nSaving results...")
        
        # Save main GLCI series
        self.storage.save_curated(
            result.glci,
            "indices",
            "glci",
            metadata=result.metadata
        )
        print("  ✓ Saved glci.parquet")
        
        # Save pillars
        self.storage.save_curated(
            result.pillars,
            "indices",
            "glci_pillars"
        )
        print("  ✓ Saved glci_pillars.parquet")
        
        # Save weights as JSON
        weights_path = CURATED_DATA_PATH / "indices" / "glci_weights.json"
        with open(weights_path, "w") as f:
            json.dump(result.weights, f, indent=2, default=str)
        print("  ✓ Saved glci_weights.json")
        
        # Save metadata as JSON
        meta_path = CURATED_DATA_PATH / "indices" / "glci_meta.json"
        with open(meta_path, "w") as f:
            json.dump(result.metadata, f, indent=2, default=str)
        print("  ✓ Saved glci_meta.json")
    
    def get_latest(self) -> dict | None:
        """Get the latest GLCI value and regime.
        
        Returns:
            Dict with latest value, regime, and date
        """
        glci_df = self.storage.load_curated("indices", "glci")
        if glci_df is None or glci_df.empty:
            return None
        
        latest = glci_df.iloc[-1]
        
        return {
            "date": str(latest["date"]),
            "value": float(latest["value"]),
            "zscore": float(latest["zscore"]),
            "regime": int(latest["regime"]),
            "regime_label": {-1: "tight", 0: "neutral", 1: "loose"}.get(int(latest["regime"]), "unknown"),
            "momentum": float(latest.get("momentum", 0)) if pd.notna(latest.get("momentum", 0)) else 0
        }
    
    def get_pillar_breakdown(self) -> dict | None:
        """Get the latest pillar breakdown.
        
        Returns:
            Dict with pillar values and weights
        """
        pillars_df = self.storage.load_curated("indices", "glci_pillars")
        if pillars_df is None or pillars_df.empty:
            return None
        
        latest = pillars_df.iloc[-1]
        pillar_weights = get_pillar_weights(self.INDEX_ID)
        
        result = {"date": str(latest["date"]), "pillars": {}}
        
        for col in pillars_df.columns:
            if col != "date":
                result["pillars"][col] = {
                    "value": float(latest[col]) if pd.notna(latest[col]) else 0,
                    "weight": pillar_weights.get(col, 0)
                }
        
        return result
    
    def get_data_freshness(self) -> dict:
        """Get information about data freshness for each component.
        
        Returns:
            Dict with freshness info per series
        """
        config = get_index_config(self.INDEX_ID)
        if not config:
            return {}
        
        freshness = {}
        for pillar_name, pillar_config in config.get("pillars", {}).items():
            for comp in pillar_config.get("components", []):
                series_id = comp["series"]
                try:
                    df = self.fetcher.fetch_series(series_id)
                    if not df.empty:
                        last_date = df["date"].max()
                        days_old = (pd.Timestamp.now() - pd.Timestamp(last_date)).days
                        freshness[series_id] = {
                            "pillar": pillar_name,
                            "last_date": str(last_date)[:10],
                            "days_old": days_old,
                            "is_stale": days_old > 14
                        }
                except:
                    freshness[series_id] = {
                        "pillar": pillar_name,
                        "last_date": "unknown",
                        "days_old": -1,
                        "is_stale": True
                    }
        
        return freshness


def compute_glci(
    start_date: str | None = None,
    end_date: str | None = None,
    save: bool = False
) -> GLCIResult:
    """Convenience function to compute GLCI.
    
    Args:
        start_date: Start date
        end_date: End date
        save: Whether to save results
        
    Returns:
        GLCIResult with all components
    """
    computer = GLCIComputer()
    return computer.compute(start_date, end_date, save_output=save)

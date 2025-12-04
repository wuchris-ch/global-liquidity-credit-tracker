"""Feature matrix builder for factor models."""
import pandas as pd
import numpy as np
from typing import Literal
from dataclasses import dataclass
import warnings

from ..config import get_series_config, get_index_config, get_country_weights
from ..etl.fetcher import DataFetcher
from .transforms import (
    resample_to_frequency,
    compute_zscore,
    compute_growth_rate,
    compute_rolling_gap,
    compute_credit_impulse,
    compute_hp_filter_gap,
    standardize_series,
    align_series,
    forward_fill_with_limit,
    apply_sign_flip,
    detect_frequency,
    get_frequency_periods,
)


@dataclass
class FeatureMetadata:
    """Metadata for a feature in the matrix."""
    series_id: str
    pillar: str
    country: str
    transform: str
    unit: str
    sign: int  # Expected sign for factor loading
    source_frequency: str  # Original data frequency
    data_quality: float  # Fraction of non-missing values
    last_updated: str  # Date of most recent observation


@dataclass
class DataQualityReport:
    """Report on data quality issues for a pillar."""
    pillar: str
    total_series: int
    loaded_series: int
    missing_series: list[str]
    low_coverage_series: list[tuple[str, float]]  # (series_id, coverage)
    stale_series: list[tuple[str, int]]  # (series_id, days_since_update)
    sign_violations: list[str]


class FeatureMatrixBuilder:
    """Builds feature matrices for factor models from configured series."""
    
    def __init__(self, fetcher: DataFetcher | None = None):
        self.fetcher = fetcher or DataFetcher()
        self._cache = {}
        self._quality_reports = {}
    
    def build_feature_matrix(
        self,
        index_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        target_freq: str = "W",
        transforms: list[str] | None = None
    ) -> tuple[pd.DataFrame, list[FeatureMetadata]]:
        """Build a feature matrix from an index configuration.
        
        Args:
            index_id: Index ID from config (e.g., 'global_liquidity_credit_index')
            start_date: Start date for data fetch
            end_date: End date for data fetch
            target_freq: Target frequency (W=weekly, M=monthly)
            transforms: List of transforms to apply ['level', 'zscore', 'growth', 'gap', 'impulse']
            
        Returns:
            Tuple of (feature_matrix DataFrame, list of FeatureMetadata)
        """
        if transforms is None:
            transforms = ["zscore"]  # Default to z-score standardization
        
        config = get_index_config(index_id)
        if not config:
            raise ValueError(f"Index '{index_id}' not found in configuration")
        
        pillars = config.get("pillars", {})
        country_weights = get_country_weights()
        
        all_features = {}
        all_metadata = []
        
        for pillar_name, pillar_config in pillars.items():
            pillar_sign = pillar_config.get("sign", 1)
            pillar_transforms = pillar_config.get("transforms", transforms)
            components = pillar_config.get("components", [])
            
            for comp in components:
                series_id = comp["series"]
                # Series-level sign combined with pillar sign
                series_sign = comp.get("sign", 1) * pillar_sign
                country = comp.get("country", "")
                comp_transforms = comp.get("transform", pillar_transforms)
                
                # Normalize transforms to list
                if isinstance(comp_transforms, str):
                    comp_transforms = [comp_transforms]
                
                # Fetch the series
                try:
                    df = self._fetch_series_cached(series_id, start_date, end_date)
                except Exception as e:
                    print(f"Warning: Could not fetch {series_id}: {e}")
                    continue
                
                if df.empty:
                    print(f"Warning: No data for {series_id}")
                    continue
                
                # Get series config for unit info
                series_config = get_series_config(series_id)
                unit = series_config.get("unit", "unknown")
                source_freq = series_config.get("frequency", "monthly")
                
                # Calculate data quality metrics
                last_date = df["date"].max()
                days_since_update = (pd.Timestamp.now() - pd.Timestamp(last_date)).days
                
                # Resample to target frequency
                df = resample_to_frequency(df, target_freq, agg_method="last")
                
                # *** KEY FIX: Apply sign flip BEFORE computing transforms ***
                # This ensures the factor loadings will have the correct sign
                if series_sign < 0:
                    df = apply_sign_flip(df, "value", series_sign)
                    # After flipping, the effective sign is now positive
                    effective_sign = 1
                else:
                    effective_sign = series_sign
                
                # Apply transforms and create features
                for transform in comp_transforms:
                    feature_name = f"{series_id}_{transform}"
                    
                    if transform == "level":
                        # Raw level (standardized)
                        transformed = standardize_series(df.copy(), method="zscore")
                        feature_values = transformed["standardized"]
                        
                    elif transform == "zscore":
                        # Rolling z-score
                        window = {"D": 252, "W": 104, "M": 24, "Q": 8}.get(target_freq, 104)
                        transformed = compute_zscore(df.copy(), window=window)
                        feature_values = transformed["zscore"]
                        
                    elif transform == "growth":
                        # Year-over-year growth
                        periods = {"D": 252, "W": 52, "M": 12, "Q": 4}.get(target_freq, 52)
                        transformed = compute_growth_rate(df.copy(), periods=periods)
                        # Standardize the growth rate
                        transformed = standardize_series(
                            transformed.rename(columns={"growth_rate": "value"}),
                            value_col="value",
                            method="zscore"
                        )
                        feature_values = transformed["standardized"]
                        
                    elif transform == "gap":
                        # Deviation from rolling mean
                        window = {"D": 504, "W": 104, "M": 24, "Q": 8}.get(target_freq, 104)
                        transformed = compute_rolling_gap(df.copy(), window=window)
                        # Standardize the gap
                        transformed = standardize_series(
                            transformed.rename(columns={"gap_pct": "value"}),
                            value_col="value",
                            method="zscore"
                        )
                        feature_values = transformed["standardized"]
                        
                    elif transform == "impulse":
                        # Credit impulse (second derivative)
                        periods = {"D": 252, "W": 52, "M": 12, "Q": 4}.get(target_freq, 4)
                        transformed = compute_credit_impulse(df.copy(), periods=periods)
                        # Standardize the impulse
                        if transformed["credit_impulse"].notna().sum() > 10:
                            transformed = standardize_series(
                                transformed.rename(columns={"credit_impulse": "value"}),
                                value_col="value",
                                method="zscore"
                            )
                            feature_values = transformed["standardized"]
                        else:
                            continue  # Skip if insufficient data
                        
                    elif transform == "hp_gap":
                        # HP filter gap
                        lamb = {"Q": 1600, "M": 129600, "A": 6.25}.get(target_freq, 1600)
                        transformed = compute_hp_filter_gap(df.copy(), lamb=lamb)
                        if transformed["hp_gap"].notna().sum() > 10:
                            transformed = standardize_series(
                                transformed.rename(columns={"hp_gap": "value"}),
                                value_col="value",
                                method="zscore"
                            )
                            feature_values = transformed["standardized"]
                        else:
                            continue
                            
                    else:
                        continue
                    
                    # Calculate coverage for this feature
                    coverage = feature_values.notna().sum() / len(feature_values) if len(feature_values) > 0 else 0
                    
                    # Store feature with date index
                    feature_df = pd.DataFrame({
                        "date": df["date"],
                        feature_name: feature_values.values if hasattr(feature_values, 'values') else feature_values
                    })
                    all_features[feature_name] = feature_df
                    
                    # Store metadata - note: sign is now always positive after pre-flipping
                    all_metadata.append(FeatureMetadata(
                        series_id=series_id,
                        pillar=pillar_name,
                        country=country or series_config.get("country", ""),
                        transform=transform,
                        unit=unit,
                        sign=effective_sign,  # Always positive after pre-flip
                        source_frequency=source_freq,
                        data_quality=coverage,
                        last_updated=str(last_date)[:10] if pd.notna(last_date) else "unknown"
                    ))
        
        if not all_features:
            raise ValueError("No features could be built from configuration")
        
        # Align all features to common dates
        aligned = self._align_features(all_features)
        
        return aligned, all_metadata
    
    def build_pillar_matrix(
        self,
        index_id: str,
        pillar_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
        target_freq: str = "W"
    ) -> tuple[pd.DataFrame, list[FeatureMetadata]]:
        """Build feature matrix for a single pillar."""
        full_matrix, full_metadata = self.build_feature_matrix(
            index_id, start_date, end_date, target_freq
        )
        
        # Filter to only this pillar
        pillar_cols = ["date"]
        pillar_metadata = []
        
        for meta in full_metadata:
            if meta.pillar == pillar_name:
                col_name = f"{meta.series_id}_{meta.transform}"
                if col_name in full_matrix.columns:
                    pillar_cols.append(col_name)
                    pillar_metadata.append(meta)
        
        return full_matrix[pillar_cols], pillar_metadata
    
    def validate_pillar_data(
        self,
        index_id: str,
        pillar_name: str,
        matrix: pd.DataFrame,
        metadata: list[FeatureMetadata]
    ) -> DataQualityReport:
        """Validate data quality for a pillar.
        
        Returns a report with warnings about data issues.
        """
        config = get_index_config(index_id)
        pillar_config = config.get("pillars", {}).get(pillar_name, {})
        expected_series = [c["series"] for c in pillar_config.get("components", [])]
        
        loaded_series = list(set(m.series_id for m in metadata))
        missing_series = [s for s in expected_series if s not in loaded_series]
        
        # Check coverage
        low_coverage = []
        stale_series = []
        
        for meta in metadata:
            if meta.data_quality < 0.5:
                low_coverage.append((meta.series_id, meta.data_quality))
            
            try:
                days_old = (pd.Timestamp.now() - pd.Timestamp(meta.last_updated)).days
                if days_old > 30:
                    stale_series.append((meta.series_id, days_old))
            except:
                pass
        
        report = DataQualityReport(
            pillar=pillar_name,
            total_series=len(expected_series),
            loaded_series=len(loaded_series),
            missing_series=missing_series,
            low_coverage_series=low_coverage,
            stale_series=stale_series,
            sign_violations=[]  # Will be filled after factor extraction
        )
        
        self._quality_reports[pillar_name] = report
        return report
    
    def get_quality_reports(self) -> dict[str, DataQualityReport]:
        """Get all data quality reports."""
        return self._quality_reports
    
    def _fetch_series_cached(
        self,
        series_id: str,
        start_date: str | None,
        end_date: str | None
    ) -> pd.DataFrame:
        """Fetch series with caching."""
        cache_key = f"{series_id}_{start_date}_{end_date}"
        
        if cache_key not in self._cache:
            self._cache[cache_key] = self.fetcher.fetch_series(
                series_id, start_date, end_date
            )
        
        return self._cache[cache_key].copy()
    
    def _align_features(
        self,
        features: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """Align all features to common dates using outer join with forward fill."""
        if not features:
            return pd.DataFrame()
        
        # Convert to dict format expected by align_series
        series_dict = {}
        for name, df in features.items():
            series_dict[name] = df.rename(columns={name: "value"})
        
        aligned = align_series(series_dict, method="outer", fill_method="ffill")
        
        # For low-frequency series that were forward-filled, apply a more
        # aggressive fill to ensure we have enough observations
        numeric_cols = aligned.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            # Extended forward fill with limit of 13 weeks (one quarter)
            aligned[col] = aligned[col].ffill(limit=13)
            # Also backfill for initial observations
            aligned[col] = aligned[col].bfill(limit=4)
        
        return aligned


def normalize_to_usd_dynamic(
    df: pd.DataFrame,
    fx_df: pd.DataFrame,
    value_col: str = "value",
    fx_col: str = "value",
    fx_type: Literal["usd_per_foreign", "foreign_per_usd"] = "foreign_per_usd"
) -> pd.DataFrame:
    """Normalize values to USD using time-varying exchange rates.
    
    Args:
        df: DataFrame with date and value columns
        fx_df: DataFrame with date and FX rate
        value_col: Name of value column in df
        fx_col: Name of FX column
        fx_type: Direction of FX quote
        
    Returns:
        DataFrame with value_usd column added
    """
    df = df.copy()
    
    # Align FX rates to df dates
    df["date"] = pd.to_datetime(df["date"])
    fx_df = fx_df.copy()
    fx_df["date"] = pd.to_datetime(fx_df["date"])
    
    # Merge on date (using asof merge for nearest date)
    merged = pd.merge_asof(
        df.sort_values("date"),
        fx_df[["date", fx_col]].sort_values("date").rename(columns={fx_col: "fx_rate"}),
        on="date",
        direction="backward"
    )
    
    if fx_type == "foreign_per_usd":
        # e.g., JPY/USD = 150 means 150 JPY per 1 USD
        merged["value_usd"] = merged[value_col] / merged["fx_rate"]
    else:
        # e.g., USD/EUR = 1.10 means 1.10 USD per 1 EUR
        merged["value_usd"] = merged[value_col] * merged["fx_rate"]
    
    return merged


def get_pillar_series_ids(index_id: str, pillar_name: str) -> list[str]:
    """Get series IDs for a specific pillar."""
    config = get_index_config(index_id)
    if not config:
        return []
    
    pillar = config.get("pillars", {}).get(pillar_name, {})
    return [comp["series"] for comp in pillar.get("components", [])]


def get_pillar_weights(index_id: str) -> dict[str, float]:
    """Get pillar weights from index configuration."""
    config = get_index_config(index_id)
    if not config:
        return {}
    
    weights = {}
    for pillar_name, pillar_config in config.get("pillars", {}).items():
        weights[pillar_name] = pillar_config.get("weight", 1.0)
    
    # Normalize weights to sum to 1
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights


def get_pillar_signs(index_id: str) -> dict[str, int]:
    """Get pillar signs from index configuration."""
    config = get_index_config(index_id)
    if not config:
        return {}
    
    signs = {}
    for pillar_name, pillar_config in config.get("pillars", {}).items():
        signs[pillar_name] = pillar_config.get("sign", 1)
    
    return signs


def get_component_signs(index_id: str, pillar_name: str) -> dict[str, int]:
    """Get expected signs for all components in a pillar.
    
    Returns dict mapping series_id to expected sign.
    """
    config = get_index_config(index_id)
    if not config:
        return {}
    
    pillar = config.get("pillars", {}).get(pillar_name, {})
    pillar_sign = pillar.get("sign", 1)
    
    signs = {}
    for comp in pillar.get("components", []):
        series_id = comp["series"]
        comp_sign = comp.get("sign", 1)
        # Combined sign = pillar sign * component sign
        signs[series_id] = pillar_sign * comp_sign
    
    return signs

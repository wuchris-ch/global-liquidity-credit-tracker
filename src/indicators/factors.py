"""Feature matrix builder for factor models."""
import pandas as pd
import numpy as np
from typing import Literal
from dataclasses import dataclass

from ..config import get_series_config, get_index_config
from ..data_quality import staleness_allowance_days
from ..etl.fetcher import DataFetcher
from .transforms import (
    compute_zscore,
    compute_growth_rate,
    compute_rolling_gap,
    compute_credit_impulse,
    compute_hp_filter_gap,
    standardize_series,
    align_series,
)


_TARGET_FREQUENCIES = {
    "D": "D",
    "W": "W-FRI",
    "M": "ME",
    "Q": "QE",
    "A": "YE",
}

_SOURCE_FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 31,
    "quarterly": 92,
    "annual": 366,
}

_TARGET_FREQUENCY_DAYS = {
    "D": 1,
    "W": 7,
    "M": 31,
    "Q": 92,
    "A": 366,
}


def _finite_transform_frame(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Select one derived transform and convert non-finite values to missing."""
    transformed = df[["date", column]].rename(columns={column: "value"}).copy()
    transformed["value"] = pd.to_numeric(
        transformed["value"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    return transformed


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
    availability_lag_days: int = 0  # Delay from period end to signal eligibility


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
    
    def __init__(self, fetcher: DataFetcher | None = None) -> None:
        self.fetcher = fetcher or DataFetcher()
        self._cache: dict[str, pd.DataFrame] = {}
        self._quality_reports: dict[str, DataQualityReport] = {}
    
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
        all_features = {}
        all_metadata = []
        
        for pillar_name, pillar_config in pillars.items():
            pillar_transforms = pillar_config.get("transforms", transforms)
            components = pillar_config.get("components", [])
            
            for comp in components:
                series_id = comp["series"]
                # Component signs orient inputs within a pillar. Pillar signs are
                # intentionally applied once, after factor extraction, when the
                # pillar is aggregated into the GLCI.
                series_sign = comp.get("sign", 1)
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
                availability_lag_days = series_config.get(
                    "availability_lag_days",
                    0,
                )
                if (
                    isinstance(availability_lag_days, bool)
                    or not isinstance(availability_lag_days, int)
                    or availability_lag_days < 0
                ):
                    raise ValueError(
                        f"Series '{series_id}' has invalid availability_lag_days: "
                        f"{availability_lag_days!r}"
                    )
                
                # Calculate data quality metrics
                last_date = df["date"].max()
                # Put raw observations on the target clock before applying any
                # row-based transform. This makes a 52-period growth transform
                # mean 52 calendar weeks even for monthly or quarterly inputs.
                df = self._regularize_series(
                    df,
                    source_freq,
                    target_freq,
                    availability_lag_days=availability_lag_days,
                    as_of_date=end_date or pd.Timestamp.now().normalize(),
                )
                if df.empty:
                    print(f"Warning: No completed {target_freq} periods for {series_id}")
                    continue
                
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
                            _finite_transform_frame(transformed, "growth_rate"),
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
                            _finite_transform_frame(transformed, "gap_pct"),
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
                                _finite_transform_frame(
                                    transformed,
                                    "credit_impulse",
                                ),
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
                                _finite_transform_frame(transformed, "hp_gap"),
                                value_col="value",
                                method="zscore"
                            )
                            feature_values = transformed["standardized"]
                        else:
                            continue
                            
                    else:
                        continue

                    # Orient the transformed signal, not its raw level. Applying
                    # a negative sign before a ratio transform such as pct_change
                    # cancels out because (-new / -old) == (new / old).
                    feature_values = (feature_values * series_sign).replace(
                        [np.inf, -np.inf],
                        np.nan,
                    )
                    
                    # Calculate coverage for this feature
                    coverage = feature_values.notna().sum() / len(feature_values) if len(feature_values) > 0 else 0
                    if coverage == 0:
                        # A fetched series can still be unusable for a long-window
                        # transform. Do not pass an all-missing feature to the
                        # factor model or count it as fitted coverage.
                        continue
                    
                    # Store feature with date index
                    feature_df = pd.DataFrame({
                        "date": df["date"],
                        feature_name: feature_values.values if hasattr(feature_values, 'values') else feature_values
                    })
                    all_features[feature_name] = feature_df
                    
                    all_metadata.append(FeatureMetadata(
                        series_id=series_id,
                        pillar=pillar_name,
                        country=country or series_config.get("country", ""),
                        transform=transform,
                        unit=unit,
                        sign=1,  # component orientation has already been consumed
                        source_frequency=source_freq,
                        data_quality=coverage,
                        last_updated=str(last_date)[:10] if pd.notna(last_date) else "unknown",
                        availability_lag_days=availability_lag_days,
                    ))
        
        if not all_features:
            raise ValueError("No features could be built from configuration")
        
        # Align all features to common dates
        aligned = self._align_features(
            all_features,
            target_freq=target_freq,
        )
        
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
        low_coverage_by_series: dict[str, float] = {}
        stale_by_series: dict[str, int] = {}
        
        for meta in metadata:
            if meta.data_quality < 0.5:
                prior_coverage = low_coverage_by_series.get(meta.series_id, 1.0)
                low_coverage_by_series[meta.series_id] = min(
                    prior_coverage,
                    meta.data_quality,
                )

            # last_updated is "unknown" when source data had no valid dates; skip
            # the staleness check in that case instead of crashing.
            if meta.last_updated == "unknown":
                continue
            days_old = (pd.Timestamp.now() - pd.Timestamp(meta.last_updated)).days
            stale_after_days = staleness_allowance_days(meta.source_frequency)
            if days_old > stale_after_days:
                stale_by_series[meta.series_id] = max(
                    stale_by_series.get(meta.series_id, 0),
                    days_old,
                )

        low_coverage = sorted(low_coverage_by_series.items())
        stale_series = sorted(stale_by_series.items())
        
        report = DataQualityReport(
            pillar=pillar_name,
            total_series=len(expected_series),
            loaded_series=len(loaded_series),
            missing_series=missing_series,
            low_coverage_series=low_coverage,
            stale_series=stale_series,
            sign_violations=[],
        )
        
        self._quality_reports[pillar_name] = report
        return report
    
    def get_quality_reports(self) -> dict[str, DataQualityReport]:
        """Get all data quality reports."""
        return self._quality_reports

    def record_sign_violations(
        self,
        pillar_name: str,
        violations: list[str],
    ) -> None:
        """Attach a post-estimation loading-sign audit to a pillar report."""
        report = self._quality_reports.get(pillar_name)
        if report is not None:
            report.sign_violations = list(dict.fromkeys(violations))
    
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
        features: dict[str, pd.DataFrame],
        target_freq: str = "W",
    ) -> pd.DataFrame:
        """Outer-align already regularized features on an explicit clock.

        Raw series are regularized before their transforms, so this final step
        does not fill any missing feature values. Values before a series' first
        observation remain missing.
        """
        if not features:
            return pd.DataFrame()

        if target_freq not in _TARGET_FREQUENCIES:
            raise ValueError(f"Unsupported target frequency: {target_freq}")

        # Convert to dict format expected by align_series
        series_dict = {}
        for name, df in features.items():
            series_dict[name] = df.rename(columns={name: "value"})
        
        aligned = align_series(series_dict, method="outer", fill_method=None)
        aligned["date"] = pd.to_datetime(aligned["date"])
        aligned = aligned.sort_values("date").set_index("date")

        start = aligned.index.min()
        end = aligned.index.max()
        grid = pd.date_range(start=start, end=end, freq=_TARGET_FREQUENCIES[target_freq])
        aligned = aligned.reindex(grid)
        aligned.index.name = "date"

        return aligned.reset_index()

    def _regularize_series(
        self,
        df: pd.DataFrame,
        source_frequency: str,
        target_freq: str,
        availability_lag_days: int = 0,
        as_of_date: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Put values on their availability clock, then bounded-fill target periods."""
        if target_freq not in _TARGET_FREQUENCIES:
            raise ValueError(f"Unsupported target frequency: {target_freq}")
        if (
            isinstance(availability_lag_days, bool)
            or not isinstance(availability_lag_days, int)
            or availability_lag_days < 0
        ):
            raise ValueError(
                "availability_lag_days must be a non-negative integer"
            )
        if df.empty:
            return pd.DataFrame(columns=["date", "value"])

        values = df[["date", "value"]].copy()
        values["date"] = pd.to_datetime(values["date"])
        if values["date"].dt.tz is not None:
            values["date"] = values["date"].dt.tz_localize(None)
        values = values.dropna(subset=["date"]).sort_values("date")
        if values.empty:
            return pd.DataFrame(columns=["date", "value"])

        # FRED and several macro APIs label monthly or quarterly observations
        # with the first day of the period even when the value describes its
        # end. Such a value cannot be signal-eligible before that period ends.
        period_frequency = {
            "monthly": "M",
            "quarterly": "Q",
            "annual": "Y",
        }.get(source_frequency.lower())
        if period_frequency is not None:
            values["date"] = (
                values["date"]
                .dt.to_period(period_frequency)
                .dt.end_time
                .dt.normalize()
            )

        values["date"] = values["date"] + pd.Timedelta(
            days=availability_lag_days
        )
        cutoff = pd.Timestamp(
            as_of_date if as_of_date is not None else values["date"].max()
        )
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_localize(None)
        cutoff = cutoff.normalize()
        values = values.loc[values["date"] <= cutoff]
        if values.empty:
            return pd.DataFrame(columns=["date", "value"])

        series = values.set_index("date")["value"]
        regularized = series.resample(_TARGET_FREQUENCIES[target_freq]).last()
        grid_end = regularized.index.max()

        if target_freq == "W":
            # A value is eligible only on a completed Friday signal date. An
            # explicit as-of date lets lower-frequency releases carry forward
            # after their release week without creating a future observation.
            # A Friday cutoff is not assumed complete because scheduled runs
            # occur before the US market close; it becomes eligible Saturday.
            last_completed_friday = pd.offsets.Week(weekday=4).rollback(
                cutoff - pd.Timedelta(days=1)
            )
            regularized = regularized.loc[regularized.index <= last_completed_friday]
            grid_end = last_completed_friday

        if regularized.empty:
            return pd.DataFrame(columns=["date", "value"])

        grid = pd.date_range(
            regularized.index.min(),
            grid_end,
            freq=_TARGET_FREQUENCIES[target_freq],
        )
        regularized = regularized.reindex(grid)
        fill_limit = self._forward_fill_limit(source_frequency, target_freq)
        regularized = regularized.ffill(limit=fill_limit)
        regularized.index.name = "date"
        return regularized.rename("value").reset_index()

    @staticmethod
    def _forward_fill_limit(source_frequency: str, target_freq: str) -> int:
        """Return a bounded carry-forward window in target periods."""
        source_days = _SOURCE_FREQUENCY_DAYS.get(source_frequency.lower(), 7)
        target_days = _TARGET_FREQUENCY_DAYS[target_freq]
        # One grace period accommodates release timing and holiday weeks while
        # still allowing stale series to become missing rather than live forever.
        return max(1, int(np.ceil(source_days / target_days)) + 1)


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
    """Get within-pillar signs for all components in a pillar.
    
    Pillar-level orientation is deliberately excluded and is applied once when
    pillar factors are combined into the composite.
    """
    config = get_index_config(index_id)
    if not config:
        return {}
    
    pillar = config.get("pillars", {}).get(pillar_name, {})
    
    signs = {}
    for comp in pillar.get("components", []):
        series_id = comp["series"]
        comp_sign = comp.get("sign", 1)
        signs[series_id] = comp_sign
    
    return signs

"""Aggregator for computing composite indices."""
import pandas as pd
import numpy as np
from typing import Literal

from ..config import get_index_config, get_all_indices, get_country_weights
from ..etl.fetcher import DataFetcher
from .transforms import (
    resample_to_frequency,
    compute_zscore,
    align_series,
)


class Aggregator:
    """Computes composite liquidity and credit indices."""
    
    def __init__(self, fetcher: DataFetcher | None = None):
        self.fetcher = fetcher or DataFetcher()
        self._cache = {}
    
    def compute_index(
        self,
        index_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """Compute a composite index by its config ID.
        
        Args:
            index_id: Index ID from config/series.yml
            start_date: Optional start date
            end_date: Optional end date
            use_cache: Whether to use cached component data
            
        Returns:
            DataFrame with date and index value
        """
        config = get_index_config(index_id)
        if not config:
            raise ValueError(f"Index '{index_id}' not found in configuration")
        
        method = config.get("method", "arithmetic")
        components = config.get("components", [])
        frequency = config.get("frequency", "M")
        
        # Fetch component series
        component_data = {}
        for comp in components:
            series_id = comp["series"]
            
            cache_key = f"{series_id}_{start_date}_{end_date}"
            if use_cache and cache_key in self._cache:
                df = self._cache[cache_key]
            else:
                df = self.fetcher.fetch_series(series_id, start_date, end_date)
                self._cache[cache_key] = df
            
            component_data[series_id] = df
        
        # Compute based on method
        if method == "arithmetic" or index_id == "fed_net_liquidity":
            return self._compute_arithmetic(index_id, component_data, components, frequency)
        elif method == "zscore_average":
            return self._compute_zscore_average(index_id, component_data, components, frequency)
        elif method == "sum_normalized":
            return self._compute_sum_normalized(index_id, component_data, components, frequency)
        elif method == "weighted_average":
            return self._compute_weighted_average(index_id, component_data, components, frequency)
        else:
            raise ValueError(f"Unknown aggregation method: {method}")
    
    def _compute_arithmetic(
        self,
        index_id: str,
        data: dict[str, pd.DataFrame],
        components: list[dict],
        frequency: str
    ) -> pd.DataFrame:
        """Compute arithmetic combination (add/subtract)."""
        # Resample all to target frequency
        resampled = {}
        for series_id, df in data.items():
            resampled[series_id] = resample_to_frequency(
                df, frequency, agg_method="last"
            )
        
        # Align series
        aligned = align_series(resampled, method="inner")
        
        # Apply operations
        result = pd.Series(0.0, index=aligned.index)
        
        for comp in components:
            series_id = comp["series"]
            operation = comp.get("operation", "add")
            weight = comp.get("weight", 1.0)
            
            if series_id in aligned.columns:
                if operation == "add":
                    result += aligned[series_id] * weight
                elif operation == "subtract":
                    result -= aligned[series_id] * weight
                elif operation == "multiply":
                    result *= aligned[series_id] * weight
        
        return pd.DataFrame({
            "date": aligned["date"],
            "value": result,
            "index_id": index_id
        })
    
    def _compute_zscore_average(
        self,
        index_id: str,
        data: dict[str, pd.DataFrame],
        components: list[dict],
        frequency: str
    ) -> pd.DataFrame:
        """Compute weighted average of z-scores."""
        # Resample and compute z-scores
        zscores = {}
        for series_id, df in data.items():
            resampled = resample_to_frequency(df, frequency, agg_method="mean")
            with_zscore = compute_zscore(resampled, window=252)  # ~1 year rolling
            zscores[series_id] = with_zscore[["date", "zscore"]].rename(
                columns={"zscore": series_id}
            )
        
        # Align
        aligned = align_series(
            {k: v.rename(columns={k: "value"}) for k, v in zscores.items()},
            method="inner"
        )
        
        # Weighted average
        total_weight = 0
        result = pd.Series(0.0, index=aligned.index)
        
        for comp in components:
            series_id = comp["series"]
            weight = comp.get("weight", 1.0)
            
            if series_id in aligned.columns:
                result += aligned[series_id].fillna(0) * weight
                total_weight += weight
        
        if total_weight > 0:
            result /= total_weight
        
        return pd.DataFrame({
            "date": aligned["date"],
            "value": result,
            "index_id": index_id
        })
    
    def _compute_sum_normalized(
        self,
        index_id: str,
        data: dict[str, pd.DataFrame],
        components: list[dict],
        frequency: str
    ) -> pd.DataFrame:
        """Compute sum of normalized (currency-adjusted) values."""
        # Resample all to target frequency
        resampled = {}
        for series_id, df in data.items():
            resampled[series_id] = resample_to_frequency(
                df, frequency, agg_method="last"
            )
        
        # Align series
        aligned = align_series(resampled, method="outer", fill_method="ffill")
        
        # Sum with weights (weights act as FX conversion factors)
        result = pd.Series(0.0, index=aligned.index)
        
        for comp in components:
            series_id = comp["series"]
            weight = comp.get("weight", 1.0)  # FX rate or conversion factor
            
            if series_id in aligned.columns:
                result += aligned[series_id].fillna(0) * weight
        
        return pd.DataFrame({
            "date": aligned["date"],
            "value": result,
            "index_id": index_id
        })
    
    def _compute_weighted_average(
        self,
        index_id: str,
        data: dict[str, pd.DataFrame],
        components: list[dict],
        frequency: str
    ) -> pd.DataFrame:
        """Compute GDP-weighted average across countries."""
        country_weights = get_country_weights()
        
        # Resample all to target frequency
        resampled = {}
        for series_id, df in data.items():
            resampled[series_id] = resample_to_frequency(
                df, frequency, agg_method="last"
            )
        
        # Align series
        aligned = align_series(resampled, method="outer", fill_method="ffill")
        
        # Weighted average
        total_weight = 0
        result = pd.Series(0.0, index=aligned.index)
        
        for comp in components:
            series_id = comp["series"]
            country = comp.get("country", "")
            weight = country_weights.get(country, comp.get("weight", 1.0))
            
            if series_id in aligned.columns:
                result += aligned[series_id].fillna(0) * weight
                total_weight += weight
        
        if total_weight > 0:
            result /= total_weight
        
        return pd.DataFrame({
            "date": aligned["date"],
            "value": result,
            "index_id": index_id
        })
    
    def compute_all_indices(
        self,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> dict[str, pd.DataFrame]:
        """Compute all configured indices."""
        all_indices = get_all_indices()
        results = {}
        
        for index_id in all_indices:
            try:
                results[index_id] = self.compute_index(index_id, start_date, end_date)
            except Exception as e:
                print(f"Warning: Failed to compute {index_id}: {e}")
        
        return results
    
    def compute_fed_net_liquidity(
        self,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> pd.DataFrame:
        """Convenience method for Fed Net Liquidity index."""
        return self.compute_index("fed_net_liquidity", start_date, end_date)
    
    def compute_funding_stress(
        self,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> pd.DataFrame:
        """Convenience method for USD Funding Stress index."""
        return self.compute_index("usd_funding_stress", start_date, end_date)

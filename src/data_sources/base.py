"""Base class for data source clients."""
from abc import ABC, abstractmethod
import pandas as pd
from pathlib import Path
from datetime import datetime


class BaseClient(ABC):
    """Abstract base class for all data source clients."""
    
    source_name: str = "base"
    
    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path
        if cache_path:
            cache_path.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def get_series(self, series_id: str, start_date: str | None = None, 
                   end_date: str | None = None) -> pd.DataFrame:
        """Fetch a time series from the data source.
        
        Returns DataFrame with columns: date, value, source, series_id
        """
        pass
    
    def _standardize_output(self, df: pd.DataFrame, series_id: str) -> pd.DataFrame:
        """Standardize output format across all sources."""
        df = df.copy()
        df["source"] = self.source_name
        df["series_id"] = series_id
        df["fetched_at"] = datetime.utcnow().isoformat()
        
        # Ensure date column is datetime
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        
        return df[["date", "value", "source", "series_id", "fetched_at"]]
    
    def _cache_key(self, series_id: str) -> Path:
        """Generate cache file path for a series."""
        if not self.cache_path:
            raise ValueError("Cache path not set")
        return self.cache_path / f"{self.source_name}_{series_id}.parquet"
    
    def _load_from_cache(self, series_id: str) -> pd.DataFrame | None:
        """Load series from cache if available."""
        cache_file = self._cache_key(series_id)
        if cache_file.exists():
            return pd.read_parquet(cache_file)
        return None
    
    def _save_to_cache(self, df: pd.DataFrame, series_id: str) -> None:
        """Save series to cache."""
        if self.cache_path:
            df.to_parquet(self._cache_key(series_id), index=False)

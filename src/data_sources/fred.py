"""FRED (Federal Reserve Economic Data) client."""
import pandas as pd
from pathlib import Path
from fredapi import Fred
from .base import BaseClient
from ..config import FRED_API_KEY


class FredClient(BaseClient):
    """Client for fetching data from FRED API."""
    
    source_name = "fred"
    
    def __init__(self, api_key: str | None = None, cache_path: Path | None = None):
        super().__init__(cache_path)
        self.api_key = api_key or FRED_API_KEY
        if not self.api_key:
            raise ValueError(
                "FRED API key required. Set FRED_API_KEY env var or pass api_key parameter. "
                "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        self._client = Fred(api_key=self.api_key)
    
    def get_series(self, series_id: str, start_date: str | None = None,
                   end_date: str | None = None) -> pd.DataFrame:
        """Fetch a series from FRED.
        
        Args:
            series_id: FRED series ID (e.g., 'WALCL', 'SOFR')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            
        Returns:
            DataFrame with date, value, source, series_id columns
        """
        try:
            data = self._client.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date
            )
            
            df = pd.DataFrame({
                "date": data.index,
                "value": data.values
            })
            
            # Drop NaN values
            df = df.dropna(subset=["value"])
            
            return self._standardize_output(df, series_id)
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch FRED series {series_id}: {e}")
    
    def get_series_info(self, series_id: str) -> dict:
        """Get metadata about a FRED series."""
        try:
            info = self._client.get_series_info(series_id)
            return info.to_dict()
        except Exception as e:
            raise RuntimeError(f"Failed to get info for FRED series {series_id}: {e}")
    
    def search_series(self, query: str, limit: int = 10) -> pd.DataFrame:
        """Search for FRED series by keyword."""
        try:
            results = self._client.search(query, limit=limit)
            return results
        except Exception as e:
            raise RuntimeError(f"Failed to search FRED: {e}")


# Convenience function for quick access
def get_fred_series(series_id: str, start_date: str | None = None,
                    end_date: str | None = None) -> pd.DataFrame:
    """Quick helper to fetch a FRED series."""
    client = FredClient()
    return client.get_series(series_id, start_date, end_date)

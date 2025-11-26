"""Data fetcher that orchestrates pulling data from all sources."""
import pandas as pd
from datetime import datetime
from typing import Literal

from ..config import get_series_config, get_all_series, RAW_DATA_PATH
from ..data_sources import FredClient, BISClient, WorldBankClient, NYFedClient


class DataFetcher:
    """Orchestrates data fetching from all configured sources."""
    
    def __init__(self, fred_api_key: str | None = None):
        self._clients = {}
        self._fred_api_key = fred_api_key
    
    def _get_client(self, source: str):
        """Get or create a client for the given source."""
        if source not in self._clients:
            cache_path = RAW_DATA_PATH / source
            
            if source == "fred":
                self._clients[source] = FredClient(
                    api_key=self._fred_api_key,
                    cache_path=cache_path
                )
            elif source == "bis":
                self._clients[source] = BISClient(cache_path=cache_path)
            elif source == "worldbank":
                self._clients[source] = WorldBankClient(cache_path=cache_path)
            elif source == "nyfed":
                self._clients[source] = NYFedClient(cache_path=cache_path)
            else:
                raise ValueError(f"Unknown data source: {source}")
        
        return self._clients[source]
    
    def fetch_series(self, series_id: str, start_date: str | None = None,
                     end_date: str | None = None) -> pd.DataFrame:
        """Fetch a single series by its config ID.
        
        Args:
            series_id: The series ID from config/series.yml
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            DataFrame with standardized columns
        """
        config = get_series_config(series_id)
        if not config:
            raise ValueError(f"Series '{series_id}' not found in configuration")
        
        source = config["source"]
        source_id = config["source_id"]
        
        client = self._get_client(source)
        
        # Handle source-specific fetching
        if source == "worldbank":
            country = config.get("country", "all")
            df = client.get_series(source_id, start_date, end_date, country=country)
        else:
            df = client.get_series(source_id, start_date, end_date)
        
        # Add metadata from config
        df["config_id"] = series_id
        df["country"] = config.get("country", "")
        df["frequency"] = config.get("frequency", "")
        df["type"] = config.get("type", "")
        df["unit"] = config.get("unit", "")
        
        return df
    
    def fetch_multiple(self, series_ids: list[str], start_date: str | None = None,
                       end_date: str | None = None) -> dict[str, pd.DataFrame]:
        """Fetch multiple series.
        
        Returns:
            Dict mapping series_id to DataFrame
        """
        results = {}
        errors = {}
        
        for series_id in series_ids:
            try:
                results[series_id] = self.fetch_series(series_id, start_date, end_date)
            except Exception as e:
                errors[series_id] = str(e)
                print(f"Warning: Failed to fetch {series_id}: {e}")
        
        if errors:
            print(f"\nFailed to fetch {len(errors)} series: {list(errors.keys())}")
        
        return results
    
    def fetch_all(self, start_date: str | None = None,
                  end_date: str | None = None) -> dict[str, pd.DataFrame]:
        """Fetch all configured series."""
        all_series = get_all_series()
        return self.fetch_multiple(list(all_series.keys()), start_date, end_date)
    
    def fetch_by_source(self, source: Literal["fred", "bis", "worldbank", "nyfed"],
                        start_date: str | None = None,
                        end_date: str | None = None) -> dict[str, pd.DataFrame]:
        """Fetch all series from a specific source."""
        all_series = get_all_series()
        series_ids = [
            sid for sid, cfg in all_series.items()
            if cfg.get("source") == source
        ]
        return self.fetch_multiple(series_ids, start_date, end_date)
    
    def fetch_by_country(self, country: str, start_date: str | None = None,
                         end_date: str | None = None) -> dict[str, pd.DataFrame]:
        """Fetch all series for a specific country."""
        all_series = get_all_series()
        series_ids = [
            sid for sid, cfg in all_series.items()
            if cfg.get("country") == country
        ]
        return self.fetch_multiple(series_ids, start_date, end_date)

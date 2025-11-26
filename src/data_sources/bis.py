"""BIS (Bank for International Settlements) SDMX client."""
import pandas as pd
import requests
from pathlib import Path
from .base import BaseClient


class BISClient(BaseClient):
    """Client for fetching data from BIS SDMX API.
    
    BIS provides credit to non-financial sector, debt statistics, 
    and international banking data.
    
    API docs: https://www.bis.org/statistics/sdmx_techspec.htm
    """
    
    source_name = "bis"
    BASE_URL = "https://stats.bis.org/api/v1"
    
    # Common dataflows
    DATAFLOWS = {
        "credit": "WS_TC",           # Total credit to non-financial sector
        "debt": "WS_DEBT_SEC2_PUB",  # Debt securities statistics
        "property": "WS_SPP",         # Property prices
    }
    
    def __init__(self, cache_path: Path | None = None):
        super().__init__(cache_path)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.sdmx.data+json;version=1.0.0"
        })
    
    def get_series(self, series_id: str, start_date: str | None = None,
                   end_date: str | None = None) -> pd.DataFrame:
        """Fetch a series from BIS.
        
        Args:
            series_id: BIS series key (e.g., 'Q:US:P:A:M:XDC:A' for US private credit)
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            
        Returns:
            DataFrame with date, value, source, series_id columns
        """
        # Default to credit dataflow
        dataflow = self.DATAFLOWS["credit"]
        
        url = f"{self.BASE_URL}/data/{dataflow}/{series_id}"
        
        params = {}
        if start_date:
            params["startPeriod"] = start_date[:7]  # YYYY-MM format
        if end_date:
            params["endPeriod"] = end_date[:7]
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            df = self._parse_sdmx_json(data)
            
            return self._standardize_output(df, series_id)
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch BIS series {series_id}: {e}")
    
    def _parse_sdmx_json(self, data: dict) -> pd.DataFrame:
        """Parse SDMX JSON response into DataFrame."""
        try:
            # Navigate SDMX JSON structure
            datasets = data.get("dataSets", [])
            if not datasets:
                return pd.DataFrame(columns=["date", "value"])
            
            observations = datasets[0].get("series", {})
            if not observations:
                return pd.DataFrame(columns=["date", "value"])
            
            # Get time dimension
            structure = data.get("structure", {})
            dimensions = structure.get("dimensions", {})
            observation_dims = dimensions.get("observation", [])
            
            time_dim = None
            for dim in observation_dims:
                if dim.get("id") == "TIME_PERIOD":
                    time_dim = dim.get("values", [])
                    break
            
            if not time_dim:
                return pd.DataFrame(columns=["date", "value"])
            
            # Extract observations
            records = []
            for series_key, series_data in observations.items():
                obs = series_data.get("observations", {})
                for time_idx, values in obs.items():
                    time_idx = int(time_idx)
                    if time_idx < len(time_dim):
                        period = time_dim[time_idx].get("id", "")
                        value = values[0] if values else None
                        if value is not None:
                            records.append({
                                "date": self._parse_period(period),
                                "value": float(value)
                            })
            
            return pd.DataFrame(records)
            
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Failed to parse BIS SDMX response: {e}")
    
    def _parse_period(self, period: str) -> pd.Timestamp:
        """Convert BIS period string to timestamp."""
        # Handle quarterly format (e.g., '2023-Q1')
        if "-Q" in period:
            year, quarter = period.split("-Q")
            month = (int(quarter) - 1) * 3 + 1
            return pd.Timestamp(f"{year}-{month:02d}-01")
        # Handle monthly format (e.g., '2023-01')
        elif len(period) == 7:
            return pd.Timestamp(f"{period}-01")
        # Handle annual format (e.g., '2023')
        elif len(period) == 4:
            return pd.Timestamp(f"{period}-01-01")
        else:
            return pd.Timestamp(period)
    
    def get_credit_to_gdp(self, country: str, start_date: str | None = None,
                          end_date: str | None = None) -> pd.DataFrame:
        """Get credit-to-GDP ratio for a country.
        
        Args:
            country: ISO 2-letter country code (e.g., 'US', 'CN', 'JP')
        """
        # Credit to GDP ratio key format
        series_id = f"Q:{country}:P:A:M:770:A"
        return self.get_series(series_id, start_date, end_date)
    
    def get_private_credit(self, country: str, start_date: str | None = None,
                           end_date: str | None = None) -> pd.DataFrame:
        """Get total credit to private non-financial sector.
        
        Args:
            country: ISO 2-letter country code
        """
        series_id = f"Q:{country}:P:A:M:XDC:A"
        return self.get_series(series_id, start_date, end_date)


def get_bis_credit(country: str, start_date: str | None = None,
                   end_date: str | None = None) -> pd.DataFrame:
    """Quick helper to fetch BIS credit data."""
    client = BISClient()
    return client.get_private_credit(country, start_date, end_date)

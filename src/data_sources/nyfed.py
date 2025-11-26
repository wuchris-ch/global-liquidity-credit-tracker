"""New York Fed Markets Data API client."""
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime, timedelta
from .base import BaseClient


class NYFedClient(BaseClient):
    """Client for fetching data from NY Fed Markets Data APIs.
    
    Provides SOFR, repo operations, SOMA holdings, and other market data.
    API docs: https://markets.newyorkfed.org/static/docs/markets-api.html
    """
    
    source_name = "nyfed"
    BASE_URL = "https://markets.newyorkfed.org/api"
    
    def __init__(self, cache_path: Path | None = None):
        super().__init__(cache_path)
        self.session = requests.Session()
    
    def get_series(self, series_id: str, start_date: str | None = None,
                   end_date: str | None = None) -> pd.DataFrame:
        """Fetch a series from NY Fed.
        
        Args:
            series_id: One of 'sofr', 'repo', 'rrp', 'soma'
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
        """
        series_map = {
            "sofr": self.get_sofr,
            "repo": self.get_repo_operations,
            "rrp": self.get_reverse_repo,
            "soma": self.get_soma_holdings,
        }
        
        if series_id.lower() not in series_map:
            raise ValueError(f"Unknown series: {series_id}. Available: {list(series_map.keys())}")
        
        return series_map[series_id.lower()](start_date, end_date)
    
    def get_sofr(self, start_date: str | None = None,
                 end_date: str | None = None) -> pd.DataFrame:
        """Get Secured Overnight Financing Rate (SOFR) data."""
        url = f"{self.BASE_URL}/rates/secured/sofr/last/365.json"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            records = []
            for item in data.get("refRates", []):
                records.append({
                    "date": pd.Timestamp(item["effectiveDate"]),
                    "value": float(item["percentRate"]),
                })
            
            df = pd.DataFrame(records)
            df = self._filter_dates(df, start_date, end_date)
            
            return self._standardize_output(df, "SOFR")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch SOFR data: {e}")
    
    def get_repo_operations(self, start_date: str | None = None,
                            end_date: str | None = None) -> pd.DataFrame:
        """Get repo operation data."""
        # Default to last 30 days
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/rp/results/all/search.json"
        params = {
            "startDate": start_date,
            "endDate": end_date,
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            records = []
            for item in data.get("repo", {}).get("operations", []):
                records.append({
                    "date": pd.Timestamp(item.get("operationDate", item.get("settlementDate"))),
                    "value": float(item.get("totalAmtAccepted", 0)),
                    "operation_type": item.get("operationType", ""),
                })
            
            df = pd.DataFrame(records)
            if df.empty:
                df = pd.DataFrame(columns=["date", "value"])
            
            return self._standardize_output(df, "REPO_OPS")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch repo operations: {e}")
    
    def get_reverse_repo(self, start_date: str | None = None,
                         end_date: str | None = None) -> pd.DataFrame:
        """Get overnight reverse repo (ON RRP) data."""
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/rp/reverserepo/propositions/search.json"
        params = {
            "startDate": start_date,
            "endDate": end_date,
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            records = []
            for item in data.get("repo", {}).get("operations", []):
                records.append({
                    "date": pd.Timestamp(item.get("operationDate")),
                    "value": float(item.get("totalAmtAccepted", 0)),
                })
            
            df = pd.DataFrame(records)
            if df.empty:
                df = pd.DataFrame(columns=["date", "value"])
            
            return self._standardize_output(df, "RRP")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch reverse repo data: {e}")
    
    def get_soma_holdings(self, start_date: str | None = None,
                          end_date: str | None = None) -> pd.DataFrame:
        """Get System Open Market Account (SOMA) holdings."""
        url = f"{self.BASE_URL}/soma/summary.json"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            records = []
            for item in data.get("soma", {}).get("summary", []):
                records.append({
                    "date": pd.Timestamp(item.get("asOfDate")),
                    "value": float(item.get("total", 0)),
                })
            
            df = pd.DataFrame(records)
            df = self._filter_dates(df, start_date, end_date)
            
            return self._standardize_output(df, "SOMA")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch SOMA holdings: {e}")
    
    def _filter_dates(self, df: pd.DataFrame, start_date: str | None,
                      end_date: str | None) -> pd.DataFrame:
        """Filter DataFrame by date range."""
        if df.empty:
            return df
        
        if start_date:
            df = df[df["date"] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df["date"] <= pd.Timestamp(end_date)]
        
        return df


def get_nyfed_sofr() -> pd.DataFrame:
    """Quick helper to fetch SOFR data."""
    client = NYFedClient()
    return client.get_sofr()

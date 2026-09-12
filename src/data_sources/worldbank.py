"""World Bank Indicators API client."""
import pandas as pd
import requests
from pathlib import Path
from datetime import date
from .base import BaseClient


class WorldBankClient(BaseClient):
    """Client for fetching data from World Bank Indicators API.
    
    API docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
    """
    
    source_name = "worldbank"
    BASE_URL = "https://api.worldbank.org/v2"
    
    # Common indicators
    INDICATORS = {
        "credit_gdp": "FS.AST.PRVT.GD.ZS",      # Domestic credit to private sector (% GDP)
        "gdp_current": "NY.GDP.MKTP.CD",         # GDP (current US$)
        "gdp_growth": "NY.GDP.MKTP.KD.ZG",       # GDP growth (annual %)
        "broad_money_gdp": "FM.LBL.BMNY.GD.ZS",  # Broad money (% of GDP)
        "bank_credit": "FD.AST.PRVT.GD.ZS",      # Bank credit to private sector (% GDP)
    }
    
    # Country code mappings
    COUNTRY_CODES = {
        "US": "USA",
        "EU": "EMU",  # Euro area
        "CN": "CHN",
        "JP": "JPN",
        "GB": "GBR",
        "DE": "DEU",
        "FR": "FRA",
        "IN": "IND",
        "BR": "BRA",
        "CA": "CAN",
        "AU": "AUS",
        "KR": "KOR",
    }
    
    def __init__(self, cache_path: Path | None = None) -> None:
        super().__init__(cache_path)
        self.session = requests.Session()
    
    def get_series(self, series_id: str, start_date: str | None = None,
                   end_date: str | None = None, country: str = "all") -> pd.DataFrame:
        """Fetch an indicator from World Bank.
        
        Args:
            series_id: World Bank indicator code (e.g., 'FS.AST.PRVT.GD.ZS')
            start_date: Start year (e.g., '2000')
            end_date: End year (e.g., '2023')
            country: Country code or 'all'
            
        Returns:
            DataFrame with date, value, country, source, series_id columns
        """
        # Map common country codes
        wb_country = self.COUNTRY_CODES.get(country, country)
        
        url = f"{self.BASE_URL}/country/{wb_country}/indicator/{series_id}"
        
        params = {
            "format": "json",
            "per_page": 1000,
        }
        
        if start_date or end_date:
            params['date'] = f"{start_date[:4] if start_date else '1960'}:{end_date[:4] if end_date else date.today().year}"
        
        try:
            pages, page, total, updated = [], 1, None, None
            while True:
                response = self.session.get(url, params={**params, 'page':page}, timeout=30)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data,list) or len(data)!=2:
                    raise ValueError('Invalid World Bank response')
                meta, items = data
                if total is None:
                    total, updated = int(meta['total']), meta.get('lastupdated')
                if int(meta['total'])!=total or meta.get('lastupdated')!=updated or int(meta['pages'])>1000:
                    raise ValueError('Unstable or excessive World Bank pagination')
                pages.extend(items or [])
                if page>=int(meta['pages']): break
                page+=1
            if len(pages)!=total:
                raise ValueError('Incomplete World Bank response')
            df=self._parse_response([{},pages])
            result=self._standardize_output(df,series_id)
            result['country']=df['country'] if 'country' in df else country
            return result

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch World Bank indicator {series_id}: {e}")
    
    def _parse_response(self, data: list) -> pd.DataFrame:
        """Parse World Bank API response."""
        if not data or len(data) < 2:
            return pd.DataFrame(columns=["date", "value"])
        
        # First element is metadata, second is data
        records = data[1]
        if not records:
            return pd.DataFrame(columns=["date", "value"])
        
        rows = []
        for record in records:
            if record.get("value") is not None:
                rows.append({
                    "date": pd.Timestamp(f"{record['date']}-12-31"),
                    "value": float(record["value"]),
                    "country": record.get("countryiso3code", record.get("country", {}).get("id", ""))
                })
        
        return pd.DataFrame(rows)
    
    def get_credit_to_gdp(self, country: str = "all", start_date: str | None = None,
                          end_date: str | None = None) -> pd.DataFrame:
        """Get domestic credit to private sector as % of GDP."""
        return self.get_series(
            self.INDICATORS["credit_gdp"],
            start_date, end_date, country
        )
    
    def get_gdp(self, country: str = "all", start_date: str | None = None,
                end_date: str | None = None) -> pd.DataFrame:
        """Get GDP in current USD."""
        return self.get_series(
            self.INDICATORS["gdp_current"],
            start_date, end_date, country
        )
    
    def get_multiple_countries(self, indicator: str, countries: list[str],
                               start_date: str | None = None,
                               end_date: str | None = None) -> pd.DataFrame:
        """Fetch indicator for multiple countries."""
        dfs = []
        for country in countries:
            try:
                df = self.get_series(indicator, start_date, end_date, country)
                df["country"] = country
                dfs.append(df)
            except Exception as e:
                print(f"Warning: Failed to fetch {indicator} for {country}: {e}")
        
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()


def get_wb_credit_gdp(country: str = "all") -> pd.DataFrame:
    """Quick helper to fetch World Bank credit-to-GDP data."""
    client = WorldBankClient()
    return client.get_credit_to_gdp(country)

"""Data fetcher that orchestrates pulling data from all sources."""
import time

import pandas as pd
from typing import Literal

from ..config import get_series_config, get_all_series, RAW_DATA_PATH
from ..data_sources import FredClient, BISClient, WorldBankClient, NYFedClient, YFinanceClient
from ..data_sources.base import BaseClient


class SourceContractError(ValueError):
    """Raised when configured source identity metadata does not match."""


class DataFetcher:
    """Orchestrates data fetching from all configured sources."""

    def __init__(self, fred_api_key: str | None = None) -> None:
        self._clients: dict[str, BaseClient] = {}
        self._fred_api_key = fred_api_key
        self._source_metadata_cache: dict[tuple[str, str], dict] = {}

    def _get_client(self, source: str) -> BaseClient:
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
            elif source == "yfinance":
                self._clients[source] = YFinanceClient(cache_path=cache_path)
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
        self._validate_source_contract(series_id, config, client)

        # Handle source-specific fetching
        if source == "worldbank" and isinstance(client, WorldBankClient):
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

    def _validate_source_contract(
        self,
        series_id: str,
        config: dict,
        client: BaseClient,
    ) -> None:
        """Fail closed when a configured FRED series no longer matches its identity."""
        contract = config.get("source_contract")
        if contract is None:
            return
        if not isinstance(contract, dict) or not contract:
            raise SourceContractError(
                f"Series '{series_id}' has an invalid source_contract"
            )

        source = config.get("source")
        source_id = config.get("source_id")
        if source != "fred":
            raise SourceContractError(
                f"Series '{series_id}' declares a source_contract for unsupported "
                f"source '{source}'"
            )

        get_series_info = getattr(client, "get_series_info", None)
        if not callable(get_series_info):
            raise SourceContractError(
                f"FRED client cannot validate source_contract for '{series_id}'"
            )

        cache_key = (source, str(source_id))
        if cache_key not in self._source_metadata_cache:
            self._source_metadata_cache[cache_key] = get_series_info(source_id)
        metadata = self._source_metadata_cache[cache_key]
        if not isinstance(metadata, dict):
            raise SourceContractError(
                f"FRED returned invalid metadata for '{series_id}' ({source_id})"
            )

        mismatches = []
        for field, expected in contract.items():
            actual = metadata.get(field)
            expected_normalized = self._normalize_contract_value(expected)
            actual_normalized = self._normalize_contract_value(actual)
            if not expected_normalized or actual_normalized != expected_normalized:
                mismatches.append(
                    f"{field}: expected {expected!r}, received {actual!r}"
                )

        if mismatches:
            raise SourceContractError(
                f"FRED source_contract mismatch for '{series_id}' ({source_id}): "
                + "; ".join(mismatches)
            )

    @staticmethod
    def _normalize_contract_value(value: object) -> str:
        """Normalize source metadata without weakening exact semantic matching."""
        if value is None:
            return ""
        return " ".join(str(value).split()).casefold()
    
    def fetch_multiple(self, series_ids: list[str], start_date: str | None = None,
                       end_date: str | None = None,
                       retries: int = 2) -> dict[str, pd.DataFrame]:
        """Fetch multiple series.

        Failed fetches are retried with backoff; rate limits and transient
        network errors (Yahoo throttling, FRED hiccups) usually clear within
        seconds, and one missed asset otherwise drops it from the publish.

        Returns:
            Dict mapping series_id to DataFrame
        """
        results = {}
        errors = {}

        for series_id in series_ids:
            last_error: Exception | None = None
            for attempt in range(retries + 1):
                try:
                    results[series_id] = self.fetch_series(series_id, start_date, end_date)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if isinstance(e, SourceContractError):
                        break
                    if attempt < retries:
                        delay = 2 * (attempt + 1)
                        print(f"Warning: fetch {series_id} failed ({e}), retrying in {delay}s")
                        time.sleep(delay)
            if last_error is not None:
                errors[series_id] = str(last_error)
                print(f"Warning: Failed to fetch {series_id}: {last_error}")
        
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

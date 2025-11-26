"""Data source clients for fetching financial data."""
from .fred import FredClient
from .bis import BISClient
from .worldbank import WorldBankClient
from .nyfed import NYFedClient

__all__ = ["FredClient", "BISClient", "WorldBankClient", "NYFedClient"]

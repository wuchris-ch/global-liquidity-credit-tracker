"""Yahoo Finance client for asset price data."""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from .base import BaseClient


class YFinanceClient(BaseClient):
    """Client for fetching price data from Yahoo Finance.

    Uses the yfinance library to fetch historical price data for stocks,
    ETFs, cryptocurrencies, and other assets available on Yahoo Finance.
    """

    source_name = "yfinance"

    def __init__(self, cache_path: Path | None = None):
        super().__init__(cache_path)
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError:
            raise ImportError(
                "yfinance package required. Install with: pip install yfinance"
            )

    def get_series(
        self,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> pd.DataFrame:
        """Fetch price series from Yahoo Finance.

        Args:
            ticker: Yahoo Finance ticker symbol (e.g., 'SPY', 'BTC-USD', 'IWM')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format

        Returns:
            DataFrame with date, value (adjusted close), source, series_id columns
        """
        # Default to 10 years of history if no start date
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        try:
            ticker_obj = self._yf.Ticker(ticker)
            hist = ticker_obj.history(
                start=start_date,
                end=end_date,
                auto_adjust=True  # Use adjusted prices
            )

            if hist.empty:
                raise RuntimeError(f"No data returned for ticker {ticker}")

            # Reset index to get date as column
            hist = hist.reset_index()

            df = pd.DataFrame({
                "date": hist["Date"],
                "value": hist["Close"].values
            })

            # Drop NaN values
            df = df.dropna(subset=["value"])

            return self._standardize_output(df, ticker)

        except Exception as e:
            raise RuntimeError(f"Failed to fetch Yahoo Finance data for {ticker}: {e}")

    def get_multiple_series(
        self,
        tickers: list[str],
        start_date: str | None = None,
        end_date: str | None = None
    ) -> dict[str, pd.DataFrame]:
        """Fetch multiple price series efficiently.

        Args:
            tickers: List of Yahoo Finance ticker symbols
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format

        Returns:
            Dictionary mapping ticker to DataFrame
        """
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.get_series(ticker, start_date, end_date)
            except Exception as e:
                print(f"Warning: Could not fetch {ticker}: {e}")
        return results

    def get_ticker_info(self, ticker: str) -> dict:
        """Get metadata about a ticker.

        Args:
            ticker: Yahoo Finance ticker symbol

        Returns:
            Dictionary with ticker information
        """
        try:
            ticker_obj = self._yf.Ticker(ticker)
            return ticker_obj.info
        except Exception as e:
            raise RuntimeError(f"Failed to get info for ticker {ticker}: {e}")


# Convenience function for quick access
def get_yfinance_series(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None
) -> pd.DataFrame:
    """Quick helper to fetch a Yahoo Finance series."""
    client = YFinanceClient()
    return client.get_series(ticker, start_date, end_date)

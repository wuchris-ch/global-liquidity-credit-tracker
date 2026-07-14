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

    def __init__(self, cache_path: Path | None = None) -> None:
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

    def get_adjusted_histories(
        self,
        tickers: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch adjusted closes for multiple tickers in one upstream request.

        This is used by the sector-rotation cross-section so every sector is
        sampled from the same download. The returned frames use the tracker's
        standard ``date``/``value`` shape and retain volume for diagnostics.
        """
        normalized = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers))
        if not normalized:
            return {}
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365 * 6)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        try:
            downloaded = self._yf.download(
                tickers=normalized,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch Yahoo Finance market histories: {exc}") from exc

        results: dict[str, pd.DataFrame] = {}
        for ticker in normalized:
            try:
                if isinstance(downloaded.columns, pd.MultiIndex):
                    level_zero = downloaded.columns.get_level_values(0)
                    level_one = downloaded.columns.get_level_values(1)
                    if ticker in level_zero:
                        history = downloaded[ticker].copy()
                    elif ticker in level_one:
                        history = downloaded.xs(ticker, axis=1, level=1).copy()
                    else:
                        continue
                else:
                    if len(normalized) != 1:
                        continue
                    history = downloaded.copy()

                if "Close" not in history or history["Close"].dropna().empty:
                    continue
                dates = pd.to_datetime(history.index)
                if getattr(dates, "tz", None) is not None:
                    dates = dates.tz_localize(None)
                frame = pd.DataFrame(
                    {
                        "date": dates,
                        "value": pd.to_numeric(history["Close"], errors="coerce").values,
                        "volume": pd.to_numeric(
                            history.get("Volume", pd.Series(index=history.index, dtype=float)),
                            errors="coerce",
                        ).values,
                    }
                ).dropna(subset=["value"])
                if not frame.empty:
                    results[ticker] = self._standardize_output(frame, ticker).merge(
                        frame[["date", "volume"]], on="date", how="left"
                    )
            except (KeyError, TypeError, ValueError):
                continue
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

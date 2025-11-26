"""Time series transformation utilities."""
import pandas as pd
import numpy as np
from typing import Literal


def resample_to_frequency(
    df: pd.DataFrame,
    target_freq: Literal["D", "W", "M", "Q", "A"],
    agg_method: Literal["last", "mean", "sum", "first"] = "last",
    value_col: str = "value",
    date_col: str = "date"
) -> pd.DataFrame:
    """Resample time series to target frequency.
    
    Args:
        df: DataFrame with date and value columns
        target_freq: Target frequency (D=daily, W=weekly, M=monthly, Q=quarterly, A=annual)
        agg_method: Aggregation method for resampling
        value_col: Name of value column
        date_col: Name of date column
        
    Returns:
        Resampled DataFrame
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    
    # Map frequency codes
    freq_map = {"D": "D", "W": "W-FRI", "M": "ME", "Q": "QE", "A": "YE"}
    pandas_freq = freq_map.get(target_freq, target_freq)
    
    # Resample
    if agg_method == "last":
        resampled = df[value_col].resample(pandas_freq).last()
    elif agg_method == "mean":
        resampled = df[value_col].resample(pandas_freq).mean()
    elif agg_method == "sum":
        resampled = df[value_col].resample(pandas_freq).sum()
    elif agg_method == "first":
        resampled = df[value_col].resample(pandas_freq).first()
    else:
        raise ValueError(f"Unknown aggregation method: {agg_method}")
    
    result = resampled.reset_index()
    result.columns = [date_col, value_col]
    
    return result.dropna()


def compute_yoy_change(
    df: pd.DataFrame,
    value_col: str = "value",
    date_col: str = "date",
    periods: int | None = None
) -> pd.DataFrame:
    """Compute year-over-year percentage change.
    
    Args:
        df: DataFrame with date and value columns
        value_col: Name of value column
        date_col: Name of date column
        periods: Number of periods to look back (auto-detected if None)
        
    Returns:
        DataFrame with yoy_change column added
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    
    # Auto-detect periods based on frequency
    if periods is None:
        if len(df) > 1:
            avg_days = (df[date_col].diff().mean()).days
            if avg_days <= 7:
                periods = 252  # Daily -> ~1 year of trading days
            elif avg_days <= 14:
                periods = 52   # Weekly
            elif avg_days <= 45:
                periods = 12   # Monthly
            elif avg_days <= 100:
                periods = 4    # Quarterly
            else:
                periods = 1    # Annual
        else:
            periods = 1
    
    df["yoy_change"] = df[value_col].pct_change(periods=periods) * 100
    
    return df


def compute_zscore(
    df: pd.DataFrame,
    value_col: str = "value",
    window: int | None = None,
    min_periods: int = 20
) -> pd.DataFrame:
    """Compute z-score (standardized value).
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        window: Rolling window size (None for expanding window)
        min_periods: Minimum periods for calculation
        
    Returns:
        DataFrame with zscore column added
    """
    df = df.copy()
    
    if window:
        rolling_mean = df[value_col].rolling(window=window, min_periods=min_periods).mean()
        rolling_std = df[value_col].rolling(window=window, min_periods=min_periods).std()
    else:
        rolling_mean = df[value_col].expanding(min_periods=min_periods).mean()
        rolling_std = df[value_col].expanding(min_periods=min_periods).std()
    
    df["zscore"] = (df[value_col] - rolling_mean) / rolling_std
    
    return df


def normalize_to_usd(
    df: pd.DataFrame,
    fx_rate: float | pd.Series,
    value_col: str = "value"
) -> pd.DataFrame:
    """Normalize values to USD using exchange rate.
    
    Args:
        df: DataFrame with value column
        fx_rate: Exchange rate (local currency per USD) or Series aligned with df
        value_col: Name of value column
        
    Returns:
        DataFrame with value_usd column added
    """
    df = df.copy()
    
    if isinstance(fx_rate, (int, float)):
        df["value_usd"] = df[value_col] / fx_rate
    else:
        df["value_usd"] = df[value_col] / fx_rate.values
    
    return df


def align_series(
    series_dict: dict[str, pd.DataFrame],
    date_col: str = "date",
    value_col: str = "value",
    method: Literal["inner", "outer"] = "outer",
    fill_method: Literal["ffill", "bfill", None] = "ffill"
) -> pd.DataFrame:
    """Align multiple series to common dates.
    
    Args:
        series_dict: Dict mapping series names to DataFrames
        date_col: Name of date column
        value_col: Name of value column
        method: Join method ('inner' or 'outer')
        fill_method: Method to fill missing values
        
    Returns:
        DataFrame with series as columns, dates as index
    """
    aligned = pd.DataFrame()
    
    for name, df in series_dict.items():
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)[[value_col]]
        df.columns = [name]
        
        if aligned.empty:
            aligned = df
        else:
            aligned = aligned.join(df, how=method)
    
    if fill_method == "ffill":
        aligned = aligned.ffill()
    elif fill_method == "bfill":
        aligned = aligned.bfill()
    
    return aligned.reset_index()


def compute_rolling_correlation(
    df: pd.DataFrame,
    col1: str,
    col2: str,
    window: int = 60
) -> pd.Series:
    """Compute rolling correlation between two columns."""
    return df[col1].rolling(window=window).corr(df[col2])


def detect_regime(
    df: pd.DataFrame,
    value_col: str = "value",
    thresholds: tuple[float, float] = (-1.0, 1.0)
) -> pd.DataFrame:
    """Detect regime based on z-score thresholds.
    
    Args:
        df: DataFrame with zscore column
        value_col: Value column to compute zscore if not present
        thresholds: (low, high) z-score thresholds
        
    Returns:
        DataFrame with regime column (-1=tight, 0=neutral, 1=loose)
    """
    df = df.copy()
    
    if "zscore" not in df.columns:
        df = compute_zscore(df, value_col)
    
    low, high = thresholds
    df["regime"] = 0
    df.loc[df["zscore"] < low, "regime"] = -1
    df.loc[df["zscore"] > high, "regime"] = 1
    
    return df

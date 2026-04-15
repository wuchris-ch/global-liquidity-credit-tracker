"""Time series transformation utilities."""
import pandas as pd
import numpy as np
from typing import Literal


def _as_series(obj) -> pd.Series:
    """Coerce a DataFrame's first column to a Series; pass Series through.

    Several pandas operations can return either a Series or a single-column
    DataFrame depending on how the input was indexed. This helper normalizes
    the result so downstream arithmetic/assignment works uniformly.
    """
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def _assign_col(df: pd.DataFrame, col: str, values) -> None:
    """Assign a computed series to a DataFrame column, unwrapping DataFrames.

    Mirrors the common pattern ``df[col] = values.values if hasattr(values, 'values') else values``
    that previously appeared after many transform computations.
    """
    values = _as_series(values)
    df[col] = values.values if hasattr(values, "values") else values


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

    values = _as_series(df[value_col])

    if window:
        rolling_mean = values.rolling(window=window, min_periods=min_periods).mean()
        rolling_std = values.rolling(window=window, min_periods=min_periods).std()
    else:
        rolling_mean = values.expanding(min_periods=min_periods).mean()
        rolling_std = values.expanding(min_periods=min_periods).std()

    _assign_col(df, "zscore", (values - rolling_mean) / rolling_std)
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


def compute_growth_rate(
    df: pd.DataFrame,
    value_col: str = "value",
    periods: int = 52,
    annualize: bool = True,
    method: Literal["pct", "log"] = "pct"
) -> pd.DataFrame:
    """Compute annualized growth rate.
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        periods: Lookback periods
        annualize: Whether to annualize the growth rate
        method: 'pct' for percentage change, 'log' for log returns
        
    Returns:
        DataFrame with growth_rate column added
    """
    df = df.copy()

    values = _as_series(df[value_col])

    if method == "log":
        # Log returns for more stable estimation
        growth = np.log(values / values.shift(periods))
    else:
        growth = values.pct_change(periods=periods)

    growth = _as_series(growth) * 100
    df["growth_rate"] = growth.values if hasattr(growth, "values") else growth

    return df


def compute_rolling_gap(
    df: pd.DataFrame,
    value_col: str = "value",
    window: int = 104,
    min_periods: int = 52
) -> pd.DataFrame:
    """Compute deviation from rolling mean (gap/trend).
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        window: Rolling window size (default 2 years for weekly)
        min_periods: Minimum periods for calculation
        
    Returns:
        DataFrame with gap column (deviation from trend)
    """
    df = df.copy()

    values = _as_series(df[value_col])
    rolling_mean = _as_series(values.rolling(window=window, min_periods=min_periods).mean())

    _assign_col(df, "gap", values - rolling_mean)
    _assign_col(df, "gap_pct", (values / rolling_mean - 1) * 100)

    return df


def create_missing_mask(
    df: pd.DataFrame,
    value_cols: list[str] | None = None
) -> pd.DataFrame:
    """Create boolean mask for missing values (for state-space models).
    
    Args:
        df: DataFrame with value columns
        value_cols: Columns to check (all numeric if None)
        
    Returns:
        DataFrame with boolean mask (True = observed, False = missing)
    """
    if value_cols is None:
        value_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    mask = ~df[value_cols].isna()
    return mask


def forward_fill_with_limit(
    df: pd.DataFrame,
    value_col: str = "value",
    limit: int = 4
) -> pd.DataFrame:
    """Forward fill with a limit on consecutive fills.
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        limit: Maximum consecutive fills
        
    Returns:
        DataFrame with forward-filled values
    """
    df = df.copy()
    df[value_col] = df[value_col].ffill(limit=limit)
    return df


def compute_credit_impulse(
    df: pd.DataFrame,
    value_col: str = "value",
    periods: int = 4,
    as_change_of_flow: bool = True
) -> pd.DataFrame:
    """Compute credit impulse (change in the flow of credit).
    
    The credit impulse is the second derivative of credit - it measures
    how the RATE of credit growth is changing, not just the level.
    This is more predictive of economic activity than credit levels.
    
    Credit Impulse = Δ(Credit Growth) = Δ(ΔCredit/GDP)
    
    Args:
        df: DataFrame with credit or credit/GDP ratio values
        value_col: Name of value column
        periods: Differencing periods (4 for quarterly data, 12 for monthly)
        as_change_of_flow: If True, computes second derivative (impulse)
                          If False, computes first derivative (flow)
        
    Returns:
        DataFrame with credit_impulse and credit_flow columns
    """
    df = df.copy()

    values = _as_series(df[value_col])

    # First derivative: credit flow (change in credit)
    credit_flow = _as_series(values.diff(periods=periods))
    _assign_col(df, "credit_flow", credit_flow)

    if as_change_of_flow:
        # Second derivative: credit impulse (change in credit flow)
        _assign_col(df, "credit_impulse", credit_flow.diff(periods=periods))
    else:
        df["credit_impulse"] = df["credit_flow"]

    return df


def compute_hp_filter_gap(
    df: pd.DataFrame,
    value_col: str = "value",
    lamb: float = 1600
) -> pd.DataFrame:
    """Compute HP filter gap (deviation from smooth trend).
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        lamb: Smoothing parameter (1600 for quarterly, 6.25 for annual)
        
    Returns:
        DataFrame with hp_trend and hp_gap columns
    """
    df = df.copy()
    values = df[value_col].dropna()
    
    if len(values) < 10:
        df["hp_trend"] = np.nan
        df["hp_gap"] = np.nan
        return df
    
    try:
        from statsmodels.tsa.filters.hp_filter import hpfilter
        cycle, trend = hpfilter(values, lamb=lamb)
        
        # Align back to original index
        df["hp_trend"] = np.nan
        df["hp_gap"] = np.nan
        df.loc[values.index, "hp_trend"] = trend.values
        df.loc[values.index, "hp_gap"] = cycle.values
    except ImportError:
        # Fallback to rolling mean if statsmodels not available
        window = int(np.sqrt(lamb))
        df["hp_trend"] = df[value_col].rolling(window=window, min_periods=window//2).mean()
        df["hp_gap"] = df[value_col] - df["hp_trend"]
    
    return df


def standardize_series(
    df: pd.DataFrame,
    value_col: str = "value",
    method: Literal["zscore", "minmax", "robust"] = "zscore",
    window: int | None = None
) -> pd.DataFrame:
    """Standardize a series using various methods.
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        method: Standardization method
        window: Rolling window (None for expanding)
        
    Returns:
        DataFrame with standardized column
    """
    df = df.copy()

    if value_col not in df.columns:
        raise ValueError(f"Column '{value_col}' not found in DataFrame")

    values = _as_series(df[value_col].copy())

    if method == "zscore":
        if window:
            mean = values.rolling(window=window, min_periods=20).mean()
            std = values.rolling(window=window, min_periods=20).std()
        else:
            mean = values.expanding(min_periods=20).mean()
            std = values.expanding(min_periods=20).std()
        standardized = (values - mean) / std

    elif method == "minmax":
        if window:
            min_val = values.rolling(window=window, min_periods=20).min()
            max_val = values.rolling(window=window, min_periods=20).max()
        else:
            min_val = values.expanding(min_periods=20).min()
            max_val = values.expanding(min_periods=20).max()
        standardized = (values - min_val) / (max_val - min_val)

    elif method == "robust":
        # Use median and IQR for robustness to outliers
        if window:
            median = values.rolling(window=window, min_periods=20).median()
            q75 = values.rolling(window=window, min_periods=20).quantile(0.75)
            q25 = values.rolling(window=window, min_periods=20).quantile(0.25)
        else:
            median = values.expanding(min_periods=20).median()
            q75 = values.expanding(min_periods=20).quantile(0.75)
            q25 = values.expanding(min_periods=20).quantile(0.25)
        iqr = q75 - q25
        standardized = (values - median) / iqr
    else:
        raise ValueError(f"Unknown standardization method: {method}")

    df["standardized"] = _as_series(standardized).values

    return df


def compute_momentum(
    df: pd.DataFrame,
    value_col: str = "value",
    short_window: int = 4,
    long_window: int = 12
) -> pd.DataFrame:
    """Compute momentum indicators.
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        short_window: Short-term moving average window
        long_window: Long-term moving average window
        
    Returns:
        DataFrame with momentum columns
    """
    df = df.copy()

    values = _as_series(df[value_col])

    # Simple momentum (rate of change)
    _assign_col(df, "momentum", values.diff(short_window))

    # MACD-style momentum
    short_ma = values.rolling(window=short_window).mean()
    long_ma = values.rolling(window=long_window).mean()
    _assign_col(df, "momentum_macd", short_ma - long_ma)

    # Rate of change
    _assign_col(df, "roc", values.pct_change(periods=short_window) * 100)

    return df


def compute_regime_probability(
    df: pd.DataFrame,
    value_col: str = "value",
    window: int = 52,
    transition_smoothing: int = 4
) -> pd.DataFrame:
    """Compute probability of regime change.
    
    Args:
        df: DataFrame with value column (should be zscore or similar)
        value_col: Name of value column
        window: Lookback window for regime statistics
        transition_smoothing: Smoothing for transition detection
        
    Returns:
        DataFrame with regime probability columns
    """
    df = df.copy()
    
    if "zscore" not in df.columns:
        df = compute_zscore(df, value_col, window=window)
    
    # Distance to regime boundaries
    df["dist_to_tight"] = df["zscore"] - (-1.0)  # Distance to tight threshold
    df["dist_to_loose"] = 1.0 - df["zscore"]     # Distance to loose threshold
    
    # Trend of zscore (momentum toward regime change)
    df["zscore_trend"] = df["zscore"].diff(transition_smoothing)
    
    # Smoothed probability based on distance and trend
    # Higher probability when closer to threshold and moving toward it
    df["prob_regime_change"] = np.where(
        df["zscore_trend"] < 0,  # Moving toward tight
        np.maximum(0, 1 - df["dist_to_tight"].abs()),
        np.maximum(0, 1 - df["dist_to_loose"].abs())
    )
    
    return df


def apply_sign_flip(
    df: pd.DataFrame,
    value_col: str = "value",
    expected_sign: int = 1
) -> pd.DataFrame:
    """Flip series sign to ensure expected directional relationship.
    
    This should be applied BEFORE factor extraction to ensure
    loadings have interpretable signs.
    
    Args:
        df: DataFrame with value column
        value_col: Name of value column
        expected_sign: 1 for positive relationship, -1 for negative
        
    Returns:
        DataFrame with potentially sign-flipped values
    """
    df = df.copy()
    if expected_sign < 0:
        df[value_col] = -df[value_col]
    return df


def detect_frequency(df: pd.DataFrame, date_col: str = "date") -> str:
    """Detect the frequency of a time series.
    
    Returns:
        Frequency code: 'D', 'W', 'M', 'Q', or 'A'
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    
    if len(df) < 2:
        return "M"  # Default to monthly
    
    avg_days = df[date_col].diff().mean().days
    
    if avg_days <= 2:
        return "D"
    elif avg_days <= 10:
        return "W"
    elif avg_days <= 45:
        return "M"
    elif avg_days <= 120:
        return "Q"
    else:
        return "A"


def get_frequency_periods(freq: str) -> dict:
    """Get standard lookback periods for a frequency.
    
    Returns dict with keys: year, half_year, quarter
    """
    periods = {
        "D": {"year": 252, "half_year": 126, "quarter": 63},
        "W": {"year": 52, "half_year": 26, "quarter": 13},
        "M": {"year": 12, "half_year": 6, "quarter": 3},
        "Q": {"year": 4, "half_year": 2, "quarter": 1},
        "A": {"year": 1, "half_year": 1, "quarter": 1},
    }
    return periods.get(freq, periods["M"])

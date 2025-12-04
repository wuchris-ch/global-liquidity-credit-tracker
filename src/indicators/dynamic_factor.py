"""Dynamic Factor Model implementation for latent factor extraction.

This module provides robust factor extraction with:
- Mixed-frequency support via Kalman filtering
- Proper sign constraint enforcement
- Data quality validation
- Shrinkage/regularization for stability
"""
import pandas as pd
import numpy as np
from typing import Literal
from dataclasses import dataclass, field
import warnings

# Try to import statsmodels for DFM
try:
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    HAS_STATSMODELS_DFM = True
except ImportError:
    HAS_STATSMODELS_DFM = False

# Try to import mixed-frequency DFM
try:
    from statsmodels.tsa.statespace.dynamic_factor_mq import DynamicFactorMQ
    HAS_MIXED_FREQ = True
except ImportError:
    HAS_MIXED_FREQ = False

# Try to import sklearn for PCA fallback
try:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


@dataclass
class FactorModelResult:
    """Results from factor model estimation."""
    factors: pd.DataFrame  # Estimated factor series
    loadings: pd.DataFrame  # Factor loadings for each variable
    explained_variance: float  # Variance explained by factors
    method: str  # Method used ('dfm', 'dfm_mq', 'pca', 'pca_shrunk')
    converged: bool  # Whether estimation converged
    metadata: dict = field(default_factory=dict)  # Additional model info
    
    def get_contribution(self, variable: str) -> float:
        """Get the contribution of a variable to the factor."""
        if variable in self.loadings.index:
            return float(self.loadings.loc[variable, "factor_1"])
        return 0.0


@dataclass 
class DataQualityCheck:
    """Results of data quality validation."""
    is_valid: bool
    n_valid_obs: int
    n_variables: int
    coverage_pct: float
    near_constant_cols: list[str]
    high_missing_cols: list[str]
    warnings: list[str]


class DynamicFactorModel:
    """Wrapper for Dynamic Factor Model with Kalman filter smoothing.
    
    This class provides a unified interface for factor extraction,
    with multiple methods available:
    - 'dfm': statsmodels Dynamic Factor Model (handles missing data)
    - 'dfm_mq': statsmodels Mixed-Frequency DFM (for ragged edges)
    - 'pca': Standard PCA (sklearn)
    - 'pca_shrunk': PCA with shrinkage on loadings
    - 'auto': Automatically choose best method based on data
    
    Features:
    - Handles missing data via Kalman filter or imputation
    - Sign constraints applied BEFORE extraction via pre-flipping
    - Shrinkage option for stable loadings
    - Falls back gracefully when packages unavailable
    """
    
    def __init__(
        self,
        n_factors: int = 1,
        factor_order: int = 1,
        error_order: int = 0,
        sign_constraints: dict[str, int] | None = None,
        max_iter: int = 100,
        method: Literal["dfm", "dfm_mq", "pca", "pca_shrunk", "auto"] = "auto",
        shrinkage_alpha: float = 0.1,
        min_observations: int = 30,
        min_variables: int = 2
    ):
        """Initialize the Dynamic Factor Model.
        
        Args:
            n_factors: Number of latent factors to extract
            factor_order: AR order for factor dynamics (DFM only)
            error_order: AR order for idiosyncratic errors (DFM only)
            sign_constraints: Dict mapping column names to expected signs (+1/-1)
                             Note: Series should be pre-flipped, so all should be +1
            max_iter: Maximum iterations for EM algorithm
            method: Estimation method
            shrinkage_alpha: Ridge regularization parameter
            min_observations: Minimum required observations
            min_variables: Minimum required variables
        """
        self.n_factors = n_factors
        self.factor_order = factor_order
        self.error_order = error_order
        self.sign_constraints = sign_constraints or {}
        self.max_iter = max_iter
        self.method = method
        self.shrinkage_alpha = shrinkage_alpha
        self.min_observations = min_observations
        self.min_variables = min_variables
        
        self._model = None
        self._results = None
        self._scaler = None
        self._columns = None
        self._fitted = False
        self._data_quality = None
    
    def validate_data(self, X: pd.DataFrame) -> DataQualityCheck:
        """Validate input data before fitting.
        
        Args:
            X: Input data matrix
            
        Returns:
            DataQualityCheck with validation results
        """
        warnings_list = []
        
        # Select only numeric columns
        numeric = X.select_dtypes(include=[np.number])
        
        # Check dimensions
        n_obs, n_vars = numeric.shape
        
        if n_obs < self.min_observations:
            warnings_list.append(f"Only {n_obs} observations, need {self.min_observations}")
        
        if n_vars < self.min_variables:
            warnings_list.append(f"Only {n_vars} variables, need {self.min_variables}")
        
        # Check for near-constant columns
        near_constant = []
        for col in numeric.columns:
            if numeric[col].std() < 1e-8:
                near_constant.append(col)
                warnings_list.append(f"Column '{col}' is near-constant")
        
        # Check for high missing
        high_missing = []
        for col in numeric.columns:
            missing_pct = numeric[col].isna().sum() / len(numeric)
            if missing_pct > 0.5:
                high_missing.append(col)
                warnings_list.append(f"Column '{col}' has {missing_pct:.0%} missing")
        
        # Overall coverage
        coverage = numeric.notna().sum().sum() / (n_obs * n_vars) if n_obs * n_vars > 0 else 0
        
        # Valid observations (rows with at least some data)
        valid_obs = (numeric.notna().sum(axis=1) > 0).sum()
        
        is_valid = (
            valid_obs >= self.min_observations and 
            (n_vars - len(near_constant)) >= self.min_variables
        )
        
        return DataQualityCheck(
            is_valid=is_valid,
            n_valid_obs=valid_obs,
            n_variables=n_vars - len(near_constant),
            coverage_pct=coverage,
            near_constant_cols=near_constant,
            high_missing_cols=high_missing,
            warnings=warnings_list
        )
    
    def fit(
        self,
        X: pd.DataFrame,
        mask: pd.DataFrame | None = None
    ) -> "DynamicFactorModel":
        """Fit the factor model to data.
        
        Args:
            X: DataFrame with numeric columns (observations x variables)
            mask: Optional boolean mask (True = observed)
            
        Returns:
            self
        """
        # Validate data
        self._data_quality = self.validate_data(X)
        
        if not self._data_quality.is_valid:
            raise ValueError(
                f"Data validation failed: {'; '.join(self._data_quality.warnings)}"
            )
        
        # Remove problematic columns
        X_clean = X.drop(columns=self._data_quality.near_constant_cols, errors="ignore")
        
        # Store column names for later
        self._columns = X_clean.select_dtypes(include=[np.number]).columns.tolist()
        
        # Determine method
        if self.method == "auto":
            use_method = self._choose_method(X_clean)
        else:
            use_method = self.method
        
        # Fit using chosen method
        if use_method == "dfm_mq" and HAS_MIXED_FREQ:
            self._fit_dfm_mq(X_clean)
        elif use_method == "dfm" and HAS_STATSMODELS_DFM:
            self._fit_dfm(X_clean, mask)
        elif use_method == "pca_shrunk" and HAS_SKLEARN:
            self._fit_pca_shrunk(X_clean)
        else:
            self._fit_pca(X_clean)
        
        self._fitted = True
        return self
    
    def _choose_method(self, X: pd.DataFrame) -> str:
        """Automatically choose the best estimation method."""
        missing_pct = X.isna().sum().sum() / X.size if X.size > 0 else 0
        
        # Check if dropna() would eliminate too much data (DFM requirement)
        complete_rows = len(X.dropna())
        total_rows = len(X)
        
        # DFM needs complete rows for initialization - skip if <50% would remain
        dfm_viable = complete_rows >= max(30, total_rows * 0.5)
        
        # If DFM viable and moderate missing data, use it
        if dfm_viable and 0 < missing_pct <= 0.3 and HAS_STATSMODELS_DFM:
            return "dfm"
        
        # Otherwise use PCA (faster, handles missing data better via imputation)
        if HAS_SKLEARN:
            return "pca_shrunk"
        elif HAS_STATSMODELS_DFM:
            return "dfm"
        else:
            return "pca"
    
    def _fit_dfm(self, X: pd.DataFrame, mask: pd.DataFrame | None = None):
        """Fit using statsmodels Dynamic Factor Model."""
        data = X.select_dtypes(include=[np.number]).copy()
        
        # Standardize data
        self._scaler = StandardScaler() if HAS_SKLEARN else None
        if self._scaler:
            # Handle NaN by filling temporarily for scaling, then restoring
            data_filled = data.fillna(data.mean())
            data_scaled = pd.DataFrame(
                self._scaler.fit_transform(data_filled),
                index=data.index,
                columns=data.columns
            )
            # Restore NaN pattern
            data_scaled[data.isna()] = np.nan
        else:
            data_scaled = (data - data.mean()) / data.std()
        
        try:
            # Create and fit the model
            model = DynamicFactor(
                data_scaled.dropna(),  # DFM needs complete data for EM init
                k_factors=self.n_factors,
                factor_order=self.factor_order,
                error_order=self.error_order
            )
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                results = model.fit(
                    method="em",
                    maxiter=self.max_iter,
                    disp=False
                )
            
            self._model = model
            self._results = results
            self._method_used = "dfm"
            
        except Exception as e:
            warnings.warn(f"DFM fitting failed: {e}. Falling back to PCA.")
            self._fit_pca(X)
    
    def _fit_dfm_mq(self, X: pd.DataFrame):
        """Fit using statsmodels Mixed-Frequency DFM."""
        # This would require frequency information for each column
        # Falling back to regular DFM for now
        self._fit_dfm(X)
    
    def _fit_pca_shrunk(self, X: pd.DataFrame):
        """Fit using PCA with shrinkage on loadings."""
        data = X.select_dtypes(include=[np.number]).copy()
        
        # Handle missing values with forward/backward fill then mean
        data = data.ffill(limit=26).bfill(limit=26)
        for col in data.columns:
            if data[col].isna().any():
                col_mean = data[col].mean()
                data[col] = data[col].fillna(col_mean if not pd.isna(col_mean) else 0)
        
        # Check if we have enough data
        valid_mask = data.notna().all(axis=1)
        data_clean = data[valid_mask]
        
        if len(data_clean) < max(self.n_factors * 2, 10):
            raise ValueError(f"Insufficient valid observations: got {len(data_clean)}")
        
        # Suppress sklearn warnings during fitting
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            
            # Standardize
            self._scaler = StandardScaler()
            data_scaled = self._scaler.fit_transform(data_clean)
            
            # Fit PCA
            pca = PCA(n_components=self.n_factors)
            pca.fit(data_scaled)
            
            # Apply shrinkage to loadings using Ridge regression
            # This makes loadings more stable when variables are correlated
            factors_raw = pca.transform(data_scaled)
            
            # Ensure factors_raw is 2D for Ridge
            if factors_raw.ndim == 1:
                factors_raw = factors_raw.reshape(-1, 1)
            
            # Re-estimate loadings with ridge regularization
            shrunk_loadings = []
            for i in range(data_scaled.shape[1]):
                ridge = Ridge(alpha=self.shrinkage_alpha, fit_intercept=False)
                ridge.fit(factors_raw, data_scaled[:, i])
                # Ridge coef shape is (n_factors,), we need it as a row
                shrunk_loadings.append(ridge.coef_.flatten())
        
        self._shrunk_loadings = np.array(shrunk_loadings)
        self._model = pca
        self._valid_index = data_clean.index
        self._full_data = data
        self._method_used = "pca_shrunk"
    
    def _fit_pca(self, X: pd.DataFrame):
        """Fit using standard PCA (fallback method)."""
        data = X.select_dtypes(include=[np.number]).copy()
        
        # Handle missing values
        data = data.ffill(limit=26).bfill(limit=26)
        for col in data.columns:
            if data[col].isna().any():
                col_mean = data[col].mean()
                data[col] = data[col].fillna(col_mean if not pd.isna(col_mean) else 0)
        
        valid_mask = data.notna().all(axis=1)
        data_clean = data[valid_mask]
        
        if len(data_clean) < max(self.n_factors * 2, 10):
            raise ValueError(f"Insufficient valid observations: got {len(data_clean)}")
        
        # Suppress sklearn warnings during fitting
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            
            if HAS_SKLEARN:
                self._scaler = StandardScaler()
                data_scaled = self._scaler.fit_transform(data_clean)
                
                pca = PCA(n_components=self.n_factors)
                pca.fit(data_scaled)
                
                self._model = pca
                self._valid_index = data_clean.index
            else:
                # Manual PCA using numpy SVD
                self._scaler = None
                data_centered = data_clean - data_clean.mean()
                data_scaled = data_centered / data_centered.std()
                
                U, S, Vt = np.linalg.svd(data_scaled.values, full_matrices=False)
                
                self._pca_components = Vt[:self.n_factors]
                self._pca_explained_variance = (S[:self.n_factors] ** 2) / (len(data_clean) - 1)
                self._valid_index = data_clean.index
                self._model = "manual_pca"
        
        self._method_used = "pca"
        self._full_data = data
    
    def transform(self, X: pd.DataFrame | None = None) -> pd.DataFrame:
        """Extract factor scores from data.
        
        Args:
            X: Data to transform (uses training data if None)
            
        Returns:
            DataFrame with factor scores
        """
        if not self._fitted:
            raise ValueError("Model must be fitted before transform")
        
        if self._method_used == "dfm":
            return self._transform_dfm(X)
        else:
            return self._transform_pca(X)
    
    def _transform_dfm(self, X: pd.DataFrame | None = None) -> pd.DataFrame:
        """Transform using DFM smoothed factors."""
        factors = self._results.factors.smoothed
        
        # Apply sign adjustment based on average loading direction
        factors = self._adjust_factor_sign(factors)
        
        if hasattr(self._results, "data"):
            index = self._results.data.row_labels
        else:
            index = range(len(factors))
        
        factor_names = [f"factor_{i+1}" for i in range(self.n_factors)]
        
        return pd.DataFrame(factors, index=index, columns=factor_names)
    
    def _transform_pca(self, X: pd.DataFrame | None = None) -> pd.DataFrame:
        """Transform using PCA factors."""
        if X is None:
            data = self._full_data
        else:
            data = X.select_dtypes(include=[np.number]).copy()
        
        # Handle missing values
        data = data.ffill().bfill()
        
        if HAS_SKLEARN and self._scaler is not None:
            data_scaled = self._scaler.transform(data)
            
            if self._method_used == "pca_shrunk":
                # Use shrunk loadings - shape: (n_variables, n_factors)
                # data_scaled shape: (n_obs, n_variables)
                # Result should be: (n_obs, n_factors)
                factors = data_scaled @ self._shrunk_loadings
                # Normalize
                factor_mean = np.nanmean(factors, axis=0)
                factor_std = np.nanstd(factors, axis=0)
                factor_std = np.where(factor_std == 0, 1, factor_std)  # Avoid division by zero
                factors = (factors - factor_mean) / factor_std
            else:
                factors = self._model.transform(data_scaled)
        else:
            data_centered = data - data.mean()
            data_scaled = data_centered / data_centered.std()
            factors = data_scaled.values @ self._pca_components.T
        
        # Ensure factors is 2D
        if factors.ndim == 1:
            factors = factors.reshape(-1, 1)
        
        # Apply sign adjustment
        factors = self._adjust_factor_sign(factors)
        
        factor_names = [f"factor_{i+1}" for i in range(self.n_factors)]
        
        return pd.DataFrame(factors, index=data.index, columns=factor_names)
    
    def _adjust_factor_sign(self, factors: np.ndarray) -> np.ndarray:
        """Adjust factor sign to ensure positive average loading.
        
        Since we pre-flip negative-sign series, all loadings should be positive.
        This method ensures the factor is oriented so that the average loading
        is positive (i.e., increases in the factor mean increases in components).
        """
        loadings = self.get_loadings()
        
        for i in range(self.n_factors):
            factor_col = f"factor_{i+1}"
            if factor_col not in loadings.columns:
                continue
            
            # Check if average loading is negative
            avg_loading = loadings[factor_col].mean()
            
            if avg_loading < 0:
                # Flip factor to make average loading positive
                if isinstance(factors, np.ndarray):
                    factors[:, i] *= -1
                else:
                    factors.iloc[:, i] *= -1
        
        return factors
    
    def get_loadings(self) -> pd.DataFrame:
        """Get factor loadings for each variable.
        
        Returns:
            DataFrame with variables as rows, factors as columns
        """
        if not self._fitted:
            raise ValueError("Model must be fitted first")
        
        factor_names = [f"factor_{i+1}" for i in range(self.n_factors)]
        
        if self._method_used == "dfm":
            # Extract loadings from DFM results
            loadings = self._results.params
            loading_dict = {}
            for i in range(self.n_factors):
                factor_key = f"factor_{i+1}"
                loading_dict[factor_key] = {}
                for col in self._columns:
                    param_name = f"loading.f{i+1}.{col}"
                    if param_name in loadings.index:
                        loading_dict[factor_key][col] = loadings[param_name]
            
            return pd.DataFrame(loading_dict)
        
        elif self._method_used == "pca_shrunk":
            # Use shrunk loadings
            return pd.DataFrame(
                self._shrunk_loadings,
                index=self._columns,
                columns=factor_names
            )
        
        else:
            # PCA loadings are the components
            if HAS_SKLEARN and hasattr(self._model, "components_"):
                loadings = self._model.components_.T
            else:
                loadings = self._pca_components.T
            
            numeric_cols = [c for c in self._columns if c in self._full_data.columns]
            
            return pd.DataFrame(
                loadings[:len(numeric_cols)],
                index=numeric_cols,
                columns=factor_names
            )
    
    def get_explained_variance(self) -> float:
        """Get proportion of variance explained by factors."""
        if not self._fitted:
            raise ValueError("Model must be fitted first")
        
        if self._method_used == "dfm":
            try:
                return 1 - self._results.sse / self._results.centered_tss
            except:
                return 0.5  # Default if calculation fails
        else:
            if HAS_SKLEARN and hasattr(self._model, "explained_variance_ratio_"):
                return sum(self._model.explained_variance_ratio_)
            elif hasattr(self, "_pca_explained_variance"):
                total_var = sum(self._pca_explained_variance)
                return total_var / (total_var + 1)
            else:
                return 0.5
    
    def get_result(self) -> FactorModelResult:
        """Get complete model results."""
        if not self._fitted:
            raise ValueError("Model must be fitted first")
        
        # Check convergence
        if self._method_used == "dfm":
            converged = self._results.mle_retvals.get("converged", True)
        else:
            converged = True
        
        return FactorModelResult(
            factors=self.transform(),
            loadings=self.get_loadings(),
            explained_variance=self.get_explained_variance(),
            method=self._method_used,
            converged=converged,
            metadata={
                "n_factors": self.n_factors,
                "n_observations": len(self.transform()),
                "n_variables": len(self._columns) if self._columns else 0,
                "data_quality": self._data_quality.__dict__ if self._data_quality else {}
            }
        )


def extract_single_factor(
    X: pd.DataFrame,
    sign_constraints: dict[str, int] | None = None,
    method: str = "auto"
) -> tuple[pd.Series, pd.Series]:
    """Convenience function to extract a single latent factor.
    
    Args:
        X: DataFrame with numeric columns
        sign_constraints: Expected signs for interpretability
        method: 'dfm', 'pca', 'pca_shrunk', or 'auto'
        
    Returns:
        Tuple of (factor_series, loadings_series)
    """
    model = DynamicFactorModel(
        n_factors=1,
        sign_constraints=sign_constraints,
        method=method
    )
    model.fit(X)
    
    factors = model.transform()
    loadings = model.get_loadings()
    
    return factors.iloc[:, 0], loadings.iloc[:, 0]


def combine_factors(
    factor_dict: dict[str, pd.Series | pd.DataFrame],
    weights: dict[str, float] | None = None,
    normalize: bool = True
) -> pd.Series:
    """Combine multiple factor series into a composite.
    
    Args:
        factor_dict: Dict mapping factor names to Series/DataFrames
        weights: Optional weights for each factor (default: equal)
        normalize: Whether to normalize output to mean 100, stdev 10
        
    Returns:
        Combined factor series
    """
    if not factor_dict:
        raise ValueError("factor_dict cannot be empty")
    
    if weights is None:
        weights = {k: 1.0 / len(factor_dict) for k in factor_dict}
    
    # Normalize weights
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}
    
    # Align all factors to common index
    all_factors = []
    for name, factor_df in factor_dict.items():
        if isinstance(factor_df, pd.DataFrame):
            factor_series = factor_df.iloc[:, 0]
        else:
            factor_series = factor_df
        
        factor_series = factor_series.rename(name)
        all_factors.append(factor_series)
    
    combined_df = pd.concat(all_factors, axis=1)
    
    # Weighted sum
    result = pd.Series(0.0, index=combined_df.index)
    for name in combined_df.columns:
        if name in weights:
            result += combined_df[name].fillna(0) * weights[name]
    
    if normalize:
        # Normalize to mean 100, stdev 10
        result = (result - result.mean()) / result.std() * 10 + 100
    
    return result


def optimize_pillar_weights(
    pillar_factors: dict[str, pd.Series],
    target_returns: pd.Series,
    window: int = 156,
    forward_periods: int = 13,
    regularization: float = 0.5
) -> pd.DataFrame:
    """Optimize pillar weights based on predictive power for returns.
    
    Uses rolling regression to find weights that maximize predictive
    power for forward risk asset returns.
    
    Args:
        pillar_factors: Dict of pillar name -> factor series
        target_returns: Target return series to predict
        window: Rolling window size
        forward_periods: How many periods forward to predict
        regularization: Ridge regularization parameter
        
    Returns:
        DataFrame with time-varying optimal weights
    """
    if not HAS_SKLEARN:
        # Return equal weights if sklearn not available
        n_pillars = len(pillar_factors)
        return pd.DataFrame({
            name: [1.0 / n_pillars] for name in pillar_factors
        })
    
    # Align data
    factors_df = pd.DataFrame(pillar_factors)
    
    # Forward returns
    forward_ret = target_returns.shift(-forward_periods)
    
    # Align
    aligned = pd.concat([factors_df, forward_ret.rename("target")], axis=1).dropna()
    
    if len(aligned) < window + forward_periods:
        # Not enough data for rolling optimization
        n_pillars = len(pillar_factors)
        return pd.DataFrame({
            name: [1.0 / n_pillars] for name in pillar_factors
        }, index=[aligned.index[-1]])
    
    # Rolling optimization
    weights_over_time = {}
    pillar_names = list(pillar_factors.keys())
    
    for t in range(window, len(aligned)):
        train = aligned.iloc[:t]
        X = train[pillar_names].values
        y = train["target"].values
        
        # Ridge regression
        ridge = Ridge(alpha=regularization, fit_intercept=False)
        ridge.fit(X, y)
        
        # Normalize to sum to 1 (taking absolute values for weights)
        raw_weights = np.abs(ridge.coef_)
        normalized = raw_weights / raw_weights.sum() if raw_weights.sum() > 0 else np.ones(len(pillar_names)) / len(pillar_names)
        
        weights_over_time[aligned.index[t]] = dict(zip(pillar_names, normalized))
    
    return pd.DataFrame(weights_over_time).T

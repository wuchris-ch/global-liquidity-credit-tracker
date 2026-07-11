"""Dynamic Factor Model implementation for latent factor extraction."""
import pandas as pd
import numpy as np
from importlib.util import find_spec
from typing import Literal
from dataclasses import dataclass, field
import warnings

# Try to import statsmodels for DFM
try:
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    HAS_STATSMODELS_DFM = True
except ImportError:
    HAS_STATSMODELS_DFM = False

# Detect optional mixed-frequency DFM support without importing an unused class.
HAS_MIXED_FREQ = (
    find_spec("statsmodels.tsa.statespace.dynamic_factor_mq") is not None
)


SIGN_CONSTRAINT_TOLERANCE = 1e-6


class FactorSignConstraintError(ValueError):
    """Raised when a fitted factor contradicts an economic sign constraint."""

    def __init__(self, violations: list[str], details: list[str] | None = None) -> None:
        self.violations = list(dict.fromkeys(violations))
        self.details = details or self.violations
        super().__init__(
            "Factor loading sign constraint violated for: " + "; ".join(self.details)
        )


def find_sign_violations(
    loadings: pd.DataFrame,
    sign_constraints: dict[str, int],
    *,
    factor_col: str = "factor_1",
    tolerance: float = SIGN_CONSTRAINT_TOLERANCE,
) -> list[str]:
    """Return constrained features with materially wrong-signed loadings."""
    if tolerance < 0:
        raise ValueError("sign constraint tolerance cannot be negative")
    if factor_col not in loadings.columns:
        raise ValueError(f"Loading column '{factor_col}' is unavailable")

    violations = []
    for feature, expected_sign in sign_constraints.items():
        if expected_sign not in (-1, 1):
            raise ValueError(
                f"Sign constraint for '{feature}' must be +1 or -1, got {expected_sign}"
            )
        if feature not in loadings.index:
            # Near-constant or otherwise unusable features can be removed before
            # fitting and are reported separately as excluded inputs.
            continue
        loading = float(loadings.loc[feature, factor_col])
        if not np.isfinite(loading) or loading * expected_sign < -tolerance:
            violations.append(str(feature))
    return violations

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
    - Sign constraints applied to already oriented features before extraction
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
    ) -> None:
        """Initialize the Dynamic Factor Model.
        
        Args:
            n_factors: Number of latent factors to extract
            factor_order: AR order for factor dynamics (DFM only)
            error_order: AR order for idiosyncratic errors (DFM only)
            sign_constraints: Dict mapping column names to expected signs (+1/-1)
                             Note: inputs are already oriented, so all should be +1
            max_iter: Maximum iterations for dynamic-factor optimization
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
        self._factor_orientations = np.ones(self.n_factors, dtype=float)
        self._sign_violations: list[str] = []
    
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
        self._fitted = False
        self._sign_violations = []
        self._factor_orientations = np.ones(self.n_factors, dtype=float)

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

        raw_loadings = self._get_raw_loadings()
        self._factor_orientations = self._determine_factor_orientations(raw_loadings)
        oriented_loadings = self._orient_loadings(raw_loadings)
        self._sign_violations = find_sign_violations(
            oriented_loadings,
            self.sign_constraints,
        )
        if self._sign_violations:
            details = []
            for feature in self._sign_violations:
                loading = float(oriented_loadings.loc[feature, "factor_1"])
                expected = self.sign_constraints[feature]
                details.append(
                    f"{feature} (loading={loading:.6g}, expected={expected:+d})"
                )
            raise FactorSignConstraintError(self._sign_violations, details)

        self._fitted = True
        return self
    
    def _choose_method(self, X: pd.DataFrame) -> str:
        """Automatically choose the best estimation method."""
        # The GLCI supplies economic sign constraints for every oriented input.
        # Of the available estimators, the shrunk PCA path can enforce those
        # constraints during fitting. An unconstrained DFM can only discover a
        # contradiction after the fact, which would make the selected method
        # depend on the current missing-data pattern.
        if self.sign_constraints:
            if HAS_SKLEARN:
                return "pca_shrunk"
            raise RuntimeError(
                "Sign-constrained factor extraction requires scikit-learn"
            )

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
    
    def _fit_dfm(self, X: pd.DataFrame, mask: pd.DataFrame | None = None) -> None:
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
                data_scaled.dropna(),  # DFM initialization needs complete data
                k_factors=self.n_factors,
                factor_order=self.factor_order,
                error_order=self.error_order
            )
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                results = model.fit(
                    method="lbfgs",
                    maxiter=self.max_iter,
                    disp=False
                )

            if not results.mle_retvals.get("converged", False):
                raise RuntimeError("DFM maximum-likelihood fit did not converge")
            
            self._model = model
            self._results = results
            self._method_used = "dfm"
            
        except Exception as e:
            warnings.warn(f"DFM fitting failed: {e}. Falling back to PCA.")
            self._fit_pca(X)
    
    def _fit_dfm_mq(self, X: pd.DataFrame) -> None:
        """Fit using statsmodels Mixed-Frequency DFM."""
        # This would require frequency information for each column
        # Falling back to regular DFM for now
        self._fit_dfm(X)
    
    def _fit_pca_shrunk(self, X: pd.DataFrame) -> None:
        """Fit PCA with ridge shrinkage and optional loading constraints.

        For the one-factor GLCI model, each configured economic sign is
        enforced in a projected alternating least-squares fit. Loadings and the
        final factor are updated jointly until they agree. A feature that moves
        against the oriented common factor receives a zero loading instead of
        silently reversing its economic meaning. The post-fit audit remains in
        place as a gate.
        """
        data = self._prepare_pca_data(X)
        
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
            
            factors_raw = pca.transform(data_scaled)
            
            # Ensure factors_raw is 2D for Ridge
            if factors_raw.ndim == 1:
                factors_raw = factors_raw.reshape(-1, 1)

            if self.sign_constraints and self.n_factors != 1:
                raise ValueError(
                    "Sign-constrained pca_shrunk currently supports one factor"
                )

            if self.sign_constraints:
                (
                    self._shrunk_loadings,
                    fitted_factor,
                    self._constraint_iterations,
                ) = self._fit_constrained_rank_one(data_scaled, factors_raw[:, 0])
                reconstruction = np.outer(
                    fitted_factor,
                    self._shrunk_loadings[:, 0],
                )
                total_sum_squares = float(np.square(data_scaled).sum())
                residual_sum_squares = float(
                    np.square(data_scaled - reconstruction).sum()
                )
                self._shrunk_explained_variance = (
                    1.0 - residual_sum_squares / total_sum_squares
                    if total_sum_squares > 0
                    else float("nan")
                )
            else:
                # Without sign constraints, retain the general multi-factor
                # ridge decoder used by the diagnostic estimator.
                shrunk_loadings = []
                for i in range(data_scaled.shape[1]):
                    ridge = Ridge(
                        alpha=self.shrinkage_alpha,
                        fit_intercept=False,
                    )
                    ridge.fit(factors_raw, data_scaled[:, i])
                    shrunk_loadings.append(ridge.coef_.flatten())
                self._shrunk_loadings = np.asarray(shrunk_loadings)
                self._shrunk_explained_variance = float(
                    np.sum(pca.explained_variance_ratio_)
                )

        active_loadings = np.any(
            np.abs(self._shrunk_loadings) > SIGN_CONSTRAINT_TOLERANCE,
            axis=1,
        )
        if int(active_loadings.sum()) < self.min_variables:
            raise ValueError(
                "Sign constraints left fewer than "
                f"{self.min_variables} active factor inputs"
            )

        factor_projection = data_scaled @ self._shrunk_loadings
        self._factor_projection_mean = np.mean(factor_projection, axis=0)
        self._factor_projection_std = np.std(factor_projection, axis=0)
        if np.any(~np.isfinite(self._factor_projection_std)) or np.any(
            self._factor_projection_std <= 1e-12
        ):
            raise ValueError("Shrunk factor projection has no usable variation")
        self._model = pca
        self._valid_index = data_clean.index
        self._full_data = data
        self._method_used = "pca_shrunk"

    def _fit_constrained_rank_one(
        self,
        data_scaled: np.ndarray,
        initial_factor: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, int]:
        """Jointly solve a ridge-shrunk rank-one model with signed loadings."""
        for feature, expected_sign in self.sign_constraints.items():
            if expected_sign not in (-1, 1):
                raise ValueError(
                    f"Sign constraint for '{feature}' must be +1 or -1, "
                    f"got {expected_sign}"
                )

        factor = np.asarray(initial_factor, dtype=float).copy()
        provisional = data_scaled.T @ factor
        constrained_scores = [
            provisional[self._columns.index(feature)] * expected_sign
            for feature, expected_sign in self.sign_constraints.items()
            if feature in self._columns
        ]
        if constrained_scores and float(np.mean(constrained_scores)) < 0:
            factor *= -1

        factor_std = float(np.std(factor))
        if not np.isfinite(factor_std) or factor_std <= 1e-12:
            raise ValueError("Initial PCA factor has no usable variation")
        factor = (factor - float(np.mean(factor))) / factor_std

        previous_loadings: np.ndarray | None = None
        tolerance = 1e-10
        for iteration in range(1, self.max_iter + 1):
            denominator = float(factor @ factor + self.shrinkage_alpha)
            loadings = (data_scaled.T @ factor) / denominator

            for feature, expected_sign in self.sign_constraints.items():
                if feature not in self._columns:
                    continue
                position = self._columns.index(feature)
                if loadings[position] * expected_sign < 0:
                    loadings[position] = 0.0

            projection = data_scaled @ loadings
            projection_std = float(np.std(projection))
            if not np.isfinite(projection_std) or projection_std <= 1e-12:
                raise ValueError("Sign constraints removed all factor variation")
            next_factor = (
                projection - float(np.mean(projection))
            ) / projection_std

            factor_change = float(np.max(np.abs(next_factor - factor)))
            loading_change = (
                float("inf")
                if previous_loadings is None
                else float(np.max(np.abs(loadings - previous_loadings)))
            )
            factor = next_factor
            if factor_change <= tolerance and loading_change <= tolerance:
                return loadings.reshape(-1, 1), factor, iteration
            previous_loadings = loadings

        raise RuntimeError(
            "Sign-constrained rank-one factor did not converge within "
            f"{self.max_iter} iterations"
        )
    
    def _fit_pca(self, X: pd.DataFrame) -> None:
        """Fit using standard PCA (fallback method)."""
        data = self._prepare_pca_data(X)
        
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
                self._manual_mean = data_clean.mean()
                self._manual_std = data_clean.std().replace(0, 1)
                data_centered = data_clean - self._manual_mean
                data_scaled = data_centered / self._manual_std
                
                U, S, Vt = np.linalg.svd(data_scaled.values, full_matrices=False)
                
                self._pca_components = Vt[:self.n_factors]
                self._pca_explained_variance = (S[:self.n_factors] ** 2) / (len(data_clean) - 1)
                self._valid_index = data_clean.index
                self._model = "manual_pca"
        
        self._method_used = "pca"
        self._full_data = data

    def _prepare_pca_data(self, X: pd.DataFrame) -> pd.DataFrame:
        """Prepare PCA inputs using only contemporaneous or past observations.

        PCA requires a complete matrix. Training begins only once every input
        series has produced at least one observation. Later gaps use a bounded
        forward fill and then the expanding mean available at that row. No
        future value is copied backward into leading history.
        """
        data = X.select_dtypes(include=[np.number]).copy()
        if self._columns:
            missing_columns = [col for col in self._columns if col not in data.columns]
            if missing_columns:
                raise ValueError(
                    "PCA input is missing fitted columns: "
                    + ", ".join(missing_columns)
                )
            data = data[self._columns]

        first_valid_positions = []
        for col in data.columns:
            valid = np.flatnonzero(data[col].notna().to_numpy())
            if not len(valid):
                raise ValueError(f"PCA input column '{col}' has no observations")
            first_valid_positions.append(int(valid[0]))

        common_start = max(first_valid_positions)
        past_means = data.expanding(min_periods=1).mean()
        prepared = data.iloc[common_start:].copy()
        prepared = prepared.ffill(limit=26)
        prepared = prepared.fillna(past_means.iloc[common_start:])

        if prepared.isna().any().any():
            missing = prepared.columns[prepared.isna().any()].tolist()
            raise ValueError(
                "PCA input could not be imputed from past observations: "
                + ", ".join(missing)
            )
        return prepared
    
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
        # statsmodels exposes (n_factors, n_observations); the shared model
        # interface uses rows as observations.
        factors = np.asarray(self._results.factors.smoothed).T
        
        factors = self._apply_factor_orientation(factors)
        
        if hasattr(self._results, "data"):
            index = self._results.data.row_labels
        else:
            index = range(len(factors))
        
        factor_names = [f"factor_{i+1}" for i in range(self.n_factors)]
        
        return pd.DataFrame(factors, index=index, columns=factor_names)
    
    def _transform_pca(self, X: pd.DataFrame | None = None) -> pd.DataFrame:
        """Transform using PCA factors."""
        if X is None:
            # Reuse the exact past-only frame prepared during fitting.
            data = self._full_data.copy()
        else:
            data = self._prepare_pca_data(X)
        
        if HAS_SKLEARN and self._scaler is not None:
            data_scaled = self._scaler.transform(data)
            
            if self._method_used == "pca_shrunk":
                factors = data_scaled @ self._shrunk_loadings
                # Use training normalization for both in-sample and new data.
                # Re-normalizing each transform request would make the same
                # observation depend on the requested slice.
                factors = (
                    factors - self._factor_projection_mean
                ) / self._factor_projection_std
            else:
                factors = self._model.transform(data_scaled)
        else:
            data_centered = data - self._manual_mean
            data_scaled = data_centered / self._manual_std
            factors = data_scaled.values @ self._pca_components.T
        
        # Ensure factors is 2D
        if factors.ndim == 1:
            factors = factors.reshape(-1, 1)
        
        factors = self._apply_factor_orientation(factors)
        
        factor_names = [f"factor_{i+1}" for i in range(self.n_factors)]
        
        return pd.DataFrame(factors, index=data.index, columns=factor_names)
    
    def _determine_factor_orientations(self, loadings: pd.DataFrame) -> np.ndarray:
        """Choose one global sign per factor before auditing individual loadings."""
        orientations = np.ones(self.n_factors, dtype=float)
        for i in range(self.n_factors):
            factor_col = f"factor_{i+1}"
            if factor_col not in loadings.columns:
                continue

            constrained_scores = []
            for feature, expected_sign in self.sign_constraints.items():
                if expected_sign not in (-1, 1):
                    raise ValueError(
                        f"Sign constraint for '{feature}' must be +1 or -1, "
                        f"got {expected_sign}"
                    )
                if feature in loadings.index:
                    constrained_scores.append(
                        float(loadings.loc[feature, factor_col]) * expected_sign
                    )

            orientation_score = (
                float(np.mean(constrained_scores))
                if constrained_scores
                else float(loadings[factor_col].mean())
            )
            if np.isfinite(orientation_score) and orientation_score < 0:
                orientations[i] = -1.0
        return orientations

    def _apply_factor_orientation(self, factors: np.ndarray) -> np.ndarray:
        """Apply the fitted global orientation to factor scores."""
        oriented = np.asarray(factors, dtype=float).copy()
        oriented *= self._factor_orientations.reshape(1, -1)
        return oriented

    def _orient_loadings(self, loadings: pd.DataFrame) -> pd.DataFrame:
        """Apply the same global orientation to reported factor loadings."""
        oriented = loadings.copy()
        for i, orientation in enumerate(self._factor_orientations):
            factor_col = f"factor_{i+1}"
            if factor_col in oriented.columns:
                oriented[factor_col] = oriented[factor_col] * orientation
        return oriented

    def get_sign_violations(self) -> list[str]:
        """Return the features rejected by the latest sign audit."""
        return list(self._sign_violations)
    
    def get_loadings(self) -> pd.DataFrame:
        """Get factor loadings for each variable.
        
        Returns:
            DataFrame with variables as rows, factors as columns
        """
        if not self._fitted:
            raise ValueError("Model must be fitted first")

        return self._orient_loadings(self._get_raw_loadings())

    def _get_raw_loadings(self) -> pd.DataFrame:
        """Get estimator-native loadings before the global sign orientation."""
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
            # statsmodels occasionally omits sse/centered_tss depending on model
            # convergence state; return NaN so callers can detect the missing
            # value rather than a silently-made-up number.
            sse = getattr(self._results, "sse", None)
            centered_tss = getattr(self._results, "centered_tss", None)
            if sse is None or centered_tss in (None, 0):
                return float("nan")
            return 1 - sse / centered_tss
        elif self._method_used == "pca_shrunk" and hasattr(
            self, "_shrunk_explained_variance"
        ):
            return self._shrunk_explained_variance
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
        
        loadings = self.get_loadings()
        constraint_exclusions = [
            feature
            for feature in self.sign_constraints
            if feature in loadings.index
            and abs(float(loadings.loc[feature, "factor_1"]))
            <= SIGN_CONSTRAINT_TOLERANCE
        ]

        return FactorModelResult(
            factors=self.transform(),
            loadings=loadings,
            explained_variance=self.get_explained_variance(),
            method=self._method_used,
            converged=converged,
            metadata={
                "n_factors": self.n_factors,
                "n_observations": len(self.transform()),
                "n_variables": len(self._columns) if self._columns else 0,
                "data_quality": self._data_quality.__dict__ if self._data_quality else {},
                "sign_constraints": self.sign_constraints,
                "sign_constraint_tolerance": SIGN_CONSTRAINT_TOLERANCE,
                "sign_violations": self.get_sign_violations(),
                "constraint_exclusions": constraint_exclusions,
                "loading_semantics": (
                    "joint_rank_one_decoder_loadings"
                    if self._method_used == "pca_shrunk" and self.sign_constraints
                    else "estimator_loadings"
                ),
                "constraint_solver_iterations": getattr(
                    self,
                    "_constraint_iterations",
                    None,
                ),
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

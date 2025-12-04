"""Indicator computation and aggregation module."""
from .aggregator import Aggregator
from .transforms import (
    resample_to_frequency,
    compute_yoy_change,
    compute_zscore,
    normalize_to_usd,
    compute_growth_rate,
    compute_rolling_gap,
    compute_credit_impulse,
    compute_hp_filter_gap,
    standardize_series,
    detect_regime,
    compute_momentum,
    compute_regime_probability,
    apply_sign_flip,
    detect_frequency,
    get_frequency_periods,
)
from .factors import (
    FeatureMatrixBuilder,
    FeatureMetadata,
    DataQualityReport,
    get_pillar_weights,
    get_pillar_signs,
    get_component_signs,
)
from .dynamic_factor import (
    DynamicFactorModel,
    FactorModelResult,
    DataQualityCheck,
    extract_single_factor,
    combine_factors,
    optimize_pillar_weights,
)
from .glci import (
    GLCIComputer,
    GLCIResult,
    GLCIPillarResult,
    compute_glci,
)

__all__ = [
    # Core aggregation
    "Aggregator",
    # Transforms
    "resample_to_frequency",
    "compute_yoy_change",
    "compute_zscore",
    "normalize_to_usd",
    "compute_growth_rate",
    "compute_rolling_gap",
    "compute_credit_impulse",
    "compute_hp_filter_gap",
    "standardize_series",
    "detect_regime",
    "compute_momentum",
    "compute_regime_probability",
    "apply_sign_flip",
    "detect_frequency",
    "get_frequency_periods",
    # Factor modeling
    "FeatureMatrixBuilder",
    "FeatureMetadata",
    "DataQualityReport",
    "DynamicFactorModel",
    "FactorModelResult",
    "DataQualityCheck",
    "extract_single_factor",
    "combine_factors",
    "optimize_pillar_weights",
    "get_pillar_weights",
    "get_pillar_signs",
    "get_component_signs",
    # GLCI
    "GLCIComputer",
    "GLCIResult",
    "GLCIPillarResult",
    "compute_glci",
]

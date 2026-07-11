"""Risk metrics computation for asset classes conditioned on GLCI regimes."""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime

from ..etl.fetcher import DataFetcher
from ..etl.storage import DataStorage


def _as_ns_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce the date column to tz-naive datetime64[ns].

    merge_asof requires both keys to have the exact same dtype. Under
    pandas >= 3, parquet roundtrips yield datetime64[us] while yfinance
    yields datetime64[s], which makes the merge raise instead of coerce.
    """
    dates = pd.to_datetime(df["date"])
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    df["date"] = dates.astype("datetime64[ns]")
    return df


@dataclass
class AssetRiskMetrics:
    """Risk metrics for a single asset."""
    asset_id: str
    name: str
    category: str
    current_sharpe: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe_by_regime: dict[str, float | None]  # regime_label -> sharpe
    return_by_regime: dict[str, float | None]
    volatility_by_regime: dict[str, float | None]
    correlation_with_glci: float | None
    rolling_sharpe_data: list[dict]  # [{date, value}, ...]
    # Internal calculation policy. These are disclosed in result/storage
    # metadata but intentionally omitted from the stable asset JSON schema.
    annualization_factor: int
    rolling_window: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.asset_id,
            "name": self.name,
            "category": self.category,
            "current_sharpe": self.current_sharpe,
            "annualized_return": self.annualized_return,
            "annualized_volatility": self.annualized_volatility,
            "max_drawdown": self.max_drawdown,
            "sharpe_by_regime": self.sharpe_by_regime,
            "return_by_regime": self.return_by_regime,
            "volatility_by_regime": self.volatility_by_regime,
            "correlation_with_glci": self.correlation_with_glci,
            "rolling_sharpe": self.rolling_sharpe_data,
        }


@dataclass
class RiskDashboardResult:
    """Complete risk dashboard data."""
    computed_at: str
    risk_free_rate: float
    current_regime: str | None
    assets: list[AssetRiskMetrics]
    regime_performance_matrix: dict  # For heatmap visualization
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "computed_at": self.computed_at,
            "risk_free_rate": self.risk_free_rate,
            "current_regime": self.current_regime,
            "assets": [a.to_dict() for a in self.assets],
            "regime_matrix": self.regime_performance_matrix,
            "metadata": self.metadata,
        }


# Asset configuration: maps series_id to display info.
# Shared by the risk dashboard and the backtest (the Playbook page).
ASSET_CONFIG = {
    "sp500_price": {"name": "S&P 500", "category": "Large Cap Equities"},
    "nasdaq100": {"name": "Nasdaq 100", "category": "Large Cap Equities"},
    "semis_price": {"name": "Semiconductors (SMH)", "category": "AI Trade"},
    "russell2000_price": {"name": "Russell 2000", "category": "Small Cap Equities"},
    "gold_price": {"name": "Gold", "category": "Commodities"},
    "silver_price": {"name": "Silver", "category": "Commodities"},
    "bitcoin_price": {
        "name": "Bitcoin", "category": "Crypto", "annualization_factor": 365
    },
    "ethereum_price": {
        "name": "Ethereum", "category": "Crypto", "annualization_factor": 365
    },
    "zcash_price": {
        "name": "Zcash", "category": "Crypto", "annualization_factor": 365
    },
    "long_bond_price": {"name": "Long Bonds (TLT)", "category": "Fixed Income"},
}


class RiskMetricsComputer:
    """Computes risk metrics conditioned on GLCI regimes."""

    ANNUALIZATION_FACTOR = 252  # Default for trading-day assets
    CALENDAR_ANNUALIZATION_FACTOR = 365
    MIN_CORRELATION_OBSERVATIONS = 20

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        storage: DataStorage | None = None,
        rolling_window: int | None = None,
    ) -> None:
        if rolling_window is not None and rolling_window < 1:
            raise ValueError("rolling_window must be a positive integer")
        self.fetcher = fetcher or DataFetcher()
        self.storage = storage or DataStorage()
        self._rolling_window_override = rolling_window
        # Keep the historical public/default value for compatibility. The
        # effective default is resolved per asset by _rolling_window_for().
        self.rolling_window = (
            rolling_window
            if rolling_window is not None
            else self.ANNUALIZATION_FACTOR
        )

    def compute(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        save_output: bool = False,
        verbose: bool = True
    ) -> RiskDashboardResult:
        """Compute risk metrics for all configured assets.

        Args:
            start_date: Start date for analysis (default: all available)
            end_date: End date for analysis (default: today)
            save_output: Whether to save results to storage
            verbose: Print progress

        Returns:
            RiskDashboardResult with all metrics
        """
        if verbose:
            print("Computing risk metrics...")

        # 1. Load GLCI regime data
        glci_df = self._load_glci_regimes()
        if glci_df is None:
            raise ValueError("GLCI data not found. Run GLCI computation first.")

        if verbose:
            print(f"  Loaded GLCI data: {len(glci_df)} observations")

        # 2. Load risk-free rate (3-month Treasury)
        rf_df = self._load_risk_free_rate()
        if verbose and rf_df is not None:
            print(f"  Loaded risk-free rate: {rf_df['value'].iloc[-1]:.2f}%")

        # 3. Compute metrics for each asset
        asset_metrics = []
        for asset_id, config in ASSET_CONFIG.items():
            if verbose:
                print(f"  Processing {config['name']}...")

            try:
                metrics = self._compute_asset_metrics(
                    asset_id, config, glci_df, rf_df, start_date, end_date
                )
                asset_metrics.append(metrics)
                if verbose:
                    print(f"    Sharpe: {metrics.current_sharpe:.2f}, Return: {metrics.annualized_return:.1f}%")
            except Exception as e:
                if verbose:
                    print(f"    Warning: Could not compute metrics for {asset_id}: {e}")

        # 4. Build regime performance matrix
        regime_matrix = self._build_regime_matrix(asset_metrics)

        # 5. Get current regime
        current_regime = self._current_regime(glci_df)

        # 6. Get current risk-free rate
        current_rf = float(rf_df["value"].iloc[-1]) if rf_df is not None and not rf_df.empty else 0.0

        rolling_window_policy = (
            "explicit_override"
            if self._rolling_window_override is not None
            else "one_year_by_asset_clock"
        )
        asset_clock_policy = {
            asset.asset_id: {
                "annualization_factor": asset.annualization_factor,
                "rolling_window": asset.rolling_window,
            }
            for asset in asset_metrics
        }

        result = RiskDashboardResult(
            computed_at=datetime.utcnow().isoformat(),
            risk_free_rate=current_rf,
            current_regime=current_regime,
            assets=asset_metrics,
            regime_performance_matrix=regime_matrix,
            metadata={
                "rolling_window": self.rolling_window,
                "annualization_factor": self.ANNUALIZATION_FACTOR,
                "annualization_policy": "per_asset_observation_clock",
                "rolling_window_policy": rolling_window_policy,
                "asset_clock_policy": asset_clock_policy,
                "start_date": start_date,
                "end_date": end_date,
                "n_assets": len(asset_metrics),
            }
        )

        if save_output:
            self._save_results(result)

        if verbose:
            print(f"  Completed: {len(asset_metrics)} assets computed")

        return result

    @staticmethod
    def _current_regime(glci_df: pd.DataFrame) -> str | None:
        """Return the latest row's regime without inventing neutral."""
        if glci_df.empty or "regime" not in glci_df:
            return None
        latest = pd.to_numeric(glci_df["regime"], errors="coerce").iloc[-1]
        if pd.isna(latest):
            return None
        return {-1: "tight", 0: "neutral", 1: "loose"}.get(
            int(latest)
        )

    def _load_glci_regimes(self) -> pd.DataFrame | None:
        """Load GLCI data with regime classifications."""
        glci_df = self.storage.load_curated("indices", "glci")
        if glci_df is None:
            return None

        glci_df = _as_ns_dates(glci_df)
        glci_df = glci_df.sort_values("date")

        if "regime" not in glci_df.columns:
            raise ValueError("Stored GLCI data is missing the regime column")

        glci_df["regime_label"] = glci_df["regime"].map({
            -1: "tight", 0: "neutral", 1: "loose"
        })

        return glci_df

    def _load_risk_free_rate(self) -> pd.DataFrame | None:
        """Load 3-month Treasury rate for Sharpe calculation."""
        try:
            df = self.fetcher.fetch_series("treasury_3m")
            df = _as_ns_dates(df)
            df = df.sort_values("date")
            # Retain the legacy trading-day field for callers that inspect it.
            # Asset metrics derive their own daily rate from ``value`` because
            # calendar-daily assets use 365 observations per year.
            df["daily_rf"] = df["value"] / 100 / self.ANNUALIZATION_FACTOR
            return df
        except Exception as e:
            print(f"  Warning: Could not load risk-free rate: {e}")
            return None

    def _compute_asset_metrics(
        self,
        asset_id: str,
        config: dict[str, str | int],
        glci_df: pd.DataFrame,
        rf_df: pd.DataFrame | None,
        start_date: str | None,
        end_date: str | None
    ) -> AssetRiskMetrics:
        """Compute risk metrics for a single asset."""
        # Fetch price data
        price_df = self.fetcher.fetch_series(asset_id, start_date, end_date)
        price_df = _as_ns_dates(price_df)
        price_df = price_df.sort_values("date")
        annualization_factor = self._annualization_factor(asset_id, price_df["date"])
        rolling_window = self._rolling_window_for(annualization_factor)

        # Compute daily returns
        price_df["return"] = price_df["value"].pct_change()

        # Merge with GLCI regimes (forward-fill regime to daily data)
        merged = pd.merge_asof(
            price_df.sort_values("date"),
            glci_df[["date", "regime", "regime_label", "value"]].rename(
                columns={"value": "glci_value"}
            ).sort_values("date"),
            on="date",
            direction="backward"
        )

        # Merge with risk-free rate
        if rf_df is not None and not rf_df.empty:
            if "value" in rf_df.columns:
                rf_for_merge = rf_df[["date", "value"]].rename(
                    columns={"value": "annual_rf_percent"}
                )
            else:
                # Compatibility for callers supplying the old, precomputed
                # trading-day rate without its annual source value.
                rf_for_merge = rf_df[["date", "daily_rf"]].copy()
            merged = pd.merge_asof(
                merged.sort_values("date"),
                rf_for_merge.sort_values("date"),
                on="date",
                direction="backward"
            )
            if "annual_rf_percent" in merged.columns:
                merged["daily_rf"] = (
                    merged["annual_rf_percent"].fillna(0)
                    / 100
                    / annualization_factor
                )
            else:
                merged["daily_rf"] = (
                    merged["daily_rf"].fillna(0)
                    * self.ANNUALIZATION_FACTOR
                    / annualization_factor
                )
        else:
            merged["daily_rf"] = 0

        # Compute excess returns
        merged["excess_return"] = merged["return"] - merged["daily_rf"]

        # Drop NaN returns (first observation)
        merged = merged.dropna(subset=["return"])

        # Overall metrics
        current_sharpe = self._compute_sharpe(
            merged["excess_return"], annualization_factor
        )
        ann_return = float(merged["return"].mean() * annualization_factor * 100)
        ann_vol = float(merged["return"].std() * np.sqrt(annualization_factor) * 100)
        max_dd = self._compute_max_drawdown(price_df["value"].dropna())

        # Metrics by regime
        sharpe_by_regime: dict[str, float | None] = {}
        return_by_regime: dict[str, float | None] = {}
        vol_by_regime: dict[str, float | None] = {}

        for regime in ["tight", "neutral", "loose"]:
            regime_data = merged[merged["regime_label"] == regime]
            if len(regime_data) > 20:  # Minimum observations for meaningful stats
                sharpe_by_regime[regime] = self._compute_sharpe(
                    regime_data["excess_return"], annualization_factor
                )
                return_by_regime[regime] = float(
                    regime_data["return"].mean() * annualization_factor * 100
                )
                vol_by_regime[regime] = float(
                    regime_data["return"].std() * np.sqrt(annualization_factor) * 100
                )
            else:
                sharpe_by_regime[regime] = None
                return_by_regime[regime] = None
                vol_by_regime[regime] = None

        # Rolling Sharpe
        rolling_sharpe = self._compute_rolling_sharpe(
            merged, annualization_factor
        )

        # Correlation is measured on a common weekly clock. Comparing daily
        # returns with a forward-filled weekly index otherwise creates mostly
        # zero GLCI changes and a single artificial jump each week.
        correlation = self._compute_glci_correlation(price_df, glci_df)

        return AssetRiskMetrics(
            asset_id=asset_id,
            name=config["name"],
            category=config["category"],
            current_sharpe=current_sharpe,
            annualized_return=ann_return,
            annualized_volatility=ann_vol,
            max_drawdown=max_dd,
            sharpe_by_regime=sharpe_by_regime,
            return_by_regime=return_by_regime,
            volatility_by_regime=vol_by_regime,
            correlation_with_glci=correlation,
            rolling_sharpe_data=rolling_sharpe,
            annualization_factor=annualization_factor,
            rolling_window=rolling_window,
        )

    @classmethod
    def _annualization_factor(
        cls,
        asset_id: str,
        dates: pd.Series | pd.DatetimeIndex | None = None,
    ) -> int:
        """Return the appropriate daily observation count for an asset.

        Known calendar-daily assets are explicit in ``ASSET_CONFIG``. For an
        unconfigured series, regular weekend observations provide a safe
        fallback signal that the market trades seven days per week.
        """
        configured = ASSET_CONFIG.get(asset_id, {}).get("annualization_factor")
        if configured is not None:
            return int(configured)

        if dates is not None:
            clean_dates = pd.DatetimeIndex(pd.to_datetime(dates)).dropna().unique()
            if len(clean_dates) >= 30:
                weekend_share = float((clean_dates.dayofweek >= 5).mean())
                gaps = pd.Series(clean_dates.sort_values()).diff().dt.days.dropna()
                median_gap = float(gaps.median()) if not gaps.empty else np.inf
                if weekend_share >= 0.20 and median_gap <= 1.0:
                    return cls.CALENDAR_ANNUALIZATION_FACTOR

        return cls.ANNUALIZATION_FACTOR

    def _rolling_window_for(self, annualization_factor: int) -> int:
        """Resolve the lookback, honoring an explicit constructor override."""
        if self._rolling_window_override is not None:
            return self._rolling_window_override
        return annualization_factor

    def _compute_sharpe(
        self,
        excess_returns: pd.Series,
        annualization_factor: int | None = None,
    ) -> float | None:
        """Compute annualized Sharpe ratio."""
        factor = annualization_factor or self.ANNUALIZATION_FACTOR
        clean_returns = excess_returns.dropna()
        if len(clean_returns) < 20:
            return 0.0

        mean_return = clean_returns.mean()
        std_return = clean_returns.std()

        # Epsilon guard: a constant series has std ~1e-18 from float error,
        # not exactly 0, which would otherwise explode the ratio.
        if pd.isna(std_return) or std_return < 1e-12:
            return 0.0

        return float((mean_return / std_return) * np.sqrt(factor))

    def _compute_rolling_sharpe(
        self,
        df: pd.DataFrame,
        annualization_factor: int | None = None,
    ) -> list[dict]:
        """Compute rolling Sharpe ratio time series."""
        factor = annualization_factor or self.ANNUALIZATION_FACTOR
        window = self._rolling_window_for(factor)
        rolling_mean = df["excess_return"].rolling(window=window).mean()
        rolling_std = df["excess_return"].rolling(window=window).std()

        # Avoid division by zero
        rolling_sharpe = (
            (rolling_mean / rolling_std.replace(0, np.nan)) * np.sqrt(factor)
        )

        result = []
        for date, sharpe in zip(df["date"], rolling_sharpe):
            if not pd.isna(sharpe):
                result.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "value": round(float(sharpe), 3)
                })

        return result

    def _compute_glci_correlation(
        self,
        price_df: pd.DataFrame,
        glci_df: pd.DataFrame,
    ) -> float:
        """Correlate W-FRI asset returns with W-FRI GLCI level changes."""
        prices = (
            price_df[["date", "value"]]
            .dropna(subset=["date", "value"])
            .drop_duplicates(subset="date", keep="last")
            .set_index("date")["value"]
            .sort_index()
        )
        glci_values = (
            glci_df[["date", "value"]]
            .dropna(subset=["date", "value"])
            .drop_duplicates(subset="date", keep="last")
            .set_index("date")["value"]
            .sort_index()
        )

        weekly = pd.concat(
            [
                prices.resample("W-FRI").last().pct_change(fill_method=None).rename(
                    "asset_return"
                ),
                glci_values.resample("W-FRI").last().diff().rename("glci_change"),
            ],
            axis=1,
            join="inner",
        ).dropna()

        if len(weekly) < self.MIN_CORRELATION_OBSERVATIONS:
            return None
        if (
            weekly["asset_return"].std() < 1e-12
            or weekly["glci_change"].std() < 1e-12
        ):
            return None

        correlation = weekly["asset_return"].corr(weekly["glci_change"])
        return None if pd.isna(correlation) else float(correlation)

    def _compute_max_drawdown(self, prices: pd.Series) -> float:
        """Compute maximum drawdown percentage."""
        if len(prices) < 2:
            return 0.0

        peak = prices.expanding().max()
        drawdown = (prices - peak) / peak
        return float(drawdown.min() * 100)

    def _build_regime_matrix(self, assets: list[AssetRiskMetrics]) -> dict:
        """Build matrix of Sharpe ratios by asset and regime for heatmap."""
        matrix = {
            "assets": [],
            "regimes": ["tight", "neutral", "loose"],
            "sharpe_data": [],
            "return_data": [],
        }

        for asset in assets:
            matrix["assets"].append(asset.name)

            sharpe_row = []
            return_row = []
            for regime in ["tight", "neutral", "loose"]:
                sharpe = asset.sharpe_by_regime.get(regime)
                ret = asset.return_by_regime.get(regime)
                sharpe_row.append(round(sharpe, 2) if sharpe is not None else None)
                return_row.append(round(ret, 1) if ret is not None else None)

            matrix["sharpe_data"].append(sharpe_row)
            matrix["return_data"].append(return_row)

        return matrix

    def _save_results(self, result: RiskDashboardResult) -> None:
        """Save risk metrics to storage."""
        # Convert to DataFrame for storage
        assets_data = []
        for asset in result.assets:
            assets_data.append({
                "asset_id": asset.asset_id,
                "name": asset.name,
                "category": asset.category,
                "current_sharpe": asset.current_sharpe,
                "annualized_return": asset.annualized_return,
                "annualized_volatility": asset.annualized_volatility,
                "max_drawdown": asset.max_drawdown,
                "sharpe_tight": asset.sharpe_by_regime.get("tight"),
                "sharpe_neutral": asset.sharpe_by_regime.get("neutral"),
                "sharpe_loose": asset.sharpe_by_regime.get("loose"),
                "return_tight": asset.return_by_regime.get("tight"),
                "return_neutral": asset.return_by_regime.get("neutral"),
                "return_loose": asset.return_by_regime.get("loose"),
                "correlation_with_glci": asset.correlation_with_glci,
            })

        df = pd.DataFrame(assets_data)
        self.storage.save_curated(df, "risk", "risk_metrics", metadata=result.metadata)
        print("  Saved risk_metrics.parquet")

        # Also save rolling sharpe data for each asset
        for asset in result.assets:
            if asset.rolling_sharpe_data:
                rolling_df = pd.DataFrame(asset.rolling_sharpe_data)
                rolling_df["date"] = pd.to_datetime(rolling_df["date"])
                self.storage.save_curated(
                    rolling_df,
                    "risk",
                    f"rolling_sharpe_{asset.asset_id}",
                    metadata={
                        "asset_id": asset.asset_id,
                        "annualization_factor": asset.annualization_factor,
                        "window": asset.rolling_window,
                        "rolling_window_policy": result.metadata[
                            "rolling_window_policy"
                        ],
                    }
                )


def compute_risk_metrics(save: bool = False, verbose: bool = True) -> RiskDashboardResult:
    """Convenience function to compute risk metrics.

    Args:
        save: Whether to save results to storage
        verbose: Print progress

    Returns:
        RiskDashboardResult with all computed metrics
    """
    computer = RiskMetricsComputer()
    return computer.compute(save_output=save, verbose=verbose)

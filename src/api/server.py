"""FastAPI server exposing liquidity data."""
from datetime import datetime, timedelta
from typing import Literal
import warnings

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import get_all_series, get_all_indices, get_series_config, get_index_config
from ..etl import DataFetcher, DataStorage
from ..indicators import Aggregator, GLCIComputer


# Suppress noisy sklearn/statsmodels warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="sklearn")
warnings.filterwarnings("ignore", message="DFM fitting failed")


# Simple in-memory cache for GLCI results
class GLCICache:
    """Cache GLCI computation results with TTL."""
    def __init__(self, ttl_seconds: int = 300):  # 5 minute default TTL
        self.ttl = ttl_seconds
        self._cache: dict = {}
        self._timestamps: dict = {}
    
    def _make_key(self, start: str, end: str) -> str:
        return f"{start}:{end}"
    
    def get(self, start: str, end: str):
        key = self._make_key(start, end)
        if key not in self._cache:
            return None
        
        # Check TTL
        cached_time = self._timestamps.get(key, datetime.min)
        if datetime.now() - cached_time > timedelta(seconds=self.ttl):
            del self._cache[key]
            del self._timestamps[key]
            return None
        
        return self._cache[key]
    
    def set(self, start: str, end: str, result):
        key = self._make_key(start, end)
        self._cache[key] = result
        self._timestamps[key] = datetime.now()
    
    def clear(self):
        self._cache.clear()
        self._timestamps.clear()


glci_cache = GLCICache(ttl_seconds=300)  # Cache for 5 minutes


app = FastAPI(
    title="Global Liquidity Tracker API",
    description="API for fetching global liquidity and credit metrics",
    version="0.2.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
fetcher = DataFetcher()
storage = DataStorage()
aggregator = Aggregator(fetcher)
glci_computer = GLCIComputer(fetcher, storage)


class SeriesInfo(BaseModel):
    id: str
    name: str
    source: str
    category: str
    frequency: str
    unit: str


class DataPoint(BaseModel):
    date: str
    value: float


class SeriesResponse(BaseModel):
    id: str
    name: str
    source: str
    unit: str
    data: list[DataPoint]


class IndexResponse(BaseModel):
    id: str
    name: str
    description: str
    data: list[DataPoint]


class SummaryMetric(BaseModel):
    value: float
    change: float
    change_period: str


class GLCIPillar(BaseModel):
    name: str
    value: float
    weight: float
    contribution: float  # Weighted contribution to index


class DataFreshnessItem(BaseModel):
    series_id: str
    pillar: str
    last_date: str
    days_old: int
    is_stale: bool


class GLCIResponse(BaseModel):
    value: float
    zscore: float
    regime: str
    regime_code: int
    date: str
    momentum: float
    prob_regime_change: float
    pillars: list[GLCIPillar]
    data: list[DataPoint]
    pillar_data: dict[str, list[DataPoint]]


class GLCIDetailedResponse(GLCIResponse):
    """Extended response with additional analytics."""
    period_high: float
    period_low: float
    period_mean: float
    regime_distribution: dict[str, int]  # tight/neutral/loose counts
    data_quality: dict[str, dict]  # Quality info per pillar


# Category mapping for frontend
CATEGORY_MAP = {
    "fed_total_assets": "Central Banks",
    "ecb_total_assets": "Central Banks",
    "boj_total_assets": "Central Banks",
    "boe_total_assets": "Central Banks",
    "pboc_total_assets": "Central Banks",
    "fed_treasury_general_account": "Central Banks",
    "fed_reverse_repo": "Central Banks",
    "fed_reserve_balances": "Central Banks",
    "sofr": "Funding Rates",
    "fed_funds_rate": "Funding Rates",
    "euro_short_term_rate": "Funding Rates",
    "us_m2": "Money Supply",
    "eu_m3": "Money Supply",
    "china_m2": "Money Supply",
    "japan_m2": "Money Supply",
    "ted_spread": "Credit Spreads",
    "ice_bofa_us_high_yield_spread": "Credit Spreads",
    "ice_bofa_us_ig_spread": "Credit Spreads",
    "vix": "Volatility",
    "move_index": "Volatility",
    "nfci": "Financial Conditions",
    "us_bank_credit_total": "Bank Credit",
    "us_bank_loans_leases": "Bank Credit",
    "us_consumer_credit": "Consumer Credit",
    "us_commercial_paper": "Commercial Paper",
    "bis_credit_us": "BIS Credit",
    "bis_credit_eu": "BIS Credit",
    "bis_credit_cn": "BIS Credit",
    "bis_credit_jp": "BIS Credit",
    "bis_credit_gap_us": "Credit Gap",
    "bis_credit_gap_eu": "Credit Gap",
    "bis_credit_gap_cn": "Credit Gap",
    "bis_credit_gap_jp": "Credit Gap",
}


@app.get("/")
async def root():
    return {"status": "ok", "service": "Global Liquidity Tracker API", "version": "0.2.0"}


@app.get("/api/series", response_model=list[SeriesInfo])
async def list_series():
    """List all available series."""
    all_series = get_all_series()
    result = []
    
    for series_id, config in all_series.items():
        result.append(SeriesInfo(
            id=series_id,
            name=config.get("description", series_id),
            source=config.get("source", "unknown").upper(),
            category=CATEGORY_MAP.get(series_id, "Other"),
            frequency=config.get("frequency", "unknown"),
            unit=config.get("unit", ""),
        ))
    
    return result


@app.get("/api/series/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: str,
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Fetch data for a specific series."""
    config = get_series_config(series_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Series '{series_id}' not found")
    
    # Default date range: 3 years
    if not start:
        start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        df = fetcher.fetch_series(series_id, start, end)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for '{series_id}'")
        
        data = [
            DataPoint(date=row["date"].strftime("%Y-%m-%d"), value=float(row["value"]))
            for _, row in df.iterrows()
        ]
        
        return SeriesResponse(
            id=series_id,
            name=config.get("description", series_id),
            source=config.get("source", "unknown").upper(),
            unit=config.get("unit", ""),
            data=data,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/series/{series_id}/latest")
async def get_series_latest(series_id: str):
    """Get the latest value for a series."""
    config = get_series_config(series_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Series '{series_id}' not found")
    
    try:
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        
        df = fetcher.fetch_series(series_id, start, end)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for '{series_id}'")
        
        latest = df.iloc[-1]
        
        # Calculate change from 7 days ago if available
        change = 0.0
        if len(df) > 7:
            prev = df.iloc[-8]["value"]
            change = ((latest["value"] - prev) / prev) * 100 if prev != 0 else 0
        
        return {
            "id": series_id,
            "date": latest["date"].strftime("%Y-%m-%d"),
            "value": float(latest["value"]),
            "change": round(change, 2),
            "unit": config.get("unit", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/indices", response_model=list[dict])
async def list_indices():
    """List all available composite indices."""
    all_indices = get_all_indices()
    result = []
    
    for index_id, config in all_indices.items():
        result.append({
            "id": index_id,
            "name": index_id.replace("_", " ").title(),
            "description": config.get("description", ""),
            "frequency": config.get("frequency", ""),
            "components": len(config.get("components", config.get("pillars", {}))),
        })
    
    return result


@app.get("/api/indices/{index_id}", response_model=IndexResponse)
async def get_index(
    index_id: str,
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Compute and return a composite index."""
    config = get_index_config(index_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Index '{index_id}' not found")
    
    if not start:
        start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        df = aggregator.compute_index(index_id, start, end)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data computed for '{index_id}'")
        
        data = [
            DataPoint(date=row["date"].strftime("%Y-%m-%d"), value=float(row["value"]))
            for _, row in df.iterrows()
        ]
        
        return IndexResponse(
            id=index_id,
            name=index_id.replace("_", " ").title(),
            description=config.get("description", ""),
            data=data,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glci", response_model=GLCIResponse)
async def get_glci(
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get the Global Liquidity & Credit Index with pillar breakdown."""
    if not start:
        start = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Check cache first
        result = glci_cache.get(start, end)
        if result is None:
            result = glci_computer.compute(start, end, save_output=False, verbose=False)
            glci_cache.set(start, end, result)
        
        glci_df = result.glci
        pillars_df = result.pillars
        
        if glci_df.empty:
            raise HTTPException(status_code=404, detail="No GLCI data computed")
        
        # Get latest values
        latest = glci_df.iloc[-1]
        latest_pillars = pillars_df.iloc[-1]
        
        # Build pillar info with contributions
        pillar_weights = result.weights.get("pillar_weights", {})
        pillar_list = []
        for pillar_name in ["liquidity", "credit", "stress"]:
            if pillar_name in pillars_df.columns:
                value = float(latest_pillars[pillar_name])
                weight = pillar_weights.get(pillar_name, 0)
                pillar_list.append(GLCIPillar(
                    name=pillar_name,
                    value=value,
                    weight=weight,
                    contribution=value * weight
                ))
        
        # Build time series data
        data = [
            DataPoint(date=row["date"].strftime("%Y-%m-%d"), value=float(row["value"]))
            for _, row in glci_df.iterrows()
        ]
        
        # Build pillar time series
        pillar_data = {}
        for pillar_name in ["liquidity", "credit", "stress"]:
            if pillar_name in pillars_df.columns:
                pillar_data[pillar_name] = [
                    DataPoint(date=row["date"].strftime("%Y-%m-%d"), value=float(row[pillar_name]))
                    for _, row in pillars_df.iterrows()
                    if not (row[pillar_name] != row[pillar_name])  # Skip NaN
                ]
        
        # Map regime
        regime_map = {-1: "tight", 0: "neutral", 1: "loose"}
        regime_code = int(latest["regime"])
        
        return GLCIResponse(
            value=float(latest["value"]),
            zscore=float(latest["zscore"]),
            regime=regime_map.get(regime_code, "unknown"),
            regime_code=regime_code,
            date=latest["date"].strftime("%Y-%m-%d"),
            momentum=float(latest.get("momentum", 0)) if latest.get("momentum") == latest.get("momentum") else 0,
            prob_regime_change=float(latest.get("prob_regime_change", 0)) if latest.get("prob_regime_change") == latest.get("prob_regime_change") else 0,
            pillars=pillar_list,
            data=data,
            pillar_data=pillar_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glci/latest")
async def get_glci_latest():
    """Get the latest GLCI value and regime (from cached data if available)."""
    try:
        # Try to load from storage first
        latest = glci_computer.get_latest()
        if latest:
            return latest
        
        # Otherwise compute fresh
        start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
        result = glci_computer.compute(start, save_output=False, verbose=False)
        
        glci_df = result.glci
        if glci_df.empty:
            raise HTTPException(status_code=404, detail="No GLCI data")
        
        latest_row = glci_df.iloc[-1]
        regime_map = {-1: "tight", 0: "neutral", 1: "loose"}
        
        return {
            "date": latest_row["date"].strftime("%Y-%m-%d"),
            "value": float(latest_row["value"]),
            "zscore": float(latest_row["zscore"]),
            "regime": int(latest_row["regime"]),
            "regime_label": regime_map.get(int(latest_row["regime"]), "unknown"),
            "momentum": float(latest_row.get("momentum", 0)) if latest_row.get("momentum") == latest_row.get("momentum") else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glci/pillars")
async def get_glci_pillars():
    """Get the latest pillar breakdown with detailed info."""
    try:
        breakdown = glci_computer.get_pillar_breakdown()
        if breakdown:
            return breakdown
        
        # Compute fresh if not cached
        start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
        result = glci_computer.compute(start, save_output=False, verbose=False)
        
        if result.pillars.empty:
            raise HTTPException(status_code=404, detail="No pillar data")
        
        latest = result.pillars.iloc[-1]
        pillar_weights = result.weights.get("pillar_weights", {})
        
        return {
            "date": str(latest["date"]),
            "pillars": {
                col: {
                    "value": float(latest[col]),
                    "weight": pillar_weights.get(col, 0),
                    "contribution": float(latest[col]) * pillar_weights.get(col, 0)
                }
                for col in result.pillars.columns if col != "date"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glci/freshness", response_model=list[DataFreshnessItem])
async def get_glci_freshness():
    """Get data freshness information for all GLCI components."""
    try:
        freshness = glci_computer.get_data_freshness()
        
        return [
            DataFreshnessItem(
                series_id=series_id,
                pillar=info["pillar"],
                last_date=info["last_date"],
                days_old=info["days_old"],
                is_stale=info["is_stale"]
            )
            for series_id, info in freshness.items()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glci/regime-history")
async def get_regime_history(
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get historical regime data for timeline visualization."""
    if not start:
        start = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Check cache first
        result = glci_cache.get(start, end)
        if result is None:
            result = glci_computer.compute(start, end, save_output=False, verbose=False)
            glci_cache.set(start, end, result)
        
        regimes_df = result.regimes
        
        # Build regime periods
        periods = []
        current_regime = None
        period_start = None
        
        for _, row in regimes_df.iterrows():
            regime = row["regime_label"]
            date = row["date"]
            
            if regime != current_regime:
                if current_regime is not None:
                    periods.append({
                        "regime": current_regime,
                        "start": str(period_start)[:10],
                        "end": str(date)[:10]
                    })
                current_regime = regime
                period_start = date
        
        # Add final period
        if current_regime is not None:
            periods.append({
                "regime": current_regime,
                "start": str(period_start)[:10],
                "end": str(regimes_df["date"].iloc[-1])[:10]
            })
        
        # Calculate stats
        regime_counts = regimes_df["regime_label"].value_counts().to_dict()
        
        return {
            "periods": periods,
            "counts": regime_counts,
            "current": current_regime
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

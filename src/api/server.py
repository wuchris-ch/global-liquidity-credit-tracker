"""FastAPI server exposing liquidity data."""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import get_all_series, get_all_indices, get_series_config, get_index_config
from ..etl import DataFetcher, DataStorage
from ..indicators import Aggregator


app = FastAPI(
    title="Global Liquidity Tracker API",
    description="API for fetching global liquidity and credit metrics",
    version="0.1.0",
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


# Category mapping for frontend
CATEGORY_MAP = {
    "fed_total_assets": "Central Banks",
    "ecb_total_assets": "Central Banks",
    "boj_total_assets": "Central Banks",
    "fed_treasury_general_account": "Central Banks",
    "fed_reverse_repo": "Central Banks",
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
}


@app.get("/")
async def root():
    return {"status": "ok", "service": "Global Liquidity Tracker API"}


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
        # Fetch last 30 days to get latest
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
            "components": len(config.get("components", [])),
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
    
    # Default date range: 3 years
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

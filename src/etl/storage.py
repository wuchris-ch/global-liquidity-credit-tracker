"""Data storage layer for raw and curated data."""
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

from ..config import RAW_DATA_PATH, CURATED_DATA_PATH


class DataStorage:
    """Handles storage and retrieval of time series data."""
    
    def __init__(self, raw_path: Path | None = None, curated_path: Path | None = None):
        self.raw_path = raw_path or RAW_DATA_PATH
        self.curated_path = curated_path or CURATED_DATA_PATH
        
        # Ensure directories exist
        self.raw_path.mkdir(parents=True, exist_ok=True)
        self.curated_path.mkdir(parents=True, exist_ok=True)
    
    # ==================
    # Raw Data Operations
    # ==================
    
    def save_raw(self, df: pd.DataFrame, source: str, series_id: str) -> Path:
        """Save raw data to parquet file.
        
        Args:
            df: DataFrame with standardized columns
            source: Data source name (fred, bis, etc.)
            series_id: Series identifier
            
        Returns:
            Path to saved file
        """
        source_path = self.raw_path / source
        source_path.mkdir(parents=True, exist_ok=True)
        
        # Clean series_id for filename
        clean_id = series_id.replace(":", "_").replace("/", "_")
        file_path = source_path / f"{clean_id}.parquet"
        
        df.to_parquet(file_path, index=False)
        return file_path
    
    def load_raw(self, source: str, series_id: str) -> pd.DataFrame | None:
        """Load raw data from parquet file."""
        clean_id = series_id.replace(":", "_").replace("/", "_")
        file_path = self.raw_path / source / f"{clean_id}.parquet"
        
        if file_path.exists():
            return pd.read_parquet(file_path)
        return None
    
    def append_raw(self, df: pd.DataFrame, source: str, series_id: str) -> Path:
        """Append new data to existing raw file, avoiding duplicates."""
        existing = self.load_raw(source, series_id)
        
        if existing is not None:
            # Combine and deduplicate by date
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date"], keep="last")
            combined = combined.sort_values("date")
            df = combined
        
        return self.save_raw(df, source, series_id)
    
    def list_raw_series(self, source: str | None = None) -> list[dict]:
        """List all available raw series."""
        series_list = []
        
        sources = [source] if source else [d.name for d in self.raw_path.iterdir() if d.is_dir()]
        
        for src in sources:
            src_path = self.raw_path / src
            if src_path.exists():
                for file in src_path.glob("*.parquet"):
                    series_list.append({
                        "source": src,
                        "series_id": file.stem,
                        "path": str(file),
                        "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                    })
        
        return series_list
    
    # ==================
    # Curated Data Operations
    # ==================
    
    def save_curated(self, df: pd.DataFrame, category: str, name: str,
                     metadata: dict | None = None) -> Path:
        """Save curated/computed data.
        
        Args:
            df: DataFrame with computed index/indicator
            category: Category folder (e.g., 'indices', 'aggregates')
            name: Name of the dataset
            metadata: Optional metadata dict to save alongside
            
        Returns:
            Path to saved file
        """
        category_path = self.curated_path / category
        category_path.mkdir(parents=True, exist_ok=True)
        
        file_path = category_path / f"{name}.parquet"
        df.to_parquet(file_path, index=False)
        
        # Save metadata if provided
        if metadata:
            meta_path = category_path / f"{name}_meta.json"
            metadata["saved_at"] = datetime.utcnow().isoformat()
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)
        
        return file_path
    
    def load_curated(self, category: str, name: str) -> pd.DataFrame | None:
        """Load curated data."""
        file_path = self.curated_path / category / f"{name}.parquet"
        
        if file_path.exists():
            return pd.read_parquet(file_path)
        return None
    
    def load_curated_metadata(self, category: str, name: str) -> dict | None:
        """Load metadata for curated dataset."""
        meta_path = self.curated_path / category / f"{name}_meta.json"
        
        if meta_path.exists():
            with open(meta_path, "r") as f:
                return json.load(f)
        return None
    
    def list_curated(self, category: str | None = None) -> list[dict]:
        """List all curated datasets."""
        datasets = []
        
        categories = [category] if category else [d.name for d in self.curated_path.iterdir() if d.is_dir()]
        
        for cat in categories:
            cat_path = self.curated_path / cat
            if cat_path.exists():
                for file in cat_path.glob("*.parquet"):
                    datasets.append({
                        "category": cat,
                        "name": file.stem,
                        "path": str(file),
                        "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                    })
        
        return datasets
    
    # ==================
    # Utility Methods
    # ==================
    
    def get_latest_date(self, source: str, series_id: str) -> pd.Timestamp | None:
        """Get the latest date in a raw series."""
        df = self.load_raw(source, series_id)
        if df is not None and not df.empty:
            return pd.Timestamp(df["date"].max())
        return None
    
    def get_date_range(self, source: str, series_id: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """Get the date range of a raw series."""
        df = self.load_raw(source, series_id)
        if df is not None and not df.empty:
            return (pd.Timestamp(df["date"].min()), pd.Timestamp(df["date"].max()))
        return None

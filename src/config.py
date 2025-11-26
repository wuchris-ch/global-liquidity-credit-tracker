"""Configuration loader for series and indices."""
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "series.yml"
DATA_PATH = Path(os.getenv("DATA_PATH", PROJECT_ROOT / "data"))

# API Keys
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Ensure data directories exist
RAW_DATA_PATH = DATA_PATH / "raw"
CURATED_DATA_PATH = DATA_PATH / "curated"
RAW_DATA_PATH.mkdir(parents=True, exist_ok=True)
CURATED_DATA_PATH.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load the series configuration from YAML."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_series_config(series_id: str) -> dict:
    """Get configuration for a specific series."""
    config = load_config()
    return config.get("series", {}).get(series_id, {})


def get_index_config(index_id: str) -> dict:
    """Get configuration for a specific composite index."""
    config = load_config()
    return config.get("indices", {}).get(index_id, {})


def get_all_series() -> dict:
    """Get all series configurations."""
    return load_config().get("series", {})


def get_all_indices() -> dict:
    """Get all index configurations."""
    return load_config().get("indices", {})


def get_country_weights() -> dict:
    """Get country GDP weights for weighted indices."""
    return load_config().get("country_weights", {})

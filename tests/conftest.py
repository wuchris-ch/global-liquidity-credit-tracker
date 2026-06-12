"""Shared fixtures for the calculation test suite.

All tests are offline: they use synthetic data and stub fetcher/storage
objects so no network access or API keys are required.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class StubFetcher:
    """In-memory stand-in for DataFetcher; serves pre-built DataFrames."""

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def fetch_series(self, series_id, start_date=None, end_date=None):
        if series_id not in self.frames:
            raise ValueError(f"Series '{series_id}' not stubbed")
        df = self.frames[series_id].copy()
        if start_date:
            df = df[df["date"] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df["date"] <= pd.Timestamp(end_date)]
        return df.reset_index(drop=True)

    def fetch_multiple(self, series_ids, start_date=None, end_date=None):
        out = {}
        for sid in series_ids:
            try:
                out[sid] = self.fetch_series(sid, start_date, end_date)
            except ValueError:
                pass
        return out


class StubStorage:
    """In-memory stand-in for DataStorage."""

    def __init__(self, curated: dict[tuple[str, str], pd.DataFrame] | None = None) -> None:
        self.curated = dict(curated or {})
        self.raw: dict[tuple[str, str], pd.DataFrame] = {}

    def load_curated(self, category, name):
        df = self.curated.get((category, name))
        return df.copy() if df is not None else None

    def save_curated(self, df, category, name, metadata=None):
        self.curated[(category, name)] = df.copy()

    def load_raw(self, source, series_id):
        df = self.raw.get((source, series_id))
        return df.copy() if df is not None else None

    def save_raw(self, df, source, series_id):
        self.raw[(source, series_id)] = df.copy()

    def get_latest_date(self, source, series_id):
        df = self.raw.get((source, series_id))
        if df is not None and not df.empty:
            return pd.Timestamp(df["date"].max())
        return None


@pytest.fixture
def stub_storage():
    return StubStorage()


def make_series(dates: pd.DatetimeIndex, values, source: str = "fred") -> pd.DataFrame:
    """Build a DataFrame in the fetcher's standardized shape."""
    return pd.DataFrame({
        "date": dates,
        "value": np.asarray(values, dtype=float),
        "source": source,
    })


@pytest.fixture
def weekly_dates():
    """Five years of weekly (Friday) dates."""
    return pd.date_range("2019-01-04", periods=260, freq="W-FRI")


@pytest.fixture
def daily_dates():
    """Three years of business days."""
    return pd.date_range("2020-01-01", periods=756, freq="B")

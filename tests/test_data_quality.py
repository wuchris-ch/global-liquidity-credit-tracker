"""Tests for shared GLCI trust and freshness semantics."""

import pandas as pd

from src.api.server import app
from src.config import get_all_series, get_index_config
from src.data_quality import build_glci_trust_payload, freshness_state
from src.etl.storage import DataStorage


def test_frequency_aware_freshness_is_shared():
    now = pd.Timestamp("2026-07-10T12:00:00Z")

    daily_days, daily_stale = freshness_state("2026-06-29", "daily", now=now)
    quarterly_days, quarterly_stale = freshness_state(
        "2026-04-01", "quarterly", now=now
    )

    assert daily_days == 11
    assert daily_stale is True
    assert quarterly_days == 100
    assert quarterly_stale is False


def test_trust_coverage_counts_fitted_components_and_reports_exclusions(tmp_path):
    storage = DataStorage(
        raw_path=tmp_path / "raw",
        curated_path=tmp_path / "curated",
    )
    liquidity_components = [
        component["series"]
        for component in get_index_config("global_liquidity_credit_index")["pillars"][
            "liquidity"
        ]["components"]
    ]
    used = liquidity_components[0]
    excluded = liquidity_components[1]
    configured_pillars = get_index_config("global_liquidity_credit_index")["pillars"]
    failed_components = {
        component["series"]
        for pillar_name in ("credit", "stress")
        for component in configured_pillars[pillar_name]["components"]
    }
    sofr_config = get_all_series()["sofr"]
    storage.save_raw(
        pd.DataFrame({"date": [pd.Timestamp("2026-07-10")], "value": [5.0]}),
        sofr_config["source"],
        "sofr",
    )
    storage.save_curated(
        pd.DataFrame({"date": [pd.Timestamp("2026-07-03")], "value": [101.0]}),
        "indices",
        "glci",
        metadata={
            "pillar_stats": {
                "liquidity": {
                    "method": "pca",
                    "n_variables": 1,
                    "data_quality": {
                        "total_series": len(liquidity_components),
                        "available_series": 2,
                        "loaded_series": 1,
                        "used_series": [used],
                        "excluded_series": [excluded],
                        "missing_series": liquidity_components[2:],
                        "stale_series": [],
                    },
                }
            }
        },
    )

    payload = build_glci_trust_payload(storage, get_all_series())

    assert payload["data_quality"]["loaded_components"] == 1
    assert payload["data_quality"]["excluded_components"] == [excluded]
    assert payload["data_quality"]["failed_pillars"] == ["credit", "stress"]
    assert failed_components <= set(payload["data_quality"]["missing_components"])
    assert "sofr" in payload["data_quality"]["missing_components"]
    assert set(
        payload["pillar_stats"]["stress"]["data_quality"]["missing_series"]
    ) == {
        component["series"] for component in configured_pillars["stress"]["components"]
    }
    assert payload["pillar_stats"]["liquidity"]["data_quality"]["used_series"] == [used]


def test_live_api_registers_glci_trust_route():
    assert "/api/glci/trust" in {route.path for route in app.routes}

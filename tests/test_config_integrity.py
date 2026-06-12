"""Configuration integrity checks for config/series.yml.

These catch the most common way the pipeline breaks silently: an index
referencing a series that was renamed or removed.
"""
import pytest

from src.config import get_all_indices, get_all_series, get_index_config
from src.indicators.risk_metrics import ASSET_CONFIG

VALID_SOURCES = {"fred", "bis", "worldbank", "nyfed", "yfinance"}
VALID_FREQUENCIES = {"daily", "weekly", "monthly", "quarterly", "annual"}


@pytest.fixture(scope="module")
def all_series():
    return get_all_series()


@pytest.fixture(scope="module")
def all_indices():
    return get_all_indices()


class TestSeriesDefinitions:
    def test_every_series_has_required_fields(self, all_series):
        for sid, cfg in all_series.items():
            assert cfg.get("source") in VALID_SOURCES, f"{sid}: bad source"
            assert cfg.get("source_id"), f"{sid}: missing source_id"
            assert cfg.get("frequency") in VALID_FREQUENCIES, f"{sid}: bad frequency"
            assert cfg.get("description"), f"{sid}: missing description"


class TestIndexDefinitions:
    def test_index_components_reference_defined_series(self, all_series, all_indices):
        for index_id, cfg in all_indices.items():
            for comp in cfg.get("components", []):
                sid = comp["series"]
                assert sid in all_series, (
                    f"Index '{index_id}' references undefined series '{sid}'"
                )

    def test_glci_pillar_components_reference_defined_series(self, all_series):
        cfg = get_index_config("global_liquidity_credit_index")
        assert cfg, "GLCI index missing from config"
        for pillar, pillar_cfg in cfg["pillars"].items():
            for comp in pillar_cfg.get("components", []):
                sid = comp["series"]
                assert sid in all_series, (
                    f"GLCI pillar '{pillar}' references undefined series '{sid}'"
                )

    def test_glci_pillar_weights_sum_to_one(self):
        cfg = get_index_config("global_liquidity_credit_index")
        weights = cfg.get("pillar_weights", {})
        assert weights, "GLCI pillar_weights missing"
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_glci_pillar_weights_match_pillar_definitions(self):
        cfg = get_index_config("global_liquidity_credit_index")
        assert set(cfg["pillar_weights"].keys()) == set(cfg["pillars"].keys())

    def test_stress_pillar_is_inverted(self):
        cfg = get_index_config("global_liquidity_credit_index")
        assert cfg["pillars"]["stress"]["sign"] == -1

    def test_fed_net_liquidity_unit_conversion(self):
        """RRP is reported in billions; the index converts it to millions.

        This weight is load-bearing: without the 1000x conversion the
        net liquidity figure is off by ~half a trillion dollars.
        """
        cfg = get_index_config("fed_net_liquidity")
        rrp = next(c for c in cfg["components"] if c["series"] == "fed_reverse_repo")
        assert rrp["operation"] == "subtract"
        assert rrp["weight"] == 1000.0


class TestRiskAssetConfig:
    def test_risk_assets_are_defined_series(self, all_series):
        for asset_id in ASSET_CONFIG:
            assert asset_id in all_series, (
                f"Risk asset '{asset_id}' not defined in series.yml"
            )

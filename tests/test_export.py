"""Tests for the static JSON export layer (scripts/export_to_json.py)."""
import json
from pathlib import Path

import pandas as pd
import pytest

import scripts.export_to_json as export_module
from scripts.export_to_json import (
    REQUIRED_PRODUCTION_EXPORT_PATHS,
    export_glci,
    export_glci_freshness,
    export_glci_trust,
    export_indices_list,
    fmt_date,
    validate_required_exports,
    write_json,
)
from src.config import get_all_indices, get_all_series, get_index_config
from src.data_quality import _snapshot_summary
from src.etl.storage import DataStorage


class TestFmtDate:
    def test_timestamp(self):
        assert fmt_date(pd.Timestamp("2024-03-15 13:45:00")) == "2024-03-15"

    def test_string_passthrough_truncates(self):
        assert fmt_date("2024-03-15T13:45:00") == "2024-03-15"

    def test_nan_becomes_empty(self):
        assert fmt_date(float("nan")) == ""


class TestWriteJson:
    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "a" / "b" / "index.json"
        write_json(target, {"x": 1})
        assert json.loads(target.read_text()) == {"x": 1}

    def test_compatibility_index_id_uses_current_display_name(self, tmp_path):
        export_indices_list(get_all_indices(), tmp_path)
        payload = json.loads((tmp_path / "api" / "indices" / "index.json").read_text())
        credit_stress = next(
            item for item in payload if item["id"] == "usd_funding_stress"
        )
        assert credit_stress["name"] == "USD Credit Stress"


class TestExportGlciRegimeHistory:
    def test_warmup_is_omitted_from_regime_periods(
        self,
        tmp_path,
        monkeypatch,
    ):
        curated = tmp_path / "curated"
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=curated,
        )
        dates = pd.date_range("2026-01-02", periods=5, freq="W-FRI")
        storage.save_curated(
            pd.DataFrame(
                {
                    "date": dates,
                    "value": [98.0, 97.0, 96.0, 101.0, 102.0],
                    "zscore": [float("nan"), -1.2, -1.1, 1.2, 1.1],
                    "regime": [float("nan"), -1.0, -1.0, 1.0, 1.0],
                    "momentum": [float("nan"), -1.0, -1.0, 1.0, 1.0],
                }
            ),
            "indices",
            "glci",
        )
        storage.save_curated(
            pd.DataFrame(
                {
                    "date": dates,
                    "liquidity": range(5),
                    "credit": range(5),
                    "stress": range(5),
                }
            ),
            "indices",
            "glci_pillars",
        )
        weights_path = curated / "indices" / "glci_weights.json"
        weights_path.write_text(
            json.dumps(
                {
                    "pillar_weights": {
                        "liquidity": 0.40,
                        "credit": 0.35,
                        "stress": 0.25,
                    }
                }
            )
        )
        monkeypatch.setattr(export_module, "CURATED_DATA_PATH", curated)

        assert export_glci(storage, tmp_path / "export") is True

        payload = json.loads(
            (
                tmp_path
                / "export"
                / "api"
                / "glci"
                / "regime-history"
                / "index.json"
            ).read_text()
        )
        assert len(payload["periods"]) == 2
        assert payload["periods"][0]["regime"] == "tight"
        assert payload["periods"][0]["start"] == "2026-01-09"
        assert payload["periods"][1]["regime"] == "loose"
        assert payload["current"] == "loose"


class TestValidateRequiredExports:
    def test_empty_directory_reports_all_paths_missing(self, tmp_path):
        errors = validate_required_exports(tmp_path)
        assert len(errors) == len(REQUIRED_PRODUCTION_EXPORT_PATHS)
        assert all(e.startswith("missing") for e in errors)

    def test_required_series_exist_in_config(self):
        """Every required export path must reference a configured series."""
        series_ids = set(get_all_series().keys())
        for rel_path in REQUIRED_PRODUCTION_EXPORT_PATHS:
            parts = rel_path.split("/")
            if parts[1] == "series" and len(parts) > 3:
                assert parts[2] in series_ids, (
                    f"Required export references unknown series '{parts[2]}'"
                )

    def test_invalid_json_is_reported(self, tmp_path):
        bad = tmp_path / REQUIRED_PRODUCTION_EXPORT_PATHS[0]
        bad.parent.mkdir(parents=True)
        bad.write_text("{not valid json")
        errors = validate_required_exports(tmp_path)
        assert any("invalid JSON" in e for e in errors)

    def test_empty_series_data_is_reported(self, tmp_path):
        path = tmp_path / "api" / "series" / "fed_total_assets" / "index.json"
        write_json(path, {"id": "fed_total_assets", "data": []})
        errors = validate_required_exports(tmp_path)
        assert any(
            "empty data in api/series/fed_total_assets/index.json" in e for e in errors
        )

    def test_incomplete_latest_payload_is_reported(self, tmp_path):
        path = tmp_path / "api" / "series" / "sofr" / "latest" / "index.json"
        write_json(path, {"id": "sofr"})  # missing date/value
        errors = validate_required_exports(tmp_path)
        assert any("incomplete latest payload" in e for e in errors)

    def test_trust_payload_cannot_claim_point_in_time_history(self, tmp_path):
        path = tmp_path / "api" / "glci" / "trust" / "index.json"
        write_json(
            path,
            {
                "as_of": "2026-07-10",
                "historical_mode": "reconstructed_current_vintage",
                "point_in_time": True,
                "frequency": "W-FRI",
                "snapshots": {},
                "data_quality": {},
                "pillar_stats": {},
            },
        )
        errors = validate_required_exports(tmp_path)
        assert any("incorrect point-in-time claim" in error for error in errors)

    def test_empty_flows_destinations_reported(self, tmp_path):
        path = tmp_path / "api" / "flows" / "index.json"
        write_json(path, {"as_of": "2026-01-02", "destinations": []})
        errors = validate_required_exports(tmp_path)
        assert any("empty destinations in api/flows/index.json" in e for e in errors)

    def test_valid_local_export_passes(self):
        """If a full local export exists (after a pipeline run), it must validate.

        Skipped when no local export has been generated (data/ is gitignored).
        """
        export_dir = Path(__file__).resolve().parent.parent / "data" / "export" / "latest"
        if not all(
            (export_dir / rel_path).is_file()
            for rel_path in REQUIRED_PRODUCTION_EXPORT_PATHS
        ):
            pytest.skip("no current full local export (run the pipeline to generate one)")
        assert validate_required_exports(export_dir) == []


class TestExportGlciTrust:
    def test_snapshot_summary_detects_a_regime_change_that_later_reverts(
        self, tmp_path
    ):
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=tmp_path / "curated",
        )
        for computed_at, regime in (
            ("2026-07-10T12:00:00Z", 0),
            ("2026-07-10T15:00:00Z", 1),
            ("2026-07-10T18:00:00Z", 0),
        ):
            storage.append_signal_snapshot(
                {
                    "signal_date": "2026-07-10",
                    "computed_at": computed_at,
                    "glci": 101.0,
                    "regime": regime,
                }
            )

        revision = _snapshot_summary(storage)["latest_signal_revision"]
        assert revision["first_regime"] == "neutral"
        assert revision["latest_regime"] == "neutral"
        assert revision["regime_changed"] is True

    def test_default_payload_has_stable_honest_schema(self, tmp_path):
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=tmp_path / "curated",
        )
        output_dir = tmp_path / "export"

        export_glci_trust(storage, get_all_series(), output_dir)

        path = output_dir / "api" / "glci" / "trust" / "index.json"
        payload = json.loads(path.read_text())
        assert set(payload) == {
            "as_of",
            "historical_mode",
            "point_in_time",
            "frequency",
            "snapshots",
            "data_quality",
            "pillar_stats",
        }
        assert payload["as_of"] is None
        assert payload["historical_mode"] == "reconstructed_current_vintage"
        assert payload["point_in_time"] is False
        assert payload["frequency"] == "W-FRI"
        assert payload["snapshots"] == {
            "count": 0,
            "unique_signal_dates": 0,
            "duplicate_vintages": 0,
            "first_signal_date": None,
            "latest_signal_date": None,
            "first_computed_at": None,
            "last_computed_at": None,
            "latest_signal_revision": None,
        }

        configured_pillars = get_index_config(
            "global_liquidity_credit_index"
        )["pillars"]
        expected_components = {
            component["series"]
            for pillar in configured_pillars.values()
            for component in pillar["components"]
        }
        quality = payload["data_quality"]
        assert quality["loaded_components"] == 0
        assert quality["total_components"] == len(expected_components)
        assert set(quality["missing_components"]) == expected_components
        assert quality["stale_components"] == []
        assert set(payload["pillar_stats"]) == set(configured_pillars)

    def test_model_quality_is_authoritative_when_raw_cache_is_absent(self, tmp_path):
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=tmp_path / "curated",
        )
        configured_pillars = get_index_config(
            "global_liquidity_credit_index"
        )["pillars"]
        pillar_stats = {}
        for pillar_name, pillar in configured_pillars.items():
            component_count = len(pillar["components"])
            pillar_stats[pillar_name] = {
                "data_quality": {
                    "total_series": component_count,
                    "loaded_series": component_count,
                    "missing_series": [],
                    "stale_series": [],
                }
            }
        storage.save_curated(
            pd.DataFrame(
                {"date": [pd.Timestamp("2026-07-10")], "value": [101.0]}
            ),
            "indices",
            "glci",
            metadata={"pillar_stats": pillar_stats},
        )

        output_dir = tmp_path / "export"
        export_glci_trust(storage, get_all_series(), output_dir)
        payload = json.loads(
            (
                output_dir / "api" / "glci" / "trust" / "index.json"
            ).read_text()
        )

        quality = payload["data_quality"]
        assert quality["loaded_components"] == quality["total_components"]
        assert quality["missing_components"] == []

    def test_staleness_allowance_respects_source_frequency(self, tmp_path):
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=tmp_path / "curated",
        )
        today = pd.Timestamp.now(tz="UTC").normalize()
        storage.save_raw(
            pd.DataFrame(
                {"date": [today - pd.Timedelta(days=11)], "value": [1.0]}
            ),
            "fred",
            "fed_reverse_repo",
        )
        storage.save_raw(
            pd.DataFrame(
                {"date": [today - pd.Timedelta(days=40)], "value": [1.0]}
            ),
            "fred",
            "boj_total_assets",
        )

        output_dir = tmp_path / "export"
        export_glci_trust(storage, get_all_series(), output_dir)
        export_glci_freshness(storage, get_all_series(), output_dir)
        payload = json.loads(
            (
                output_dir / "api" / "glci" / "trust" / "index.json"
            ).read_text()
        )

        stale = payload["data_quality"]["stale_components"]
        assert "fed_reverse_repo" in stale
        assert "boj_total_assets" not in stale
        liquidity_quality = payload["pillar_stats"]["liquidity"]["data_quality"]
        assert "fed_reverse_repo" in liquidity_quality["stale_series"]
        assert "boj_total_assets" not in liquidity_quality["stale_series"]

        freshness = json.loads(
            (
                output_dir / "api" / "glci" / "freshness" / "index.json"
            ).read_text()
        )
        freshness_by_id = {item["series_id"]: item for item in freshness}
        assert freshness_by_id["fed_reverse_repo"]["is_stale"] is True
        assert freshness_by_id["boj_total_assets"]["is_stale"] is False

    def test_snapshot_summary_and_as_of_are_exported(self, tmp_path):
        storage = DataStorage(
            raw_path=tmp_path / "raw",
            curated_path=tmp_path / "curated",
        )
        storage.save_curated(
            pd.DataFrame(
                {
                    "date": [pd.Timestamp("2026-07-10")],
                    "value": [101.0],
                }
            ),
            "indices",
            "glci",
        )
        base_snapshot = {
            "signal_date": "2026-07-10",
            "historical_mode": "reconstructed_current_vintage",
            "point_in_time": False,
            "frequency": "W-FRI",
            "glci": 101.0,
            "zscore": 0.3,
            "regime": 0,
        }
        storage.append_signal_snapshot(
            {**base_snapshot, "computed_at": "2026-07-10T12:00:00Z"}
        )
        storage.append_signal_snapshot(
            {
                **base_snapshot,
                "computed_at": "2026-07-10T18:00:00Z",
                "glci": 102.0,
                "zscore": 0.5,
                "regime": 1,
            }
        )

        output_dir = tmp_path / "export"
        export_glci_trust(storage, get_all_series(), output_dir)
        payload = json.loads(
            (
                output_dir / "api" / "glci" / "trust" / "index.json"
            ).read_text()
        )

        assert payload["as_of"] == "2026-07-10"
        assert payload["snapshots"] == {
            "count": 2,
            "unique_signal_dates": 1,
            "duplicate_vintages": 1,
            "first_signal_date": "2026-07-10",
            "latest_signal_date": "2026-07-10",
            "first_computed_at": "2026-07-10T12:00:00Z",
            "last_computed_at": "2026-07-10T18:00:00Z",
            "latest_signal_revision": {
                "vintage_count": 2,
                "first_glci": 101,
                "latest_glci": 102,
                "glci_change": 1,
                "glci_min": 101,
                "glci_max": 102,
                "first_zscore": 0.3,
                "latest_zscore": 0.5,
                "zscore_change": 0.2,
                "first_regime": "neutral",
                "latest_regime": "loose",
                "regime_changed": True,
            },
        }

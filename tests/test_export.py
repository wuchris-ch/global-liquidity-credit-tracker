"""Tests for the static JSON export layer (scripts/export_to_json.py)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_to_json import (
    REQUIRED_PRODUCTION_EXPORT_PATHS,
    fmt_date,
    validate_required_exports,
    write_json,
)
from src.config import get_all_series


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
        if not (export_dir / "api" / "series" / "fed_total_assets" / "index.json").is_file():
            pytest.skip("no full local export present (run the pipeline to generate one)")
        assert validate_required_exports(export_dir) == []

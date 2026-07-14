"""Tests for append-only signal-vintage storage."""

import pytest

from src.etl.storage import DataStorage


def _storage(tmp_path) -> DataStorage:
    return DataStorage(
        raw_path=tmp_path / "raw",
        curated_path=tmp_path / "curated",
    )


def _snapshot(computed_at: str, glci: float) -> dict:
    return {
        "computed_at": computed_at,
        "signal_date": "2026-07-10",
        "historical_mode": "reconstructed_current_vintage",
        "point_in_time": False,
        "frequency": "W-FRI",
        "glci": glci,
        "zscore": 0.4,
        "regime": 0,
        "momentum": 0.2,
        "pillar_liquidity": 1.1,
    }


def test_signal_snapshots_retain_two_vintages_for_one_signal_date(tmp_path):
    storage = _storage(tmp_path)

    storage.append_signal_snapshot(_snapshot("2026-07-10T12:00:00Z", 101.0))
    # A new process loading the restored parquet must extend, not replace, it.
    storage = _storage(tmp_path)
    storage.append_signal_snapshot(_snapshot("2026-07-10T18:00:00Z", 102.0))

    saved = storage.load_curated("indices", "glci_vintages")
    assert saved is not None
    assert len(saved) == 2
    assert saved["signal_date"].tolist() == ["2026-07-10", "2026-07-10"]
    assert saved["glci"].tolist() == [101.0, 102.0]


def test_signal_snapshot_exact_identity_is_idempotent_and_immutable(tmp_path):
    storage = _storage(tmp_path)
    original = _snapshot("2026-07-10T12:00:00Z", 101.0)

    storage.append_signal_snapshot(original)
    storage.append_signal_snapshot(original)
    revised_same_identity = {**original, "glci": 999.0}
    storage.append_signal_snapshot(revised_same_identity)

    saved = storage.load_curated("indices", "glci_vintages")
    assert saved is not None
    assert len(saved) == 1
    assert saved.iloc[0]["glci"] == 101.0


@pytest.mark.parametrize(
    ("computed_at", "signal_date", "message"),
    [
        ("not-a-date", "2026-07-10", "unparseable"),
        ("2026-07-11T12:00:00Z", "not-a-date", "unparseable"),
        ("2026-07-09T23:59:00Z", "2026-07-10", "cannot precede"),
    ],
)
def test_signal_snapshot_rejects_invalid_identity_dates(
    tmp_path, computed_at, signal_date, message
):
    storage = _storage(tmp_path)
    snapshot = _snapshot(computed_at, 101.0)
    snapshot["signal_date"] = signal_date

    with pytest.raises(ValueError, match=message):
        storage.append_signal_snapshot(snapshot)

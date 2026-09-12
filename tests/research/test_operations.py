import json
from decimal import Decimal

import pytest

from src.research.ingestion import load_demo
from src.research.operations import backup, verify_backup
from src.research.outcomes import Outcome, outcome_summary, record_outcome
from src.research.storage import ResearchStore, canonical


def test_first_matured_outcome_survives_price_corrections(tmp_path):
    store = ResearchStore(tmp_path)
    model = "a" * 64
    store.control.put(
        "personal", "model_run", model, {"interpretation": "reconstruction"}
    )

    def record(price):
        cap = store.capture(
            "personal",
            "https://example.org/prices",
            {},
            canonical(
                {
                    "schema_version": "adjusted-close/1",
                    "target": "SPY",
                    "prices": [
                        {"date": "2024-01-02", "value": "100"},
                        {"date": "2024-02-02", "value": price},
                    ],
                }
            ),
        )
        return record_outcome(
            store,
            "personal",
            Outcome(
                signal_date="2024-01-01",
                model_run_id=model,
                target="SPY",
                entry_date="2024-01-02",
                exit_date="2024-02-02",
                entry_price="100",
                exit_price=price,
                price_capture_id=cap["id"],
            ),
        )

    a = record("110")
    b = record("108")
    assert Decimal(a["return_pct"]) == 10 and Decimal(b["return_pct"]) == 8
    assert b["first_matured_id"] == a["id"] and b["correction_of"] == a["id"]
    assert outcome_summary(store, "personal")["distinct_signal_dates"] == 1
    assert (
        store.control.get("personal", "outcome", a["id"])["return_pct"]
        == a["return_pct"]
    )


def test_backup_rejects_missing_dependencies(tmp_path):
    store = ResearchStore(tmp_path / "data")
    load_demo(store)
    path = tmp_path / "backup"
    backup(store, path)
    _, manifest = store.manifest("personal")
    part = manifest["snapshots"][0]["part"]
    relative = f"objects/{part[:2]}/{part}"
    (path / relative).unlink()
    meta = json.loads((path / "backup.json").read_text())
    del meta["files"][relative]
    (path / "backup.json").write_bytes(canonical(meta))
    with pytest.raises(ValueError, match="dependency"):
        verify_backup(path)

"""Tests for forward-only evaluation of immutable signal publications."""

import numpy as np
import pandas as pd
import pytest

from src.etl.storage import DataStorage
from src.indicators.live_evaluation import compute_live_evaluation


ASSETS = {
    "sp500_price": {"name": "S&P 500", "category": "Large Cap Equities"}
}


def _storage(tmp_path) -> DataStorage:
    return DataStorage(
        raw_path=tmp_path / "raw",
        curated_path=tmp_path / "curated",
    )


def _snapshot(signal_date: str, computed_at: str, regime: int, glci: float) -> dict:
    return {
        "signal_date": signal_date,
        "computed_at": computed_at,
        "regime": regime,
        "glci": glci,
    }


def _save_prices(storage: DataStorage, dates, values) -> None:
    storage.save_raw(
        pd.DataFrame({"date": pd.to_datetime(dates), "value": values}),
        "fred",
        "sp500_price",
    )


def test_live_record_selects_first_publication_and_waits_for_later_bar(tmp_path):
    storage = _storage(tmp_path)
    storage.append_signal_snapshot(
        _snapshot("2026-07-10", "2026-07-11T12:00:00Z", 1, 100.0)
    )
    storage.append_signal_snapshot(
        _snapshot("2026-07-10", "2026-07-14T12:00:00Z", -1, 999.0)
    )
    _save_prices(
        storage,
        ["2026-07-10", "2026-07-17", "2026-07-24"],
        [100.0, 110.0, 121.0],
    )

    result = compute_live_evaluation(
        storage,
        ASSETS,
        horizons=[1, 4],
        min_observations=1,
    )

    assert result["ledger"] == {
        "vintage_count": 2,
        "unique_signal_dates": 1,
        "duplicate_vintages": 1,
        "first_signal_date": "2026-07-10",
        "latest_signal_date": "2026-07-10",
    }
    one_week = result["assets"][0]["horizons"]["1"]
    assert one_week["matured"] == 1
    assert one_week["median"] is None
    assert one_week["hit_rate"] is None
    assert one_week["by_regime"]["loose"]["matured"] == 1
    assert one_week["by_regime"]["loose"]["median"] == 0.1
    assert one_week["by_regime"]["tight"]["matured"] == 0

    four_week = result["assets"][0]["horizons"]["4"]
    assert four_week["pending"] == 1
    assert four_week["next_maturity_date"] == "2026-08-14"


def test_metrics_stay_hidden_until_minimum_sample_is_met(tmp_path):
    storage = _storage(tmp_path)
    for week in range(3):
        signal_date = pd.Timestamp("2026-01-02") + pd.offsets.Week(week, weekday=4)
        storage.append_signal_snapshot(
            _snapshot(
                signal_date.strftime("%Y-%m-%d"),
                (signal_date + pd.Timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z"),
                0,
                100.0 + week,
            )
        )

    dates = pd.date_range("2026-01-02", periods=8, freq="W-FRI")
    _save_prices(storage, dates, np.linspace(100.0, 107.0, len(dates)))

    result = compute_live_evaluation(
        storage,
        ASSETS,
        horizons=[1],
        min_observations=4,
    )
    stats = result["assets"][0]["horizons"]["1"]
    assert stats["matured"] == 3
    assert stats["median"] is None
    assert stats["hit_rate"] is None
    assert stats["status"] == "collecting"
    assert result["status"] == "collecting"


def test_aggregate_sample_cannot_make_mixed_regimes_reportable(tmp_path):
    storage = _storage(tmp_path)
    signal_dates = pd.date_range("2025-01-03", periods=21, freq="W-FRI")
    for index, signal_date in enumerate(signal_dates):
        storage.append_signal_snapshot(
            _snapshot(
                signal_date.strftime("%Y-%m-%d"),
                (signal_date + pd.Timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z"),
                (-1, 0, 1)[index % 3],
                100.0 + index,
            )
        )
    price_dates = pd.date_range("2025-01-03", periods=30, freq="W-FRI")
    _save_prices(storage, price_dates, np.linspace(100.0, 129.0, len(price_dates)))

    result = compute_live_evaluation(
        storage,
        ASSETS,
        horizons=[1],
        min_observations=8,
    )
    stats = result["assets"][0]["horizons"]["1"]

    assert stats["matured"] == 21
    assert stats["median"] is None
    assert stats["hit_rate"] is None
    assert stats["status"] == "collecting"
    assert all(
        regime_stats["matured"] == 7
        for regime_stats in stats["by_regime"].values()
    )
    assert result["status"] == "collecting"


def test_missing_ledger_is_explicitly_unavailable(tmp_path):
    result = compute_live_evaluation(
        _storage(tmp_path),
        ASSETS,
        horizons=[4, 13, 26],
    )

    assert result["status"] == "unavailable"
    assert result["ledger"]["vintage_count"] == 0
    assert result["assets"] == []
    assert result["methodology"]["signal_recorded_before_outcome"] is True
    assert result["methodology"]["source_vintage_complete"] is False
    assert result["methodology"]["outcome_vintage_complete"] is False


def test_malformed_nonempty_ledger_fails_closed(tmp_path):
    storage = _storage(tmp_path)
    storage.save_curated(
        pd.DataFrame({"signal_date": ["2026-07-10"]}),
        "indices",
        "glci_vintages",
    )

    with pytest.raises(ValueError, match="missing required columns: computed_at, regime"):
        compute_live_evaluation(storage, ASSETS, horizons=[4])


def test_publication_before_signal_date_fails_closed(tmp_path):
    storage = _storage(tmp_path)
    storage.save_curated(
        pd.DataFrame(
            [_snapshot("2026-07-10", "2026-07-09T23:59:00Z", 0, 100.0)]
        ),
        "indices",
        "glci_vintages",
    )

    with pytest.raises(ValueError, match="computation before its signal date"):
        compute_live_evaluation(storage, ASSETS, horizons=[4])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("signal_date", "not-a-date", "unparseable"),
        ("computed_at", "not-a-date", "unparseable"),
        ("regime", 2, "outside -1, 0, or 1"),
        ("regime", None, "outside -1, 0, or 1"),
    ],
)
def test_invalid_publication_identity_or_regime_fails_closed(
    tmp_path, field, value, message
):
    storage = _storage(tmp_path)
    snapshot = _snapshot("2026-07-10", "2026-07-11T12:00:00Z", 0, 100.0)
    snapshot[field] = value
    storage.save_curated(
        pd.DataFrame([snapshot]),
        "indices",
        "glci_vintages",
    )

    with pytest.raises(ValueError, match=message):
        compute_live_evaluation(storage, ASSETS, horizons=[4])

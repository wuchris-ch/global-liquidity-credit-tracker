"""Tests for scheduled-update signal snapshot construction."""

from types import SimpleNamespace

import pandas as pd

from scripts.update_data import build_glci_snapshot


def test_build_glci_snapshot_captures_latest_state_and_pillars(monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    result = SimpleNamespace(
        glci=pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-07-03", "2026-07-10"]),
                "value": [100.0, 101.5],
                "zscore": [0.2, 0.4],
                "regime": [0, 0],
                "momentum": [-0.1, 0.3],
                "prob_regime_change": [0.1, 0.2],
            }
        ),
        pillars=pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-07-03", "2026-07-10"]),
                "liquidity": [0.5, 0.7],
                "credit": [-0.2, -0.1],
                "stress": [0.3, 0.1],
            }
        ),
        metadata={
            "computed_at": "2026-07-10T12:30:00",
            "factor_method": "auto",
        },
        weights={
            "pillar_weights": {
                "liquidity": 0.45,
                "credit": 0.35,
                "stress": 0.20,
            }
        },
    )

    snapshot = build_glci_snapshot(result)

    assert snapshot == {
        "computed_at": "2026-07-10T12:30:00Z",
        "signal_date": "2026-07-10",
        "historical_mode": "reconstructed_current_vintage",
        "point_in_time": False,
        "frequency": "W-FRI",
        "model_revision": "local",
        "factor_method": "auto",
        "glci": 101.5,
        "zscore": 0.4,
        "regime": 0,
        "momentum": 0.3,
        "prob_regime_change": 0.2,
        "weight_credit": 0.35,
        "weight_liquidity": 0.45,
        "weight_stress": 0.2,
        "pillar_liquidity": 0.7,
        "pillar_credit": -0.1,
        "pillar_stress": 0.1,
    }

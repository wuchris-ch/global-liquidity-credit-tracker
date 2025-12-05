#!/usr/bin/env python3
"""
Export curated time-series data to API-shaped JSON for static hosting (e.g., Cloudflare R2).

Outputs are written under a target directory (default: data/export/latest) using the
same paths as the FastAPI endpoints, so a static host can serve them directly:

  <base>/api/series
  <base>/api/series/{id}
  <base>/api/series/{id}/latest
  <base>/api/indices
  <base>/api/indices/{id}
  <base>/api/glci
  <base>/api/glci/latest
  <base>/api/glci/pillars
  <base>/api/glci/freshness
  <base>/api/glci/regime-history

Optional snapshots can be copied to snapshots/YYYY-MM-DD for long-cache hosting.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# Ensure repository root is on sys.path for module imports when run in CI
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (
    CURATED_DATA_PATH,
    RAW_DATA_PATH,
    get_all_indices,
    get_all_series,
    get_index_config,
    get_series_config,
)
from src.etl.storage import DataStorage

# Mirrors CATEGORY_MAP in src/api/server.py; kept here to avoid FastAPI import.
CATEGORY_MAP: Dict[str, str] = {
    "fed_total_assets": "Central Banks",
    "ecb_total_assets": "Central Banks",
    "boj_total_assets": "Central Banks",
    "boe_total_assets": "Central Banks",
    "pboc_total_assets": "Central Banks",
    "fed_treasury_general_account": "Central Banks",
    "fed_reverse_repo": "Central Banks",
    "fed_reserve_balances": "Central Banks",
    "sofr": "Funding Rates",
    "fed_funds_rate": "Funding Rates",
    "euro_short_term_rate": "Funding Rates",
    "us_m2": "Money Supply",
    "eu_m3": "Money Supply",
    "china_m2": "Money Supply",
    "japan_m2": "Money Supply",
    "ted_spread": "Credit Spreads",
    "ice_bofa_us_high_yield_spread": "Credit Spreads",
    "ice_bofa_us_ig_spread": "Credit Spreads",
    "vix": "Volatility",
    "move_index": "Volatility",
    "nfci": "Financial Conditions",
    "us_bank_credit_total": "Bank Credit",
    "us_bank_loans_leases": "Bank Credit",
    "us_consumer_credit": "Consumer Credit",
    "us_commercial_paper": "Commercial Paper",
    "bis_credit_us": "BIS Credit",
    "bis_credit_eu": "BIS Credit",
    "bis_credit_cn": "BIS Credit",
    "bis_credit_jp": "BIS Credit",
    "bis_credit_gap_us": "Credit Gap",
    "bis_credit_gap_eu": "Credit Gap",
    "bis_credit_gap_cn": "Credit Gap",
    "bis_credit_gap_jp": "Credit Gap",
}

REGIME_LABELS = {-1: "tight", 0: "neutral", 1: "loose"}


def fmt_date(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def export_series_list(series_cfg: Dict[str, dict], output_dir: Path) -> None:
    items = []
    for series_id, cfg in series_cfg.items():
        items.append(
            {
                "id": series_id,
                "name": cfg.get("description", series_id),
                "source": cfg.get("source", "unknown").upper(),
                "category": CATEGORY_MAP.get(series_id, "Other"),
                "frequency": cfg.get("frequency", "unknown"),
                "unit": cfg.get("unit", ""),
            }
        )
    write_json(output_dir / "api" / "series", items)


def export_single_series(
    storage: DataStorage, series_id: str, cfg: dict, output_dir: Path
) -> bool:
    source = cfg.get("source")
    df = storage.load_raw(source, series_id)
    if df is None or df.empty:
        return False

    df = df.sort_values("date")
    data_points = [
        {"date": fmt_date(row["date"]), "value": float(row["value"])}
        for _, row in df.iterrows()
        if not pd.isna(row["value"])
    ]

    payload = {
        "id": series_id,
        "name": cfg.get("description", series_id),
        "source": source.upper() if source else "",
        "unit": cfg.get("unit", ""),
        "data": data_points,
    }
    write_json(output_dir / "api" / "series" / series_id, payload)

    # Latest endpoint
    latest = df.iloc[-1]
    change_pct = 0.0
    if len(df) > 7:
        prev = df.iloc[-8]["value"]
        if prev not in (0, None) and not pd.isna(prev):
            change_pct = ((latest["value"] - prev) / prev) * 100
    latest_payload = {
        "id": series_id,
        "date": fmt_date(latest["date"]),
        "value": float(latest["value"]),
        "change": round(change_pct, 2),
        "unit": cfg.get("unit", ""),
    }
    write_json(output_dir / "api" / "series" / series_id / "latest", latest_payload)
    return True


def export_indices_list(index_cfg: Dict[str, dict], output_dir: Path) -> None:
    items = []
    for index_id, cfg in index_cfg.items():
        items.append(
            {
                "id": index_id,
                "name": index_id.replace("_", " ").title(),
                "description": cfg.get("description", ""),
                "frequency": cfg.get("frequency", ""),
                "components": len(cfg.get("components", cfg.get("pillars", {}))),
            }
        )
    write_json(output_dir / "api" / "indices", items)


def export_single_index(
    storage: DataStorage, index_id: str, output_dir: Path
) -> bool:
    df = storage.load_curated("indices", index_id)
    if df is None or df.empty:
        return False

    df = df.sort_values("date")
    data_points = [
        {"date": fmt_date(row["date"]), "value": float(row["value"])}
        for _, row in df.iterrows()
        if not pd.isna(row["value"])
    ]
    payload = {
        "id": index_id,
        "name": index_id.replace("_", " ").title(),
        "description": get_index_config(index_id).get("description", ""),
        "data": data_points,
    }
    write_json(output_dir / "api" / "indices" / index_id, payload)
    return True


def export_glci(storage: DataStorage, output_dir: Path) -> bool:
    glci_df = storage.load_curated("indices", "glci")
    pillars_df = storage.load_curated("indices", "glci_pillars")
    weights_path = CURATED_DATA_PATH / "indices" / "glci_weights.json"

    if glci_df is None or glci_df.empty or pillars_df is None or pillars_df.empty:
        return False
    if not weights_path.exists():
        return False

    with open(weights_path, "r") as f:
        weights = json.load(f)
    pillar_weights = weights.get("pillar_weights", {})

    glci_df = glci_df.sort_values("date")
    pillars_df = pillars_df.sort_values("date")

    latest = glci_df.iloc[-1]
    regime_code = int(latest.get("regime", 0))
    regime_label = REGIME_LABELS.get(regime_code, "unknown")

    # Build pillar list for latest
    latest_pillars = pillars_df.iloc[-1]
    pillar_list = []
    for name, weight in pillar_weights.items():
        if name in latest_pillars:
            value = float(latest_pillars[name]) if not pd.isna(latest_pillars[name]) else 0
            pillar_list.append(
                {
                    "name": name,
                    "value": value,
                    "weight": weight,
                    "contribution": value * weight,
                }
            )

    data_series = [
        {"date": fmt_date(row["date"]), "value": float(row["value"])}
        for _, row in glci_df.iterrows()
        if not pd.isna(row["value"])
    ]

    pillar_data: Dict[str, List[Dict[str, float]]] = {}
    for name in pillar_weights.keys():
        if name in pillars_df.columns:
            pillar_data[name] = [
                {"date": fmt_date(row["date"]), "value": float(row[name])}
                for _, row in pillars_df.iterrows()
                if not pd.isna(row[name])
            ]

    payload = {
        "value": float(latest["value"]),
        "zscore": float(latest.get("zscore", 0) or 0),
        "regime": regime_label,
        "regime_code": regime_code,
        "date": fmt_date(latest["date"]),
        "momentum": float(latest.get("momentum", 0) or 0),
        "prob_regime_change": float(latest.get("prob_regime_change", 0) or 0),
        "pillars": pillar_list,
        "data": data_series,
        "pillar_data": pillar_data,
    }

    write_json(output_dir / "api" / "glci", payload)
    write_json(
        output_dir / "api" / "glci" / "latest",
        {
            "date": fmt_date(latest["date"]),
            "value": float(latest["value"]),
            "zscore": float(latest.get("zscore", 0) or 0),
            "regime": regime_code,
            "regime_label": regime_label,
            "momentum": float(latest.get("momentum", 0) or 0),
        },
    )

    # Pillar breakdown (latest)
    write_json(
        output_dir / "api" / "glci" / "pillars",
        {
            "date": fmt_date(latest_pillars["date"]),
            "pillars": {
                name: {
                    "value": float(latest_pillars[name])
                    if not pd.isna(latest_pillars[name])
                    else 0,
                    "weight": pillar_weights.get(name, 0),
                    "contribution": (
                        float(latest_pillars[name]) * pillar_weights.get(name, 0)
                        if not pd.isna(latest_pillars[name])
                        else 0
                    ),
                }
                for name in pillar_weights.keys()
                if name in latest_pillars
            },
        },
    )

    # Regime history
    regimes_df = glci_df[["date", "regime"]].copy()
    regimes_df["regime_label"] = regimes_df["regime"].map(REGIME_LABELS)

    periods = []
    current_regime = None
    period_start = None
    for _, row in regimes_df.iterrows():
        regime = row["regime_label"]
        date = row["date"]
        if regime != current_regime:
            if current_regime is not None:
                periods.append(
                    {
                        "regime": current_regime,
                        "start": fmt_date(period_start),
                        "end": fmt_date(date),
                    }
                )
            current_regime = regime
            period_start = date
    if current_regime is not None:
        periods.append(
            {
                "regime": current_regime,
                "start": fmt_date(period_start),
                "end": fmt_date(regimes_df["date"].iloc[-1]),
            }
        )
    regime_counts = regimes_df["regime_label"].value_counts().to_dict()
    write_json(
        output_dir / "api" / "glci" / "regime-history",
        {"periods": periods, "counts": regime_counts, "current": current_regime},
    )

    return True


def export_glci_freshness(
    storage: DataStorage, series_cfg: Dict[str, dict], output_dir: Path
) -> None:
    index_cfg = get_index_config("global_liquidity_credit_index") or {}
    freshness = []
    for pillar_name, pillar_cfg in index_cfg.get("pillars", {}).items():
        for comp in pillar_cfg.get("components", []):
            sid = comp["series"]
            src = series_cfg.get(sid, {}).get("source", "unknown")
            last_date = storage.get_latest_date(src, sid)
            if last_date is not None:
                days_old = (pd.Timestamp.now() - last_date).days
                freshness.append(
                    {
                        "series_id": sid,
                        "pillar": pillar_name,
                        "last_date": fmt_date(last_date),
                        "days_old": int(days_old),
                        "is_stale": days_old > 14,
                    }
                )
            else:
                freshness.append(
                    {
                        "series_id": sid,
                        "pillar": pillar_name,
                        "last_date": "unknown",
                        "days_old": -1,
                        "is_stale": True,
                    }
                )
    write_json(output_dir / "api" / "glci" / "freshness", freshness)


def export_all(output_dir: Path, add_snapshot: bool) -> None:
    storage = DataStorage(raw_path=RAW_DATA_PATH, curated_path=CURATED_DATA_PATH)
    series_cfg = get_all_series()
    index_cfg = get_all_indices()

    print(f"[export] Writing JSON to {output_dir}")

    # Series
    export_series_list(series_cfg, output_dir)
    for sid, cfg in series_cfg.items():
        ok = export_single_series(storage, sid, cfg, output_dir)
        if not ok:
            print(f"[export] Skipped series (no data): {sid}")

    # Indices
    export_indices_list(index_cfg, output_dir)
    for idx in index_cfg.keys():
        ok = export_single_index(storage, idx, output_dir)
        if not ok:
            print(f"[export] Skipped index (no data): {idx}")

    # GLCI endpoints
    glci_ok = export_glci(storage, output_dir)
    if not glci_ok:
        print("[export] Skipped GLCI (missing curated data)")
    else:
        export_glci_freshness(storage, series_cfg, output_dir)

    if add_snapshot:
        date_stamp = datetime.utcnow().strftime("%Y-%m-%d")
        snap_dir = output_dir.parent / "snapshots" / date_stamp
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
        shutil.copytree(output_dir, snap_dir)
        print(f"[export] Snapshot copied to {snap_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export curated data to static JSON for CDN hosting."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/export/latest"),
        help="Output directory for JSON artifacts (default: data/export/latest)",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Also copy output to snapshots/YYYY-MM-DD for long-cache hosting",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_all(args.output, args.snapshot)


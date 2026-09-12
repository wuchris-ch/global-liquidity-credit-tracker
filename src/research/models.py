"""Pinned GLCI inputs and inspectable cutoff-fitted numerical artifacts."""

import json
from datetime import date

import numpy as np
import pandas as pd
from pydantic import Field

from ..config import get_index_config, get_series_config
from ..indicators.dynamic_factor import DynamicFactorModel
from .contracts import Contract, Query, now
from .control import Conflict
from .service import environment
from .storage import canonical, digest


class ModelRequest(Contract):
    cutoff: date
    start: date
    inputs: dict[str, Query] = Field(min_length=1, max_length=100)
    interpretation: str = "reconstruction"


class DatasetView:
    """Fetcher boundary with no network or fallback to the mutable raw store."""

    def __init__(self, store, workspace, inputs, cutoff):
        self.cutoff = pd.Timestamp(cutoff)
        self.inputs = {name: store.query(workspace, q) for name, q in inputs.items()}
        self.unit_conversions = {}
        aliases = {
            "Millions of U.S. Dollars": "millions_usd",
            "Billions of U.S. Dollars": "billions_usd",
            "Billions of US Dollars": "billions_usd",
            "Billions of Dollars": "billions_usd",
            "Millions of Euros": "millions_eur",
            "100 Million Yen": "hundred_millions_jpy",
            "Percent": "percent",
            "Index": "index",
        }
        for name, item in self.inputs.items():
            spec = get_series_config(name)
            if (
                not spec
                or spec["source_id"] != item["series"]["source_id"]
                or spec["source"] != item["series"]["source"]
            ):
                raise ValueError(f"Model source identity mismatch: {name}")
            if spec["frequency"] != item["series"]["frequency"]:
                raise ValueError(f"Model source frequency mismatch: {name}")
            country = {"US": "USA", "EU": "EMU", "CN": "CHN", "JP": "JPN"}.get(
                spec.get("country"), spec.get("country")
            )
            if item["series"]["country"] not in (country, spec.get("country")):
                raise ValueError(f"Model source country mismatch: {name}")
            actual = aliases.get(
                item["series"]["unit"], item["series"]["unit"].lower().replace(" ", "_")
            )
            expected = spec["unit"]
            if actual == expected or (
                expected == "local_currency" and spec["source"] == "bis"
            ):
                scale = 1
            elif actual == "billions_usd" and expected == "millions_usd":
                scale = 1000
            elif actual == "millions_usd" and expected == "billions_usd":
                scale = 0.001
            else:
                raise ValueError(
                    f"Model unit conversion is unreviewed: {name}: {actual} to {expected}"
                )
            self.unit_conversions[name] = {
                "source_unit": item["series"]["unit"],
                "model_unit": expected,
                "scale": scale,
            }

    def fetch_series(self, series_id, start_date=None, end_date=None, **kwargs):
        if series_id not in self.inputs:
            raise ValueError(f"Pinned model input unavailable: {series_id}")
        item = self.inputs[series_id]
        frame = pd.DataFrame(item["data"], columns=["date", "value"])
        frame["date"] = pd.to_datetime(frame["date"])
        frame["value"] = (
            pd.to_numeric(frame["value"]) * self.unit_conversions[series_id]["scale"]
        )
        end = min(self.cutoff, pd.Timestamp(end_date)) if end_date else self.cutoff
        frame = frame[frame.date <= end]
        if start_date:
            frame = frame[frame.date >= pd.Timestamp(start_date)]
        return frame.reset_index(drop=True)


def factor_artifact(model, training):
    if model._method_used not in ("pca", "pca_shrunk") or model._scaler is None:
        raise ValueError("Research artifacts require the explicit sklearn PCA path")
    prepared = model._full_data
    state = {
        "schema_version": "1.0",
        "method": model._method_used,
        "columns": model._columns,
        "training": json.loads(
            training.reset_index(names="date").to_json(
                orient="records", date_format="iso"
            )
        ),
        "prepared": prepared.to_numpy().tolist(),
        "dates": [str(d) for d in prepared.index],
        "imputation": "past-only forward fill up to 26 rows, then expanding mean; common observed start",
        "scaler_mean": model._scaler.mean_.tolist(),
        "scaler_scale": model._scaler.scale_.tolist(),
        "pca_components": model._model.components_.tolist(),
        "pca_mean": model._model.mean_.tolist(),
        "orientation": model._factor_orientations.tolist(),
        "sign_constraints": model.sign_constraints,
        "shrinkage_alpha": model.shrinkage_alpha,
        "factors": model.transform().to_numpy().tolist(),
    }
    if model._method_used == "pca_shrunk":
        state.update(
            loadings=model._shrunk_loadings.tolist(),
            projection_mean=model._factor_projection_mean.tolist(),
            projection_std=model._factor_projection_std.tolist(),
        )
    replay_factor(state)
    return state


def replay_factor(state):
    scaled = (np.array(state["prepared"]) - state["scaler_mean"]) / state[
        "scaler_scale"
    ]
    if state["method"] == "pca_shrunk":
        factors = (
            scaled @ np.array(state["loadings"]) - state["projection_mean"]
        ) / state["projection_std"]
    else:
        factors = (scaled - state["pca_mean"]) @ np.array(state["pca_components"]).T
    factors *= state["orientation"]
    if not np.allclose(factors, state["factors"], atol=1e-8, rtol=1e-8):
        raise ValueError("Model replay exceeds numerical tolerance")
    return factors


def fit_factor_at_cutoff(frame, cutoff):
    training = frame.loc[frame.index <= pd.Timestamp(cutoff)].copy()
    model = DynamicFactorModel(
        method="pca_shrunk", sign_constraints={c: 1 for c in training.columns}
    )
    model.fit(training)
    return factor_artifact(model, training)


def run_glci(store, workspace, payload):
    from ..indicators.glci import GLCIComputer

    request = ModelRequest.model_validate(payload)
    if request.start > request.cutoff:
        raise ValueError("Model start follows cutoff")
    if request.interpretation not in ("reconstruction", "source_vintage"):
        raise ValueError("Unknown model interpretation")
    for q in request.inputs.values():
        if not q.dataset:
            raise ValueError("Model jobs require pinned manifests")
        if request.interpretation == "source_vintage" and (
            q.basis != "source" or q.as_of > str(request.cutoff)
        ):
            raise ValueError(
                "Historical model requires source vintages no later than training cutoff"
            )
    required = {
        c["series"]
        for p in get_index_config("global_liquidity_credit_index")["pillars"].values()
        for c in p["components"]
    }
    if required - set(request.inputs):
        raise ValueError(
            "Missing pinned model inputs: "
            + ", ".join(sorted(required - set(request.inputs)))
        )
    view = DatasetView(store, workspace, request.inputs, request.cutoff)
    artifacts = {}
    computer = GLCIComputer(
        fetcher=view,
        training_cutoff=request.cutoff,
        artifact_sink=lambda name, model, training: artifacts.update(
            {name: factor_artifact(model, training)}
        ),
    )
    result = computer.compute(
        start_date=str(request.start),
        end_date=str(request.cutoff),
        factor_method="pca_shrunk",
        save_output=False,
        verbose=False,
    )
    record = {
        "request": request.model_dump(mode="json"),
        "inputs": view.inputs,
        "unit_conversions": view.unit_conversions,
        "environment": environment(),
        "models": artifacts,
        "glci": json.loads(result.glci.to_json(orient="records", date_format="iso")),
        "pillars": json.loads(
            result.pillars.to_json(orient="records", date_format="iso")
        ),
        "regimes": json.loads(
            result.regimes.to_json(orient="records", date_format="iso")
        ),
        "weights": result.weights,
        "current_regime": result.metadata["current_regime"],
        "regime_coverage": (
            "available"
            if result.metadata["current_regime"]["regime"] is not None
            else "insufficient common history for the configured rolling regime"
        ),
        "interpretation": request.interpretation,
        "historical_platform_prediction": False,
    }
    identifier = digest(canonical(record))
    artifact = store.objects.write(canonical(record))
    try:
        with store.control.transaction() as tx:
            from .fencing import guard

            guard(store.control, workspace, tx)
            store.control.put(
                workspace,
                "model_run",
                identifier,
                {"artifact": artifact, **record, "computed_at": now()},
                connection=tx,
            )
    except Conflict:
        return store.control.get(workspace, "model_run", identifier)
    return store.control.get(workspace, "model_run", identifier)

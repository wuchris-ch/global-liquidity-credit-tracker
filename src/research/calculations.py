"""Allowlisted deterministic calculations. No evaluation of user code or SQL."""

from decimal import Decimal, localcontext

from .contracts import Recipe


def calculate(recipe: Recipe, inputs: list[dict]) -> dict:
    units = [i["series"]["unit"] for i in inputs]
    op = recipe.operation
    if op in ("spread", "ratio") and len(set(units)) != 1:
        raise ValueError("Spread and ratio require matching units")
    usd_scale = {"millions USD": Decimal(1), "billions USD": Decimal(1000)}
    if op == "net_liquidity" and any(u not in usd_scale for u in units):
        raise ValueError("Net liquidity requires explicitly scaled USD inputs")
    maps = [
        {
            r["date"]: Decimal(r["value"]) if r["value"] is not None else None
            for r in i["data"]
        }
        for i in inputs
    ]
    dates = sorted(set().union(*(m.keys() for m in maps)))
    values = []
    window = recipe.window
    with localcontext() as ctx:
        ctx.prec = 28
        for index, d in enumerate(dates):
            row = [m.get(d) for m in maps]
            value = row[0]
            if op in ("spread", "ratio", "net_liquidity"):
                if any(v is None for v in row):
                    value = None
                elif op == "spread":
                    value = row[0] - row[1]
                elif op == "ratio":
                    value = row[0] / row[1] if row[1] else None
                else:
                    value = (
                        row[0] * usd_scale[units[0]]
                        - row[1] * usd_scale[units[1]]
                        - row[2] * usd_scale[units[2]]
                    )
            elif op in ("difference", "pct_change", "annualized_growth"):
                prior = maps[0].get(dates[index - window]) if index >= window else None
                if value is None or prior is None:
                    value = None
                elif op == "difference":
                    value -= prior
                elif not prior:
                    value = None
                elif op == "pct_change":
                    value = (value / prior - 1) * 100
                elif value / prior <= 0:
                    value = None
                else:
                    value = (
                        (value / prior) ** (Decimal(recipe.periods_per_year) / window)
                        - 1
                    ) * 100
            elif op in ("rolling_mean", "zscore"):
                history = [
                    maps[0].get(t)
                    for t in dates[max(0, index - window + 1) : index + 1]
                ]
                if len(history) < window or any(v is None for v in history):
                    value = None
                else:
                    mean = sum(history) / window
                    if op == "rolling_mean":
                        value = mean
                    else:
                        sd = (
                            (
                                sum((v - mean) ** 2 for v in history) / (window - 1)
                            ).sqrt()
                            if window > 1
                            else 0
                        )
                        value = (value - mean) / sd if sd else None
            values.append(
                {
                    "date": d,
                    "value": str(value) if value is not None else None,
                    "threshold_met": (
                        bool(value >= recipe.threshold)
                        if value is not None and recipe.threshold is not None
                        else None
                    ),
                }
            )
    unit = (
        "percent"
        if op in ("pct_change", "annualized_growth")
        else "zscore" if op == "zscore" else "ratio" if op == "ratio" else units[0]
    )
    if op == "net_liquidity":
        unit = "millions USD"
    return {
        "unit": unit,
        "data": values,
        "operation": op,
        "missing_policy": "no implicit filling; null propagates",
        "window_basis": "observation rows, not calendar durations",
        "precision": "decimal28",
    }


def compare(left, right):
    if left["result"]["unit"] != right["result"]["unit"]:
        raise ValueError("Cannot compare different output units")
    a = {r["date"]: r["value"] for r in left["result"]["data"]}
    b = {r["date"]: r["value"] for r in right["result"]["data"]}
    rows = []
    for d in sorted(a.keys() | b.keys()):
        x, y = a.get(d), b.get(d)
        rows.append(
            {
                "date": d,
                "before": x,
                "after": y,
                "change": (
                    str(Decimal(y) - Decimal(x))
                    if x is not None and y is not None
                    else None
                ),
            }
        )
    recipe_a = {
        k: v for k, v in left["recipe"].items() if k not in ("title", "queries")
    }
    recipe_b = {
        k: v for k, v in right["recipe"].items() if k not in ("title", "queries")
    }
    same = recipe_a == recipe_b and [
        q["series_id"] for q in left["recipe"]["queries"]
    ] == [q["series_id"] for q in right["recipe"]["queries"]]
    return {
        "left": left["id"],
        "right": right["id"],
        "unit": left["result"]["unit"],
        "data": rows,
        "attribution": (
            "data comparison with fixed transformation"
            if same
            else "data and/or transformation changed; no isolated attribution"
        ),
    }

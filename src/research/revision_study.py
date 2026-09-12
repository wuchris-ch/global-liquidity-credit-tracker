"""A fixed-cohort payroll revision study, with exact inputs and block uncertainty."""

from __future__ import annotations

import json
import math
import random
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

from .calculations import calculate
from .contracts import Query, Recipe, now
from .ingestion import Transport
from .release_lab import bundle_evidence, capture_release, public_snapshot, seal_bundle
from .release_sources import TRACKS, WORKSPACE, paged, periods
from .storage import canonical, digest

PLAN_PATH = (
    Path(__file__).resolve().parents[2] / "config/research/payroll-revision-study.json"
)


def percentile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def summarize(rows, thresholds):
    included = [r for r in rows if r["status"] == "included"]
    revisions = [float(r["revision"]) for r in included]
    if not revisions:
        return {"n": 0, "planned": len(rows), "excluded": len(rows)}
    return dict(
        n=len(included),
        planned=len(rows),
        excluded=len(rows) - len(included),
        initial_mean=mean(float(r["initial"]) for r in included),
        revised_mean=mean(float(r["revised"]) for r in included),
        mean_revision=mean(revisions),
        median_revision=median(revisions),
        mean_absolute_revision=mean(abs(v) for v in revisions),
        largest_absolute_revision=max(abs(v) for v in revisions),
        upward_revisions=sum(v > 0 for v in revisions),
        downward_revisions=sum(v < 0 for v in revisions),
        unchanged=sum(v == 0 for v in revisions),
        thresholds=[
            dict(
                threshold=t,
                initial_above=sum(Decimal(r["initial"]) > t for r in included),
                revised_above=sum(Decimal(r["revised"]) > t for r in included),
                switches=sum(
                    (Decimal(r["initial"]) > t) != (Decimal(r["revised"]) > t)
                    for r in included
                ),
                to_above=sum(
                    Decimal(r["initial"]) <= t < Decimal(r["revised"]) for r in included
                ),
                from_above=sum(
                    Decimal(r["revised"]) <= t < Decimal(r["initial"]) for r in included
                ),
            )
            for t in thresholds
        ],
    )


def uncertainty(rows, plan):
    if any(r["status"] != "included" for r in rows):
        return {
            "status": "unavailable",
            "reason": "Complete chronological cohort required for block resampling",
        }
    spec = plan["uncertainty"]
    revisions = [float(r["revision"]) for r in rows]
    n, intervals = len(rows), []
    for block in spec["block_months"]:
        rng = random.Random(spec["seed"] + block)
        means, absolute, switches = [], [], {t: [] for t in plan["thresholds"]}
        for _ in range(spec["replicates"]):
            indices = []
            while len(indices) < n:
                first = rng.randrange(n)
                indices.extend((first + j) % n for j in range(block))
            indices = indices[:n]
            means.append(mean(revisions[i] for i in indices))
            absolute.append(mean(abs(revisions[i]) for i in indices))
            for threshold in switches:
                switches[threshold].append(
                    mean(
                        (Decimal(rows[i]["initial"]) > threshold)
                        != (Decimal(rows[i]["revised"]) > threshold)
                        for i in indices
                    )
                )
        bounds = lambda v: [percentile(v, 0.025), percentile(v, 0.975)]
        intervals.append(
            dict(
                block_months=block,
                mean_revision=bounds(means),
                mean_absolute_revision=bounds(absolute),
                switch_share=[
                    dict(threshold=t, interval=bounds(v)) for t, v in switches.items()
                ],
            )
        )
    return dict(
        status="computed",
        **spec,
        intervals=intervals,
        interpretation="95% resampling intervals describe stability within this 24-month sample under 3- and 6-month dependence blocks. They are not forecast intervals or confidence in an unrevised true value. Common benchmark changes can affect the whole sample.",
    )


def previous_month(value):
    year, month = int(value[:4]), int(value[5:7])
    return f"{year if month > 1 else year-1:04d}-{month-1 if month > 1 else 12:02d}-01"


def build_study(store, plan=None, transport=None):
    plan = plan or json.loads(PLAN_PATH.read_text())
    expected = periods(plan["observation_start"], plan["observation_end"])
    transport = transport or Transport(store, WORKSPACE)
    initial, discovery_caps = paged(
        transport,
        "series/observations",
        "observations",
        {
            "series_id": plan["series_id"],
            "observation_start": plan["observation_start"],
            "observation_end": plan["observation_end"],
            "realtime_start": "1776-07-04",
            "realtime_end": plan["comparison_information_date"],
            "output_type": 4,
        },
    )
    if len({r["date"] for r in initial}) != len(initial) or any(
        r["date"] not in expected for r in initial
    ):
        raise ValueError("Initial-release history has duplicate or unexpected periods")
    firsts = {r["date"]: r for r in initial}
    snapshots, rows, captures = {}, [], list(discovery_caps)
    dates = {r["realtime_start"] for r in initial if r["value"] != "."}
    dates.add(plan["comparison_information_date"])
    for information_date in sorted(dates):
        if information_date > plan["comparison_information_date"]:
            raise ValueError("Initial-release date follows the fixed comparison date")
        existing = [
            s
            for s in store.control.list(WORKSPACE, "release_snapshot")
            if s["series_id"] == plan["series_id"]
            and s["information_date"] == information_date
        ]
        identifier = (
            existing[0]["id"]
            if existing
            else capture_release(store, plan["series_id"], information_date, transport)
        )
        snapshot = store.control.get(WORKSPACE, "release_snapshot", identifier)
        snapshots[information_date] = snapshot
        captures.extend(snapshot["captures"])
    latest = snapshots[plan["comparison_information_date"]]
    for period in expected:
        first = firsts.get(period)
        if not first or first["value"] == ".":
            rows.append(
                dict(
                    period=period,
                    status="excluded",
                    reason="Initial-release history unavailable",
                )
            )
            continue
        before = snapshots[first["realtime_start"]]
        prior = previous_month(period)
        maps = [
            {r["date"]: r["value"] for r in s["observations"]} for s in (before, latest)
        ]
        if any(period not in m or prior not in m for m in maps):
            rows.append(
                dict(
                    period=period,
                    status="excluded",
                    reason="Same-vintage current and preceding levels unavailable",
                )
            )
            continue
        if Decimal(maps[0][period]) != Decimal(first["value"]):
            raise ValueError("Initial-release level disagrees with the dated snapshot")
        results, run_specs = [], []
        for snapshot in (before, latest):
            recipe = Recipe(
                title=f"Payroll monthly change: {period}",
                operation="difference",
                queries=[
                    Query(
                        series_id=plan["series_id"],
                        start=prior,
                        end=period,
                        as_of=snapshot["information_date"],
                        dataset=snapshot["dataset_manifest"],
                    )
                ],
            )
            inputs = [store.query(WORKSPACE, recipe.queries[0])]
            result = calculate(recipe, inputs)
            results.append(Decimal(result["data"][-1]["value"]))
            run_specs.append(
                dict(
                    recipe=recipe.model_dump(mode="json"),
                    result_hash=digest(canonical(result)),
                    capture_ids=snapshot["captures"],
                )
            )
        current_revision = Decimal(maps[1][period]) - Decimal(maps[0][period])
        prior_contribution = Decimal(maps[0][prior]) - Decimal(maps[1][prior])
        revision = results[1] - results[0]
        if current_revision + prior_contribution != revision:
            raise ValueError("Changed-input attribution failed to reconcile")
        rows.append(
            dict(
                period=period,
                status="included",
                initial_date=before["information_date"],
                revised_date=latest["information_date"],
                before_snapshot=before["id"],
                after_snapshot=latest["id"],
                initial=str(results[0]),
                revised=str(results[1]),
                revision=str(revision),
                inputs=dict(
                    initial_current=maps[0][period],
                    initial_previous=maps[0][prior],
                    revised_current=maps[1][period],
                    revised_previous=maps[1][prior],
                ),
                attribution=dict(
                    current_level=str(current_revision),
                    previous_level=str(prior_contribution),
                ),
                # Result identities are public; internal workspace capture IDs stay in the store.
                result_hashes=[r["result_hash"] for r in run_specs],
            )
        )
    study = dict(
        plan=plan,
        plan_hash=digest(canonical(plan)),
        rows=rows,
        summary=summarize(rows, plan["thresholds"]),
        by_year=[
            dict(
                year=year,
                **summarize(
                    [r for r in rows if r["period"].startswith(str(year))],
                    plan["thresholds"],
                ),
            )
            for year in sorted({int(p[:4]) for p in expected})
        ],
        uncertainty=uncertainty(rows, plan),
        methods=[
            "Resolve initial information dates from archived initial-release rows.",
            "Verify complete, correctly scaled snapshots for every date and the fixed comparison date.",
            "Compute each monthly change from two levels in the same vintage.",
            "Compare matched periods; reconcile revisions to the two changed input levels.",
            "Report every planned month, threshold and outcome; resample consecutive blocks for stability.",
        ],
        sources=[
            "https://fred.stlouisfed.org/docs/api/fred/series_observations.html",
            "https://www.bls.gov/web/empsit/cesnaicsrev.htm",
            "https://www.bls.gov/opub/hom/ces/presentation.htm",
        ],
    )
    return seal_bundle(
        dict(
            schema_version="release-lab/1",
            kind="revision-study",
            as_of=plan["comparison_information_date"],
            captured_at=now(),
            series=[dict(id=plan["series_id"], **TRACKS[plan["series_id"]])],
            snapshots=[public_snapshot(store, s) for s in snapshots.values()],
            evidence=bundle_evidence(store, captures),
            study=study,
            inbox=[],
        )
    )

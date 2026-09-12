#!/usr/bin/env python3
"""Independently replay a release-lab bundle or notebook export, entirely offline.

Usage: python3 replay_release_lab.py research-replay.json [another-bundle.json]
Only the Python standard library is required. No workbench modules are imported.
"""

import hashlib
import json
import math
import random
import sys
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import mean, median


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, message, tolerance=1.1e-8):
    if actual is None or expected is None:
        check(actual is expected, message)
    else:
        check(
            math.isclose(
                float(actual), float(expected), rel_tol=1e-12, abs_tol=tolerance
            ),
            message,
        )


def shift(period, amount):
    original = date.fromisoformat(period)
    year, month = divmod(original.year * 12 + original.month - 1 + amount, 12)
    return date(year, month + 1, 1).isoformat()


def grid(start, end, step=1):
    check(start <= end and start[8:] == end[8:] == "01", "Invalid period range")
    result = []
    while start <= end:
        check(len(result) < 1000, "Period budget exceeded")
        result.append(start)
        start = shift(start, step)
    return result


def verify_sources(bundle):
    check(bundle["schema_version"] == "release-lab/1", "Unknown bundle format")
    payload = {k: v for k, v in bundle.items() if k != "id"}
    check(sha(encoded(payload)) == bundle["id"], "Publication hash mismatch")
    evidence = bundle["evidence"]
    responses = {}
    for identity, item in evidence.items():
        raw = item["body"].encode()
        check(sha(raw) == identity == item["sha256"], "Raw response hash mismatch")
        check(len(raw) == item["bytes"], "Raw response length mismatch")
        check(
            item["source_url"].startswith("https://api.stlouisfed.org/fred/"),
            "Unapproved source",
        )
        check("api_key" not in item["params"], "A source request contains a credential")
        responses[identity] = json.loads(raw)
    tracks = {s["id"]: s for s in bundle["series"]}
    maps = {}
    check(
        len({s["id"] for s in bundle["snapshots"]}) == len(bundle["snapshots"]),
        "Duplicate snapshot identity",
    )
    for snapshot in bundle["snapshots"]:
        series = tracks[snapshot["series_id"]]
        check(
            snapshot["information_date"] <= bundle["as_of"],
            "Information date after collection cutoff",
        )
        rows, metadata = [], []
        total = None
        for identity in snapshot["evidence"]:
            cap, data = evidence[identity], responses[identity]
            check(
                cap["params"]["series_id"] == series["id"],
                "Evidence belongs to another series",
            )
            check(
                data["realtime_start"]
                == data["realtime_end"]
                == snapshot["information_date"],
                "Evidence has another information date",
            )
            if cap["source_url"].endswith("/series/observations"):
                check(
                    data["units"] == "lin" and data["output_type"] == 1,
                    "Unexpected source transformation",
                )
                check(int(data["offset"]) == len(rows), "Observation page gap")
                check(
                    total is None or total == data["count"],
                    "Observation count changed between pages",
                )
                total = data["count"]
                for r in data["observations"]:
                    check(
                        r["realtime_start"]
                        == r["realtime_end"]
                        == snapshot["information_date"],
                        "Row has another information date",
                    )
                    rows.append({"date": r["date"], "value": r["value"]})
            elif cap["source_url"].endswith("/series"):
                metadata.extend(data["seriess"])
        check(
            rows == snapshot["observations"] and len(rows) == total,
            "Normalized rows differ from raw evidence",
        )
        check(
            len(metadata) == 1 and metadata[0]["id"] == series["id"],
            "Metadata identity mismatch",
        )
        meta = metadata[0]
        check(
            meta["units"] == series["unit"]
            and meta["seasonal_adjustment_short"] == series["adjustment"],
            "Unit or adjustment mismatch",
        )
        step = 1 if series["frequency"] == "monthly" else 3
        check(
            meta["frequency_short"] == ("M" if step == 1 else "Q"), "Frequency mismatch"
        )
        check(
            rows[0]["date"] == snapshot["observation_start"]
            and rows[-1]["date"] == snapshot["observation_end"],
            "Declared observation bounds differ",
        )
        check(
            rows[-1]["date"] == meta["observation_end"],
            "Last published period is missing",
        )
        check(
            [r["date"] for r in rows] == grid(rows[0]["date"], rows[-1]["date"], step),
            "Calendar gap in complete snapshot",
        )
        check(
            all(r["value"] != "." for r in rows),
            "Missing observation in complete snapshot",
        )
        maps[snapshot["id"]] = {r["date"]: Decimal(r["value"]) for r in rows}
    return maps, responses


def calculate_rows(bundle, recipe, maps):
    check(
        recipe["schema_version"] == "research-comparison/1"
        and recipe["bundle_id"] == bundle["id"],
        "Recipe publication mismatch",
    )
    check(recipe["comparison"] == "strictly_above", "Unknown threshold rule")
    track = next(s for s in bundle["series"] if s["id"] == recipe["series_id"])
    snapshots = {s["id"]: s for s in bundle["snapshots"]}
    a, b = recipe["before_snapshot"], recipe["after_snapshot"]
    check(
        snapshots[a]["series_id"] == snapshots[b]["series_id"] == track["id"],
        "Mixed input series",
    )
    check(recipe["operation"] == track["operation"], "Unapproved transformation")
    step = 1 if track["frequency"] == "monthly" else 3
    dates = grid(recipe["observation_start"], recipe["observation_end"], step)
    check(len(dates) <= 60, "Recipe period budget exceeded")
    check(step == 1 or int(dates[0][5:7]) in (1, 4, 7, 10), "Invalid quarter anchor")
    threshold = Decimal(str(recipe["threshold"]))
    check(threshold.is_finite() and abs(threshold) <= 10000, "Invalid threshold")
    result = []
    with localcontext() as context:
        context.prec = 28
        for period in dates:
            previous = shift(period, -step)
            x, y, p, q = (
                maps[a].get(period),
                maps[b].get(period),
                maps[a].get(previous),
                maps[b].get(previous),
            )
            keys = [period] if track["operation"] == "level" else [period, previous]
            citations = []
            for identifier in (a, b):
                snapshot = snapshots[identifier]
                for d in keys:
                    if d in maps[identifier]:
                        cap = next(
                            h
                            for h in snapshot["evidence"]
                            if bundle["evidence"][h]["source_url"].endswith(
                                "/observations"
                            )
                        )
                        citations.append(
                            (
                                identifier,
                                snapshot["information_date"],
                                d,
                                maps[identifier][d],
                                cap,
                            )
                        )
            if (
                x is None
                or y is None
                or (
                    track["operation"] != "level"
                    and (
                        p is None
                        or q is None
                        or (track["operation"] == "pct_change" and (p == 0 or q == 0))
                    )
                )
            ):
                result.append(
                    dict(
                        period=period,
                        initial=None,
                        revised=None,
                        revision=None,
                        current_contribution=None,
                        previous_contribution=None,
                        switched=None,
                        citations=citations,
                    )
                )
                continue
            initial, revised, current, prior = x, y, y - x, Decimal(0)
            if track["operation"] == "difference":
                initial, revised, prior = x - p, y - q, p - q
            elif track["operation"] == "pct_change":
                initial, revised = (x / p - 1) * 100, (y / q - 1) * 100
                # Average the two exact orders of replacing the changed inputs.
                order_a = ((y / p - 1) * 100 - initial, revised - (y / p - 1) * 100)
                order_b = (revised - (x / q - 1) * 100, (x / q - 1) * 100 - initial)
                current, prior = (order_a[0] + order_b[0]) / 2, (
                    order_a[1] + order_b[1]
                ) / 2
            close(
                current + prior,
                revised - initial,
                "Input attribution does not reconcile",
            )
            result.append(
                dict(
                    period=period,
                    initial=initial,
                    revised=revised,
                    revision=revised - initial,
                    current_contribution=current,
                    previous_contribution=prior,
                    switched=(initial > threshold) != (revised > threshold),
                    citations=citations,
                )
            )
    return result


def verify_comparison(bundle, recipe, recorded, maps):
    rows = calculate_rows(bundle, recipe, maps)
    check(len(recorded["rows"]) == len(rows), "Result population mismatch")
    for expected, actual in zip(rows, recorded["rows"]):
        check(
            actual["period"] == expected["period"]
            and actual["switched"] == expected["switched"],
            "Result period or classification mismatch",
        )
        for metric in (
            "initial",
            "revised",
            "revision",
            "current_contribution",
            "previous_contribution",
        ):
            close(
                actual[metric],
                expected[metric],
                f"Replayed {metric} differs at {expected['period']}",
            )
        found = [
            (
                c["snapshot"],
                c["information_date"],
                c["observation_date"],
                Decimal(c["value"]),
                c["capture"],
            )
            for c in actual["citations"]
        ]
        check(found == expected["citations"], "Exact-input citations differ")
    return len(rows)


def verify_study(bundle, maps, responses):
    study = bundle["study"]
    plan = study["plan"]
    check(sha(encoded(plan)) == study["plan_hash"], "Study plan hash mismatch")
    expected_periods = grid(plan["observation_start"], plan["observation_end"])
    check(
        [r["period"] for r in study["rows"]] == expected_periods,
        "Study omitted a planned month",
    )
    firsts = {
        r["date"]: r
        for h, d in responses.items()
        if d.get("output_type") == 4
        for r in d["observations"]
    }
    revisions = []
    for row in study["rows"]:
        if row["status"] == "excluded":
            check(bool(row.get("reason")), "Excluded month lacks a reason")
            continue
        period, prior = row["period"], shift(row["period"], -1)
        a, b = maps[row["before_snapshot"]], maps[row["after_snapshot"]]
        check(
            firsts[period]["realtime_start"] == row["initial_date"],
            "Initial information date differs from source archive",
        )
        check(
            Decimal(firsts[period]["value"]) == a[period],
            "Initial source level differs",
        )
        check(
            row["revised_date"] == plan["comparison_information_date"],
            "Comparison cutoff moved",
        )
        initial, revised = a[period] - a[prior], b[period] - b[prior]
        close(row["initial"], initial, "Initial study value differs")
        close(row["revised"], revised, "Revised study value differs")
        close(row["revision"], revised - initial, "Study revision differs")
        for key, v in zip(
            (
                "initial_current",
                "initial_previous",
                "revised_current",
                "revised_previous",
            ),
            (a[period], a[prior], b[period], b[prior]),
        ):
            close(row["inputs"][key], v, "Study input citation differs")
        close(
            row["attribution"]["current_level"],
            b[period] - a[period],
            "Current contribution differs",
        )
        close(
            row["attribution"]["previous_level"],
            a[prior] - b[prior],
            "Prior contribution differs",
        )
        revisions.append(float(revised - initial))

    def summary(rows, actual):
        included = [r for r in rows if r["status"] == "included"]
        values = [float(r["revision"]) for r in included]
        check(
            actual["n"] == len(included)
            and actual["planned"] == len(rows)
            and actual["excluded"] == len(rows) - len(included),
            "Summary denominator differs",
        )
        for key, expected in {
            "initial_mean": mean(float(r["initial"]) for r in included),
            "revised_mean": mean(float(r["revised"]) for r in included),
            "mean_revision": mean(values),
            "median_revision": median(values),
            "mean_absolute_revision": mean(map(abs, values)),
            "largest_absolute_revision": max(map(abs, values)),
            "upward_revisions": sum(v > 0 for v in values),
            "downward_revisions": sum(v < 0 for v in values),
            "unchanged": sum(v == 0 for v in values),
        }.items():
            close(actual[key], expected, f"Study summary differs: {key}")
        check(
            [t["threshold"] for t in actual["thresholds"]] == plan["thresholds"],
            "A planned threshold is missing",
        )
        for t in actual["thresholds"]:
            flags = [
                (
                    Decimal(r["initial"]) > t["threshold"],
                    Decimal(r["revised"]) > t["threshold"],
                )
                for r in included
            ]
            expected = dict(
                initial_above=sum(a for a, b in flags),
                revised_above=sum(b for a, b in flags),
                switches=sum(a != b for a, b in flags),
                to_above=sum(not a and b for a, b in flags),
                from_above=sum(a and not b for a, b in flags),
            )
            for k, v in expected.items():
                check(t[k] == v, f"Threshold result differs: {k}")

    summary(study["rows"], study["summary"])
    for by_year in study["by_year"]:
        summary(
            [r for r in study["rows"] if r["period"].startswith(str(by_year["year"]))],
            by_year,
        )
    # Recreate the published block resampling using independently read source values.
    spec = plan["uncertainty"]
    for interval in study["uncertainty"].get("intervals", []):
        block = interval["block_months"]
        rng = random.Random(spec["seed"] + block)
        n = len(revisions)
        samples = []
        absolute = []
        switch_shares = {t: [] for t in plan["thresholds"]}
        for _ in range(spec["replicates"]):
            indices = []
            for _ in range(math.ceil(n / block)):
                beginning = rng.randrange(n)
                indices += [(beginning + j) % n for j in range(block)]
            indices = indices[:n]
            samples.append(sum(revisions[i] for i in indices) / n)
            absolute.append(sum(abs(revisions[i]) for i in indices) / n)
            for t in switch_shares:
                switch_shares[t].append(
                    sum(
                        (Decimal(study["rows"][i]["initial"]) > t)
                        != (Decimal(study["rows"][i]["revised"]) > t)
                        for i in indices
                    )
                    / n
                )

        def bounds(values):
            values.sort()
            result = []
            for p in (0.025, 0.975):
                k = p * (len(values) - 1)
                low = int(k)
                result.append(
                    values[low] + (values[math.ceil(k)] - values[low]) * (k - low)
                )
            return result

        for key, values in (
            ("mean_revision", samples),
            ("mean_absolute_revision", absolute),
        ):
            for actual, expected in zip(interval[key], bounds(values)):
                close(actual, expected, "Resampling interval differs")
        for t in interval["switch_share"]:
            for actual, expected in zip(
                t["interval"], bounds(switch_shares[t["threshold"]])
            ):
                close(actual, expected, "Switch-share interval differs")
    return len(study["rows"])


def replay(document):
    bundle = document.get("bundle", document)
    maps, responses = verify_sources(bundle)
    periods = verify_study(bundle, maps, responses) if bundle.get("study") else 0
    comparisons = (
        verify_comparison(bundle, document["recipe"], document["result"], maps)
        if document.get("schema_version") == "research-replay/1"
        else 0
    )
    return dict(
        status="verified",
        publication=bundle["id"],
        snapshots=len(maps),
        source_responses=len(responses),
        study_periods=periods,
        comparison_periods=comparisons,
        network_requests=0,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    try:
        for filename in sys.argv[1:]:
            print(json.dumps(replay(json.loads(Path(filename).read_text()))))
    except (ValueError, KeyError, StopIteration, TypeError) as error:
        raise SystemExit(f"Replay failed: {error}") from None

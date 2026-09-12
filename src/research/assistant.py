"""Bounded research assistant with deterministic answers and resolvable citations.

No arbitrary prompts are sent to an external model. Supported intents query actual
workspace records. Optional prose generation can be added without relaxing these facts.
"""

from decimal import Decimal

from .service import Research


def answer(store, workspace, question, run_ids):
    if len(question) > 2000 or len(run_ids) > 2:
        raise ValueError("Question exceeds assistant budget")
    research = Research(store)
    runs = [research.get_run(workspace, r) for r in run_ids]
    lower = question.lower()
    if any(
        s in lower
        for s in (
            "trade",
            "buy",
            "sell",
            "guarantee",
            "password",
            "execute",
            "ignore previous",
            "other workspace",
        )
    ):
        return {
            "status": "abstained",
            "answer": "This assistant only explains saved research data and revisions.",
            "facts": [],
            "citations": [],
        }
    import re

    if "platform" in lower or "publish" in lower:
        year = re.search(r"\b(20\d{2})\b", lower)
        if year:
            pubs = store.control.list(workspace, "publication")
            if not any(p["created_at"].startswith(year[1]) for p in pubs):
                period = ("April " if "april" in lower else "") + year[1]
                return {
                    "status": "answered",
                    "answer": f"No recorded platform publication is available for {period}. Imported source vintages were collected later.",
                    "facts": [],
                    "citations": [],
                }
        return {
            "status": "abstained",
            "answer": "A publication check requires a year with recorded publication evidence. Source vintages alone are insufficient.",
            "facts": [],
            "citations": [],
        }
    if not re.search(
        r"\b(revision|revisions|revised|changed|change|compare|comparison|difference|estimate|estimates|value|values|data|observations|growth|gdp|unit|units|source|evidence|threshold|saved|result|results)\b",
        lower,
    ):
        return {
            "status": "abstained",
            "answer": "I can explain saved values, comparisons and their source evidence. This question is outside that scope.",
            "facts": [],
            "citations": [],
        }
    citations = []
    for run in runs:
        for inp in run["inputs"]:
            for cap_id in inp["evidence_ids"]:
                cap = store.control.get(workspace, "capture", cap_id)
                citations.append(
                    {
                        "id": cap_id,
                        "url": cap["url"],
                        "first_seen_at": cap["first_seen_at"],
                        "body_hash": cap["body"],
                    }
                )
    if len(runs) == 2:
        comparison = research.comparison(workspace, *run_ids)
        facts = [
            {
                "calculation_id": f'{run_ids[0]}:{run_ids[1]}:{r["date"]}',
                **r,
                "unit": comparison["unit"],
            }
            for r in comparison["data"][-100:]
            if r["change"] is not None
        ]
        if not facts:
            return {
                "status": "abstained",
                "answer": "No comparable non-missing observations in these saved runs.",
                "facts": [],
                "citations": citations,
            }
        f = facts[-1]
        # Values come only from the deterministic comparison, never extracted from prose.
        assert Decimal(f["after"]) - Decimal(f["before"]) == Decimal(f["change"])
        display_unit = (
            "percentage points"
            if comparison["unit"].startswith("percent")
            else comparison["unit"]
        )
        wording = f"For {f['date']}, the saved value changed from {f['before']} to {f['after']} ({f['change']} {display_unit}). {comparison['attribution']}. Source data alone does not establish an economic cause."
        return {
            "status": "answered",
            "answer": wording,
            "facts": facts,
            "citations": citations,
            "tool_calls": len(runs) + 1,
        }
    if len(runs) == 1:
        run = runs[0]
        return {
            "status": "answered",
            "answer": "These are the exact observations calculated in the selected saved analysis. Opening it does not refresh its data.",
            "facts": [
                {"calculation_id": run["id"], **r, "unit": run["result"]["unit"]}
                for r in run["result"]["data"][-100:]
            ],
            "citations": citations,
            "tool_calls": 1,
        }
    return {
        "status": "abstained",
        "answer": "Select one saved analysis to inspect, or two to explain a revision.",
        "facts": [],
        "citations": [],
    }

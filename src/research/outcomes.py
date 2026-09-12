"""Immutable matured outcomes with explicit price evidence and correction versions."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, now
from .control import Conflict
from .storage import canonical, digest


class Outcome(Contract):
    signal_date: date
    model_run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    target: str = Field(min_length=1, max_length=100)
    entry_date: date
    exit_date: date
    entry_price: Decimal = Field(gt=0)
    exit_price: Decimal = Field(gt=0)
    price_capture_id: str
    entry_rule: Literal["first close strictly after signal date"] = (
        "first close strictly after signal date"
    )

    @model_validator(mode="after")
    def order(self):
        if not self.signal_date < self.entry_date < self.exit_date:
            raise ValueError("Outcome requires signal < entry < exit")
        if str(self.exit_date) > now()[:10]:
            raise ValueError("Outcome has not matured")
        return self


def record_outcome(store, workspace, outcome):
    store.control.get(workspace, "model_run", outcome.model_run_id)
    capture = store.control.get(workspace, "capture", outcome.price_capture_id)
    if capture["first_seen_at"][:10] < str(outcome.exit_date):
        raise ValueError("Price capture predates outcome maturity")
    prices = store.objects.json(capture["body"])
    if (
        prices.get("schema_version") != "adjusted-close/1"
        or prices.get("target") != outcome.target
    ):
        raise ValueError("Outcome needs a matching adjusted-close price capture")
    by_date = {p["date"]: Decimal(str(p["value"])) for p in prices["prices"]}
    if len(by_date) != len(prices["prices"]):
        raise ValueError("Duplicate price dates")
    eligible = sorted(d for d in by_date if d > str(outcome.signal_date))
    if not eligible or eligible[0] != str(outcome.entry_date):
        raise ValueError("Entry must be the first captured close after signal")
    if (
        by_date.get(str(outcome.entry_date)) != outcome.entry_price
        or by_date.get(str(outcome.exit_date)) != outcome.exit_price
    ):
        raise ValueError("Outcome prices disagree with captured evidence")
    body = outcome.model_dump(mode="json")
    body["return_pct"] = str((outcome.exit_price / outcome.entry_price - 1) * 100)
    # Signal identity deliberately excludes repeated computation timestamps.
    signal = digest(
        canonical(
            {
                k: body[k]
                for k in (
                    "signal_date",
                    "target",
                    "entry_rule",
                    "entry_date",
                    "exit_date",
                )
            }
        )
    )
    identifier = digest(canonical(body))
    for _ in range(8):
        try:
            with store.control.transaction() as tx:
                try:
                    head = store.control.get(workspace, "outcome_head", signal, tx)
                except KeyError:
                    head = None
                saved = store.control.put(
                    workspace,
                    "outcome",
                    identifier,
                    {
                        **body,
                        "signal_key": signal,
                        "first_matured_id": head["first"] if head else identifier,
                        "correction_of": head["latest"] if head else None,
                    },
                    connection=tx,
                )
                store.control.put(
                    workspace,
                    "outcome_head",
                    signal,
                    {
                        "first": head["first"] if head else identifier,
                        "latest": identifier,
                    },
                    head["version"] if head else None,
                    tx,
                )
                return saved
        except Conflict:
            try:
                return store.control.get(workspace, "outcome", identifier)
            except KeyError:
                continue
    raise Conflict("Concurrent outcome update; retry")


def outcome_summary(store, workspace):
    records = store.control.list(workspace, "outcome")
    first = [r for r in records if r["first_matured_id"] == r["id"]]
    return {
        "outcome_versions": len(records),
        "distinct_signal_dates": len({r["signal_date"] for r in first}),
        "first_matured_outcomes": first,
        "interpretation": "descriptive; no forecast superiority claim",
        "performance_gate": "Requires frozen predictions, non-overlapping splits, target-specific baselines and uncertainty before evaluating forecast skill",
    }

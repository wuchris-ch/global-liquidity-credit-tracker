"""Strict public contracts. Dates describe source evidence, never collection time."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Series(Contract):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_:./-]+$")
    name: str = Field(min_length=1, max_length=300)
    source: Literal["fred", "bis", "worldbank", "nyfed", "fixture", "legacy"]
    source_id: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=1, max_length=20)
    unit: str = Field(min_length=1, max_length=100)
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "annual"]
    dimensions: dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=10000)
    source_url: str = ""
    redistribution: Literal["allowed", "personal_only", "unreviewed"] = "unreviewed"


class Observation(Contract):
    date: date
    value: Decimal | None
    status: Literal["observed", "missing", "retracted"] = "observed"
    attributes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self):
        if (self.value is None) != (self.status != "observed"):
            raise ValueError(
                "Missing/retracted rows require null; observed rows require finite values"
            )
        return self


class Scope(Contract):
    start: date
    end: date
    information_date: date
    mode: Literal[
        "source_vintage",
        "forward_capture",
        "reconstructed_current_vintage",
        "archive_edition",
    ]
    precision: Literal["date", "archive_edition", "unknown"] = "date"
    complete: bool = True

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("Start must not follow end")
        return self


class Query(Contract):
    series_id: str = Field(max_length=200)
    start: date
    end: date
    as_of: str
    basis: Literal["source", "platform"] = "source"
    dataset: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    allow_partial: bool = False

    @model_validator(mode="after")
    def valid_range(self):
        if self.start > self.end:
            raise ValueError("Start must not follow end")
        if self.basis == "source":
            date.fromisoformat(self.as_of)  # No fabricated intraday precision.
        else:
            self.as_of = timestamp(self.as_of)
        return self


class Recipe(Contract):
    title: str = Field(min_length=1, max_length=200)
    queries: list[Query] = Field(min_length=1, max_length=10)
    operation: Literal[
        "level",
        "difference",
        "pct_change",
        "annualized_growth",
        "rolling_mean",
        "zscore",
        "spread",
        "ratio",
        "net_liquidity",
    ] = "level"
    window: int = Field(default=1, ge=1, le=520)
    periods_per_year: int = Field(default=4, ge=1, le=366)
    threshold: Decimal | None = None

    @model_validator(mode="after")
    def arity(self):
        required = {"spread": 2, "ratio": 2, "net_liquidity": 3}.get(self.operation, 1)
        if len(self.queries) != required:
            raise ValueError(f"{self.operation} requires {required} input series")
        return self


class Note(Contract):
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(min_length=1, max_length=10000)


class Watchlist(Contract):
    name: str = Field(min_length=1, max_length=200)
    series_ids: list[str] = Field(default_factory=list, max_length=100)


class Release(Contract):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    series_ids: list[str] = Field(max_length=100)
    expected_at: str
    observed_at: str | None = None
    source_url: str
    state: Literal["scheduled", "released", "cancelled"] = "scheduled"

    @field_validator("expected_at", "observed_at")
    @classmethod
    def aware(cls, v):
        return timestamp(v) if v else v

    @model_validator(mode="after")
    def release_state(self):
        if self.state == "released" and self.observed_at is None:
            raise ValueError("Released state requires an observed release timestamp")
        if self.state == "scheduled" and self.observed_at is not None:
            raise ValueError("Observed releases cannot remain scheduled")
        return self

"""Recorded-response integration and failure recovery for the public release loop."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.replay_release_lab import replay
from src.research.contracts import Query
from src.research.ingestion import TransientSourceError
from src.research.operations import backup, restore
from src.research.release_lab import (
    capture_release,
    live_bundle,
    reconcile_releases,
    write_bundle,
)
from src.research.release_sources import WORKSPACE, paged, periods, release_inventory
from src.research.revision_study import summarize, uncertainty
from src.research.storage import ResearchStore, canonical

ROOT = Path(__file__).resolve().parents[2]
STUDY = json.loads((ROOT / "frontend/src/lib/release-study.json").read_text())
FEED = json.loads((ROOT / "frontend/src/lib/release-feed.json").read_text())


class RecordedTransport:
    """Serve exact captured HTTP bytes; faults explicitly modify a copy."""

    def __init__(self, store, mutate=None):
        self.store, self.mutate, self.calls = store, mutate, []
        self.evidence = list(STUDY["evidence"].values()) + list(
            FEED["evidence"].values()
        )

    def get(self, url, params):
        safe = {k: v for k, v in params.items() if k != "api_key"}
        self.calls.append((url, safe))
        matches = [
            e
            for e in self.evidence
            if e["source_url"] == url
            and all(str(e["params"].get(k)) == str(v) for k, v in safe.items())
        ]
        assert matches, f"No recorded response for {url} {safe}"
        data = json.loads(matches[-1]["body"])
        if self.mutate:
            data = self.mutate(url, safe, data)
        raw = canonical(data) if self.mutate else matches[-1]["body"].encode()
        capture = self.store.capture(WORKSPACE, url, safe, raw)
        return data, capture["id"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "recorded-response-test-key")
    return ResearchStore(tmp_path / "store")


def test_every_public_snapshot_and_study_outcome_replays():
    study = replay(STUDY)
    assert study["study_periods"] == 24 and study["source_responses"] == 51
    assert replay(FEED)["snapshots"] == 9
    assert len(STUDY["study"]["uncertainty"]["intervals"]) == 2
    # Independently read BLS's first-estimate table, checked 2026-09-12.
    # https://www.bls.gov/web/empsit/cesnaicsrev.htm
    assert [int(r["initial"]) for r in STUDY["study"]["rows"]] == [
        517,
        311,
        236,
        253,
        339,
        209,
        187,
        187,
        336,
        150,
        199,
        216,
        353,
        275,
        303,
        175,
        272,
        206,
        114,
        142,
        254,
        12,
        227,
        256,
    ]


@pytest.mark.parametrize(
    "series,vintage",
    [
        ("PAYEMS", "2023-02-03"),
        ("INDPRO", "2026-08-18"),
        ("A191RL1Q225SBEA", "2026-07-30"),
    ],
)
def test_recorded_observations_ingest_with_verified_metadata(store, series, vintage):
    identity = capture_release(store, series, vintage, RecordedTransport(store))
    snapshot = store.control.get(WORKSPACE, "release_snapshot", identity)
    assert snapshot["information_date"] == vintage
    if series == "A191RL1Q225SBEA":
        assert snapshot["observation_start"] == "2023-01-01"
    assert len(store.control.list(WORKSPACE, "manifest")) == 1


def test_missed_runs_calendar_delay_and_utc_midnight(store):
    transport = RecordedTransport(store)
    reconcile_releases(store, today="2026-09-12", transport=transport)
    jobs = store.control.list(WORKSPACE, "job")
    assert len(jobs) == 9  # All vintage changes since June, including missed polls.
    assert not any(j["payload"]["information_date"] == "2026-08-26" for j in jobs)
    gdp = store.control.get(WORKSPACE, "release_inventory", "A191RL1Q225SBEA")
    assert "2026-08-26" in gdp["calendar"] and "2026-08-26" not in gdp["vintages"]
    assert gdp["source_as_of"] == "2026-09-11"
    assert all(
        p["realtime_end"] == "2026-09-11"
        for u, p in transport.calls
        if u.endswith("/vintagedates")
    )
    reconcile_releases(store, today="2026-09-12", transport=transport)
    assert len(store.control.list(WORKSPACE, "job")) == len(jobs)


@pytest.mark.parametrize(
    "fault",
    [
        "unit",
        "frequency",
        "adjustment",
        "missing",
        "missing_tail",
        "duplicate",
        "vintage",
        "pagination",
    ],
)
def test_partial_or_changed_contract_never_commits(store, fault):
    def mutate(url, params, data):
        if url.endswith("/series"):
            if fault == "unit":
                data["seriess"][0]["units"] = "Persons"
            if fault == "frequency":
                data["seriess"][0]["frequency_short"] = "Q"
            if fault == "adjustment":
                data["seriess"][0]["seasonal_adjustment_short"] = "NSA"
        if url.endswith("/observations"):
            if fault == "missing":
                data["observations"][-1]["value"] = "."
            if fault == "missing_tail":
                data["observations"].pop()
                data["count"] -= 1
            if fault == "duplicate":
                data["observations"][-1] = data["observations"][0]
            if fault == "vintage":
                data["realtime_end"] = "2023-02-04"
            if fault == "pagination":
                data["offset"] = 1
        return data

    with pytest.raises(ValueError):
        capture_release(store, "PAYEMS", "2023-02-03", RecordedTransport(store, mutate))
    assert not store.control.list(WORKSPACE, "manifest")
    assert store.control.list(WORKSPACE, "capture")  # Rejected raw evidence retained.


def test_conflicting_same_vintage_is_quarantined_and_new_vintage_is_additive(store):
    first = capture_release(store, "PAYEMS", "2023-02-03", RecordedTransport(store))
    old = store.control.get(WORKSPACE, "head", "current")["manifest"]

    def correction(url, params, data):
        if url.endswith("/observations"):
            data["observations"][-1]["value"] = str(
                int(data["observations"][-1]["value"]) + 1
            )
        return data

    with pytest.raises(ValueError, match="Conflicting historical snapshot"):
        capture_release(
            store, "PAYEMS", "2023-02-03", RecordedTransport(store, correction)
        )
    assert store.control.get(WORKSPACE, "head", "current")["manifest"] == old
    second = capture_release(store, "PAYEMS", "2023-03-10", RecordedTransport(store))
    assert (
        first != second and len(store.control.list(WORKSPACE, "release_snapshot")) == 2
    )
    # An earlier pinned manifest still queries the same historical rows.
    result = store.query(
        WORKSPACE,
        Query(
            series_id="PAYEMS",
            start="2022-12-01",
            end="2023-01-01",
            as_of="2023-02-03",
            dataset=old,
        ),
    )
    assert result["data"][-1]["value"] == "155073"


def test_concurrent_duplicate_captures_commit_once(store):
    def run(_):
        return capture_release(store, "PAYEMS", "2023-02-03", RecordedTransport(store))

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(run, range(8)))
    assert len(set(identifiers)) == 1
    assert len(store.control.list(WORKSPACE, "release_snapshot")) == 1
    assert len(store.manifest(WORKSPACE)[1]["snapshots"]) == 1


def populate_feed(store):
    transport = RecordedTransport(store)
    reconcile_releases(store, today="2026-09-12", transport=transport)
    for snapshot in FEED["snapshots"]:
        capture_release(
            store, snapshot["series_id"], snapshot["information_date"], transport
        )
    return transport


def test_discovery_failure_retains_complete_publication_and_explains_it(store):
    populate_feed(store)
    previous = live_bundle(store, as_of="2026-09-12")

    class Unavailable:
        def get(self, *_):
            raise TransientSourceError("temporary source outage")

    reconcile_releases(store, today="2026-09-12", transport=Unavailable())
    current = live_bundle(store, as_of="2026-09-12")
    assert current["snapshots"] == previous["snapshots"]
    assert sum(i["status"] == "discovery_held" for i in current["inbox"]) == 3
    assert any(
        i["date"] == "2026-08-26" and i["status"] == "awaiting_vintage"
        for i in current["inbox"]
    )
    # A study cutoff between releases must never become a new release date.
    capture_release(store, "PAYEMS", "2026-09-11", RecordedTransport(store))
    assert all(
        s["information_date"] != "2026-09-11" for s in live_bundle(store)["snapshots"]
    )


def test_backup_restore_and_immutable_publication_recovery(store, tmp_path):
    populate_feed(store)
    bundle = live_bundle(store, as_of="2026-09-12")
    destination = tmp_path / "backup"
    backup(store, destination)
    recovered = ResearchStore(tmp_path / "recovered")
    restore(recovered, destination)
    assert (
        live_bundle(recovered, as_of="2026-09-12")["snapshots"] == bundle["snapshots"]
    )
    assert len(recovered.control.list(WORKSPACE, "job")) == 9
    path = tmp_path / f"{bundle['id']}.json"
    write_bundle(bundle, path)
    old_bytes = path.read_bytes()
    changed = copy.deepcopy(bundle)
    changed["as_of"] = "2026-09-13"
    with pytest.raises(ValueError, match="immutable publication"):
        write_bundle(changed, path)
    assert path.read_bytes() == old_bytes


def test_unstable_calendar_and_association_stop_discovery(store):
    def mutate(url, params, data):
        if url.endswith("/series/release"):
            data["releases"][0]["id"] = 999
        return data

    with pytest.raises(ValueError, match="association"):
        release_inventory(
            RecordedTransport(store, mutate),
            "PAYEMS",
            "2026-06-01",
            "2026-09-12",
            "2026-10-27",
        )

    def wrong_offset(url, params, data):
        if url.endswith("/dates"):
            data["offset"] = 10
        return data

    with pytest.raises(ValueError, match="page count"):
        release_inventory(
            RecordedTransport(store, wrong_offset),
            "PAYEMS",
            "2026-06-01",
            "2026-09-12",
            "2026-10-27",
        )


def test_missing_history_is_an_exclusion_not_a_zero_or_resampling_join():
    rows = copy.deepcopy(STUDY["study"]["rows"])
    rows[4] = {
        "period": rows[4]["period"],
        "status": "excluded",
        "reason": "Initial history unavailable",
    }
    result = summarize(rows, [0, 100, 200])
    assert result["n"] == 23 and result["planned"] == 24 and result["excluded"] == 1
    assert uncertainty(rows, STUDY["study"]["plan"])["status"] == "unavailable"
    assert periods("2022-12-01", "2023-04-01", "quarterly") == [
        "2023-01-01",
        "2023-04-01",
    ]


def test_replay_rejects_tampered_values_and_dropped_months():
    changed = copy.deepcopy(STUDY)
    changed["study"]["rows"].pop()
    with pytest.raises(ValueError, match="hash"):
        replay(changed)


def test_standalone_public_verifier_matches_source():
    assert (ROOT / "frontend/public/research/lab/replay.py").read_bytes() == (
        ROOT / "scripts/replay_release_lab.py"
    ).read_bytes()


def test_reference_classification_uses_source_precision_before_display_rounding():
    case = json.loads(
        (ROOT / "tests/research/fixtures/precision-boundary.json").read_text()
    )
    case["bundle"] = FEED
    assert replay(case)["comparison_periods"] == 1
    assert case["result"]["rows"][0]["switched"] is True


def test_incomplete_study_keeps_draft_evidence_and_previous_publication(
    store, tmp_path, monkeypatch
):
    from scripts import publish_release_lab as publisher
    from src.research.storage import digest

    incomplete = copy.deepcopy(STUDY)
    incomplete["study"]["summary"]["excluded"] = 1
    output = tmp_path / "public"
    write_bundle(STUDY, output / "study.json")
    original = (output / "study.json").read_bytes()
    monkeypatch.setattr(publisher, "ResearchStore", lambda _: store)
    monkeypatch.setattr(publisher, "build_study", lambda _: incomplete)
    monkeypatch.setattr(
        "sys.argv", ["publisher", "--study-only", "--output", str(output)]
    )
    with pytest.raises(ValueError, match="publication held"):
        publisher.main()
    draft_bytes = json.dumps(incomplete, sort_keys=True).encode()
    assert store.objects.read(digest(draft_bytes)) == draft_bytes
    assert (output / "study.json").read_bytes() == original

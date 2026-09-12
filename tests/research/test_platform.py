import json

import pytest
from fastapi.testclient import TestClient

from src.research.api import create_app
from src.research.calculations import calculate
from src.research.contracts import Observation, Query, Recipe, Scope, Series
from src.research.control import Conflict
from src.research.ingestion import fred_snapshot, load_demo
from src.research.operations import backup, restore
from src.research.service import Research, replay
from src.research.storage import CoverageError, ResearchStore, canonical
from src.research.worker import tick


@pytest.fixture
def store(tmp_path):
    return ResearchStore(tmp_path / "research")


@pytest.fixture
def demo(store):
    load_demo(store)
    return store


def query(day="2024-04-25", **kw):
    return Query(
        series_id="fred:A191RL1Q225SBEA",
        start="2024-01-01",
        end="2024-01-01",
        as_of=day,
        **kw,
    )


def make_run(store, day="2024-04-25", workspace="personal"):
    service = Research(store)
    recipe = Recipe(title="Growth", queries=[query(day)], threshold="1.5")
    saved = service.save_recipe(workspace, "tester", recipe)
    job = service.queue_run(workspace, "tester", saved["id"])
    return service.execute(workspace, job["payload"])


def test_authentic_revision_and_replay(demo):
    a, b = make_run(demo), make_run(demo, "2024-05-30")
    s = Research(demo)
    assert a["result"]["data"][0]["threshold_met"] is True
    assert b["result"]["data"][0]["threshold_met"] is False
    assert s.comparison("personal", a["id"], b["id"])["data"][0]["change"] == "-0.3"
    bundle = s.bundle("personal", a["id"])
    assert replay(json.loads(json.dumps(bundle))) == a["result"]
    bundle["inputs"][0]["data"][0]["value"] = "999"
    with pytest.raises(ValueError, match="integrity"):
        replay(bundle)


def test_historical_coverage_is_not_fabricated(demo):
    with pytest.raises(CoverageError):
        demo.query("personal", query("2024-04-26"))
    with pytest.raises(CoverageError):
        demo.query("personal", query("2024-04-25T12:00:00Z", basis="platform"))
    with pytest.raises(ValueError):
        query("2024-04-25T12:00:00Z")
    with pytest.raises(ValueError):
        query("2024-04-25T12:00:00", basis="platform")
    with pytest.raises(CoverageError):
        demo.query(
            "personal",
            Query(
                series_id=query().series_id,
                start="2023-01-01",
                end="2024-01-01",
                as_of="2024-04-25",
            ),
        )


def test_pin_and_workspace_isolation(demo):
    result = demo.query("personal", query())
    manifest = result["dataset_manifest"]
    with pytest.raises(KeyError):
        demo.manifest("stranger", manifest)
    with pytest.raises(CoverageError):
        demo.query("stranger", query())
    assert demo.query("personal", query(dataset=manifest))["data"] == result["data"]


def test_capture_redaction_and_hash_integrity(store):
    cap = store.capture(
        "personal",
        "https://user:password@example.org/data?api_key=secret",
        {"api_key": "secret", "Authorization": "token", "offset": 0},
        b"{}",
    )
    assert "secret" not in json.dumps(cap) and "password" not in json.dumps(cap)
    assert cap["params"] == {"offset": 0}
    other = store.capture("personal", "https://example.org/data", {}, b"{}")
    assert other["body"] == cap["body"] and other["id"] != cap["id"]
    store.objects.path(cap["body"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.objects.read(cap["body"])


def test_duplicate_and_conflicting_snapshot(demo):
    first = demo.manifest("personal")[0]
    load_demo(demo)
    assert demo.manifest("personal")[0] == first
    _, m = demo.manifest("personal")
    s = m["snapshots"][0]
    with pytest.raises(ValueError, match="Conflicting"):
        demo.ingest(
            "personal",
            Series.model_validate(s["series"]),
            Scope.model_validate(s["scope"]),
            [Observation(date="2024-01-01", value="999")],
            s["captures"],
        )


def test_null_and_country_identity(store):
    for country in ("USA", "CAN"):
        s = Series(
            id="wb:" + country,
            name=country,
            source="worldbank",
            source_id="GDP",
            country=country,
            unit="USD",
            frequency="annual",
        )
        cap = store.capture("personal", "https://example.org", {}, b"{}")
        store.ingest(
            "personal",
            s,
            Scope(
                start="2024-12-31",
                end="2024-12-31",
                information_date="2025-01-01",
                mode="forward_capture",
            ),
            [Observation(date="2024-12-31", value=None, status="missing")],
            [cap["id"]],
        )
    assert len(store.catalog("personal")) == 2
    with pytest.raises(ValueError):
        Observation(date="2024-01-01", value=None)
    with pytest.raises(ValueError):
        Observation(date="2024-01-01", value="Infinity")


def test_jobs_idempotency_leases_and_recovery(store):
    c = store.control
    a = c.enqueue("personal", "one", "test", {"x": 1})
    assert c.enqueue("personal", "one", "test", {"x": 1}) == a
    with pytest.raises(Conflict):
        c.enqueue("personal", "one", "test", {"x": 2})
    lease = c.claim("personal", "worker-a", lease_seconds=-1)
    new = c.claim("personal", "worker-b")
    assert new["generation"] == 2
    with pytest.raises(Conflict):
        c.finish("personal", lease, "succeeded")
    assert c.finish("personal", new, "succeeded")["status"] == "succeeded"
    assert c.claim("personal", "worker-c") is None


def test_transactional_head_failure_retains_old(demo, monkeypatch):
    before = demo.manifest("personal")[0]
    original = demo.control.put

    def fail(workspace, kind, *args, **kwargs):
        if kind == "head":
            raise RuntimeError("injected crash")
        return original(workspace, kind, *args, **kwargs)

    monkeypatch.setattr(demo.control, "put", fail)
    s = Series(
        id="fixture:new",
        name="New",
        source="fixture",
        source_id="new",
        country="USA",
        unit="USD",
        frequency="annual",
    )
    cap = demo.capture("personal", "https://example.org", {}, b"{}")
    with pytest.raises(RuntimeError):
        demo.ingest(
            "personal",
            s,
            Scope(
                start="2020-01-01",
                end="2020-01-01",
                information_date="2021-01-01",
                mode="forward_capture",
            ),
            [Observation(date="2020-01-01", value="1")],
            [cap["id"]],
        )
    assert demo.manifest("personal")[0] == before
    assert len(demo.control.list("personal", "manifest")) == 2


def test_exports_rights_and_restore(demo, tmp_path):
    run = make_run(demo)
    service = Research(demo)
    for fmt in ("csv", "json", "html", "parquet"):
        content, mime = service.export("personal", run["id"], fmt)
        assert content and mime
    backup(demo, tmp_path / "backup")
    target = ResearchStore(tmp_path / "restored")
    restore(target, tmp_path / "backup")
    assert Research(target).get_run("personal", run["id"])["result"] == run["result"]
    with pytest.raises(ValueError, match="empty"):
        restore(target, tmp_path / "backup")


def test_unit_safety_and_future_perturbation():
    inp = {
        "series": {"unit": "USD"},
        "data": [{"date": str(d), "value": str(d)} for d in range(1, 5)],
    }
    recipe = Recipe(title="mean", queries=[query()], operation="rolling_mean", window=2)
    a = calculate(recipe, [inp])
    inp["data"].append({"date": "5", "value": "100000"})
    b = calculate(recipe, [inp])
    assert a["data"] == b["data"][:4]
    spread = Recipe(title="spread", queries=[query(), query()], operation="spread")
    with pytest.raises(ValueError, match="matching units"):
        calculate(spread, [inp, {"series": {"unit": "JPY"}, "data": []}])


def test_fred_pages_and_missing(store, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "secret")

    class Mock:
        def get(self, url, params):
            if url.endswith("/series"):
                body = {
                    "seriess": [
                        {"id": "test", "units": "Percent", "frequency_short": "Q"}
                    ]
                }
                return (
                    body,
                    store.capture("personal", url, params, canonical(body))["id"],
                )
            offset = params["offset"]
            body = {
                "count": 2,
                "offset": offset,
                "observations": [
                    {
                        "date": "2024-01-01" if offset == 0 else "2024-04-01",
                        "value": "1.6" if offset == 0 else ".",
                        "realtime_start": "2024-05-30",
                        "realtime_end": "2024-05-30",
                    }
                ],
            }
            cap = store.capture("personal", url, params, canonical(body))
            return body, cap["id"]

    s = Series(
        id="fred:test",
        name="Test",
        source="fred",
        source_id="test",
        country="USA",
        unit="percent",
        frequency="quarterly",
    )
    scope = Scope(
        start="2024-01-01",
        end="2024-04-01",
        information_date="2024-05-30",
        mode="source_vintage",
    )
    fred_snapshot(store, "personal", s, scope, Mock())
    r = store.query(
        "personal",
        Query(series_id=s.id, start=scope.start, end=scope.end, as_of="2024-05-30"),
    )
    assert r["data"][1]["status"] == "missing" and r["data"][1]["value"] is None


def test_http_workflow_and_origin_boundary(tmp_path):
    app = create_app(tmp_path / "http", start_worker=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert (
            client.get("/api/v1/research/workspace").json()["session"]["workspace"]
            == "personal"
        )
        assert (
            client.post(
                "/api/v1/research/demo", headers={"Origin": "https://attacker.example"}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/research/series", headers={"Host": "attacker.example"}
            ).status_code
            == 403
        )
        assert client.post("/api/v1/research/demo").status_code == 200
        recipe = Recipe(
            title="API test", queries=[query()], threshold="1.5"
        ).model_dump(mode="json")
        saved = client.post("/api/v1/research/analyses", json=recipe).json()
        job = client.post(
            f'/api/v1/research/analyses/{saved["id"]}/runs', json={}
        ).json()
        assert job["status"] == "planned"
        completed = tick(app.state.store)
        assert completed["status"] == "succeeded"
        run_id = completed["result"]["run_id"]
        result = client.get("/api/v1/research/runs/" + run_id)
        assert result.status_code == 200
        assert (
            client.post(
                "/api/v1/research/annotations",
                json={"run_id": run_id, "text": "Hypothesis"},
            ).status_code
            == 201
        )
        assert (
            client.get(
                "/api/v1/research/runs/" + run_id + "/export?format=bundle"
            ).status_code
            == 200
        )
        assert client.get("/api/v1/research/publications/2024").status_code == 404
        w = client.put(
            "/api/v1/research/watchlists/default",
            json={"name": "Daily", "series_ids": []},
        )
        assert w.status_code == 200
        assert (
            client.put(
                "/api/v1/research/watchlists/default",
                json={"name": "Other", "series_ids": []},
                headers={"If-Match": "999"},
            ).status_code
            == 409
        )


def test_run_retry_keeps_original_manifest_after_new_data(demo):
    service = Research(demo)
    saved = service.save_recipe(
        "personal", "tester", Recipe(title="Retry", queries=[query()])
    )
    original = service.queue_run("personal", "tester", saved["id"], "request-key")
    cap = demo.capture("personal", "https://example.org", {}, b"{}")
    demo.ingest(
        "personal",
        Series(
            id="fixture:new",
            name="New",
            source="fixture",
            source_id="new",
            country="USA",
            unit="USD",
            frequency="annual",
        ),
        Scope(
            start="2024-01-01",
            end="2024-01-01",
            information_date="2024-04-25",
            mode="source_vintage",
        ),
        [Observation(date="2024-01-01", value="2")],
        [cap["id"]],
    )
    assert (
        demo.manifest("personal")[0]
        != original["payload"]["recipe"]["queries"][0]["dataset"]
    )
    assert (
        service.queue_run("personal", "tester", saved["id"], "request-key") == original
    )
    with pytest.raises(Conflict):
        service.queue_run(
            "personal", "tester", saved["id"], "request-key", refresh=True
        )

import json
from datetime import datetime, timedelta, timezone

import jwt
import numpy as np
import pandas as pd
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from src.data_sources.worldbank import WorldBankClient
from src.research.auth import Auth
from src.research.contracts import Observation, Scope, Series
from src.research.control import Conflict
from src.research.fencing import lease
from src.research.ingestion import TransientSourceError, Transport
from src.research.models import fit_factor_at_cutoff, replay_factor
from src.research.scheduler import Schedule, reconcile
from src.research.source_metadata import verify_bis, verify_fred
from src.research.storage import ResearchStore, canonical


def test_cutoff_fit_is_invariant_to_future_scaling_imputation_and_orientation():
    rng = np.random.default_rng(41)
    t = np.arange(160)
    frame = pd.DataFrame(
        {f"x{i}": np.sin(t / 8) + t / 80 + rng.normal(0, 0.2, 160) for i in range(4)},
        index=pd.date_range("2010-01-01", periods=160, freq="W-FRI"),
    )
    frame.iloc[20:50, 1] = np.nan
    frame.iloc[:8, 2] = np.nan
    cutoff = frame.index[110]
    a = fit_factor_at_cutoff(frame, cutoff)
    frame.loc[frame.index > cutoff] = rng.normal(-99999, 50000, (49, 4))
    b = fit_factor_at_cutoff(frame, cutoff)
    assert canonical(a) == canonical(b)
    replay_factor(a)
    broken = json.loads(json.dumps(a))
    broken["scaler_mean"][0] += 1
    with pytest.raises(ValueError, match="tolerance"):
        replay_factor(broken)


def test_stale_worker_cannot_publish(tmp_path):
    s = ResearchStore(tmp_path)
    s.control.enqueue("personal", "partition", "ingest", {})
    old = s.control.claim("personal", "old", lease_seconds=-1)
    s.control.claim("personal", "new")
    cap = s.capture("personal", "https://example.org", {}, b"[]")
    token = lease.set(old)
    try:
        with pytest.raises(Conflict):
            s.ingest(
                "personal",
                Series(
                    id="test",
                    source="fixture",
                    source_id="x",
                    name="x",
                    country="USA",
                    unit="percent",
                    frequency="daily",
                ),
                Scope(
                    start="2024-01-01",
                    end="2024-01-01",
                    information_date="2024-01-01",
                    mode="source_vintage",
                ),
                [Observation(date="2024-01-01", value="1")],
                [cap["id"]],
            )
    finally:
        lease.reset(token)
    assert not s.control.list("personal", "manifest")


def test_schedule_restart_reconciles_once(tmp_path):
    s = ResearchStore(tmp_path)
    spec = Schedule(
        series=Series(
            id="x",
            name="x",
            source="fred",
            source_id="x",
            country="USA",
            unit="percent",
            frequency="daily",
        ),
        start="2020-01-01",
    )
    s.control.put("personal", "schedule", "daily", spec.model_dump(mode="json"))
    assert len(reconcile(s, "personal")) == 1
    assert reconcile(ResearchStore(tmp_path), "personal") == []
    assert len(s.control.list("personal", "job")) == 1


def test_wrong_unit_and_dimension_fail():
    series = Series(
        id="x",
        source="fred",
        source_id="x",
        name="x",
        country="JPN",
        unit="millions yen",
        frequency="monthly",
    )

    class T:
        def get(self, *a):
            return {
                "seriess": [
                    {"id": "x", "units": "Billions of Yen", "frequency_short": "M"}
                ]
            }, "cap"

    with pytest.raises(ValueError, match="unit"):
        verify_fred(
            series,
            Scope(
                start="2024-01-01",
                end="2024-01-01",
                information_date="2024-01-01",
                mode="source_vintage",
            ),
            T(),
        )
    series = series.model_copy(
        update={"source_id": "Q.US", "dimensions": {"FREQ": "Q", "AREA": "US"}}
    )
    with pytest.raises(ValueError, match="key"):
        verify_bis(
            series,
            {
                "dimensions": {
                    "series": [
                        {"id": "FREQ", "values": [{"id": "Q"}]},
                        {"id": "AREA", "values": [{"id": "JP"}]},
                    ]
                }
            },
            "0:0",
        )


def test_worldbank_pagination_preserves_geography_and_open_range():
    calls = []

    class Response:
        def __init__(self, p):
            self.p = p

        def raise_for_status(self):
            pass

        def json(self):
            return [
                {"total": 2, "pages": 2, "lastupdated": "2026-09-01"},
                [
                    {
                        "date": "2024",
                        "value": 100 + self.p,
                        "countryiso3code": "USA" if self.p == 1 else "JPN",
                    }
                ],
            ]

    class Session:
        def get(self, url, params, timeout):
            calls.append(params)
            return Response(params["page"])

    client = WorldBankClient()
    client.session = Session()
    df = client.get_series("NY.GDP.MKTP.CD", start_date="2020")
    assert df.country.tolist() == ["USA", "JPN"]
    assert calls[0]["date"].endswith(str(datetime.now(timezone.utc).year))
    assert len(df) == 2 and df.date.nunique() == 1


def test_transport_retry_and_malformed_capture(tmp_path, monkeypatch):
    monkeypatch.setattr("src.research.ingestion.time.sleep", lambda _: None)
    s = ResearchStore(tmp_path)

    class Response:
        status_code = 200
        headers = {}  # noqa: RUF012
        content = b"not-json"

        def json(self):
            raise ValueError("bad")

    class Session:
        def get(self, *a, **kw):
            return Response()

    t = Transport(s, "personal", session=Session(), spacing=0)
    with pytest.raises(ValueError, match="malformed"):
        t.get("https://example.org", {})
    assert len(s.control.list("personal", "capture")) == 1
    Response.status_code = 429
    Response.headers = {"Retry-After": "1"}
    with pytest.raises(TransientSourceError):
        t.get("https://example.org", {})


def test_oidc_scope_roles_revocation_and_expiry(tmp_path, monkeypatch):
    s = ResearchStore(tmp_path)
    for k, v in {
        "RESEARCH_AUTH_MODE": "oidc",
        "OIDC_ISSUER": "https://issuer.example",
        "OIDC_AUDIENCE": "research",
        "OIDC_JWKS_URL": "https://issuer.example/keys",
    }.items():
        monkeypatch.setenv(k, v)
    auth = Auth(s.control)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class Keys:
        def get_signing_key_from_jwt(self, _):
            return type("Key", (), {"key": private.public_key()})()

    auth.jwks = Keys()
    member = s.control.put("a", "member", "alice", {"active": True, "role": "viewer"})

    def req(workspace="a", expiry=300):
        token = jwt.encode(
            {
                "sub": "alice",
                "iss": "https://issuer.example",
                "aud": "research",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(seconds=expiry),
            },
            private,
            algorithm="RS256",
        )
        return Request(
            {
                "type": "http",
                "headers": [
                    (b"authorization", ("Bearer " + token).encode()),
                    (b"x-workspace-id", workspace.encode()),
                ],
            }
        )

    assert auth.principal(req()).role == "viewer"
    for request in [req("b"), req(expiry=-1)]:
        with pytest.raises(HTTPException) as err:
            auth.principal(request)
        assert err.value.status_code == 401
    s.control.put(
        "a", "member", "alice", {"active": False, "role": "viewer"}, member["version"]
    )
    with pytest.raises(HTTPException):
        auth.principal(req())


def test_assistant_regression_corpus():
    from src.research.evaluation import evaluate_assistant

    result = evaluate_assistant()
    assert result["passed"] == result["cases"] == 40


def test_vintage_specific_units_and_scaled_net_liquidity(tmp_path):
    from src.research.calculations import calculate
    from src.research.contracts import Query, Recipe

    s = ResearchStore(tmp_path)
    series = Series(
        id="fred:tga",
        name="TGA",
        source="fred",
        source_id="WTREGEN",
        country="USA",
        unit="billions USD",
        frequency="weekly",
    )
    for day, value, unit in [
        ("2024-05-30", "700", "billions USD"),
        ("2026-09-10", "700000", "millions USD"),
    ]:
        cap = s.capture("personal", "https://example.org", {}, b"[]")
        s.ingest(
            "personal",
            series.model_copy(update={"unit": unit}),
            Scope(
                start="2024-05-01",
                end="2024-05-01",
                information_date=day,
                mode="source_vintage",
            ),
            [Observation(date="2024-05-01", value=value)],
            [cap["id"]],
        )
    old = s.query(
        "personal",
        Query(
            series_id=series.id,
            start="2024-05-01",
            end="2024-05-01",
            as_of="2024-05-30",
        ),
    )
    assert old["series"]["unit"] == "billions USD" and old["data"][0]["value"] == "700"
    q = Query(series_id="x", start="2024-05-01", end="2024-05-01", as_of="2024-05-30")
    recipe = Recipe(title="Net", queries=[q, q, q], operation="net_liquidity")
    inputs = [
        {"series": {"unit": u}, "data": [{"date": "2024-05-01", "value": v}]}
        for u, v in [
            ("millions USD", "7000000"),
            ("billions USD", "700"),
            ("billions USD", "500"),
        ]
    ]
    result = calculate(recipe, inputs)
    assert result["data"][0]["value"] == "5800000" and result["unit"] == "millions USD"


def test_research_model_preserves_unknown_regime_during_warmup(monkeypatch):
    from src.indicators.glci import GLCIComputer, GLCIPillarResult

    index = pd.date_range("2024-01-05", periods=18, freq="W-FRI")

    def pillar(self, name, *args):
        return GLCIPillarResult(
            name=name,
            factor=pd.Series(np.sin(np.arange(18) / 3), index=index),
            loadings=pd.DataFrame({"factor_1": [0.5, 0.5]}, index=["a", "b"]),
            explained_variance=0.8,
            method="pca_shrunk",
            data_quality=None,
        )

    monkeypatch.setattr(GLCIComputer, "_compute_pillar_factor", pillar)
    result = GLCIComputer(training_cutoff="2024-05-31").compute(
        save_output=False, verbose=False
    )
    assert result.metadata["current_regime"]["regime"] is None
    assert result.metadata["current_regime"]["regime_label"] == "unavailable"
    with pytest.raises(ValueError, match="insufficient common history"):
        GLCIComputer().compute(save_output=False, verbose=False)


def test_cancelled_job_is_not_claimed(tmp_path):
    from fastapi.testclient import TestClient

    from src.research.api import create_app
    from src.research.worker import tick

    app = create_app(tmp_path, start_worker=False)
    app.state.store.control.enqueue("personal", "cancel-me", "analysis", {})
    with TestClient(app) as client:
        response = client.post("/api/v1/research/jobs/cancel-me/cancel")
        assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert tick(app.state.store) is None


def test_expired_failure_does_not_kill_worker(tmp_path, monkeypatch):
    from src.research.ingestion import TransientSourceError
    from src.research.worker import tick

    s = ResearchStore(tmp_path)
    series = Series(
        id="x",
        name="x",
        source="fred",
        source_id="x",
        unit="percent",
        country="USA",
        frequency="daily",
    )
    scope = Scope(
        start="2024-01-01",
        end="2024-01-01",
        information_date="2024-01-01",
        mode="source_vintage",
    )
    s.control.enqueue(
        "personal",
        "retry",
        "ingest",
        {
            "series": series.model_dump(mode="json"),
            "scope": scope.model_dump(mode="json"),
        },
    )

    def fail(*args):
        job = s.control.get("personal", "job", "retry")
        s.control.put(
            "personal",
            "job",
            "retry",
            {**job, "lease_until": "2000-01-01T00:00:00+00:00"},
            job["version"],
        )
        raise TransientSourceError("timeout")

    monkeypatch.setattr("src.research.worker.source_snapshot", fail)
    assert tick(s) is None
    assert s.control.claim("personal", "replacement")["generation"] == 2

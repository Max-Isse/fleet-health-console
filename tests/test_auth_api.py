"""API and authorisation tests with locally signed tokens and an in-memory repository."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from fleet.api import create_app
from fleet.auth import TokenVerifier

ISSUER = "http://idp.test/realms/fleet"
AUDIENCE = "fleet-api"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def token(roles: list[str], key=KEY, **overrides: Any) -> str:
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "u1",
        "preferred_username": "sam",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "realm_access": {"roles": roles},
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


class FakeRepo:
    def __init__(self) -> None:
        self.alerts = {
            1: {
                "id": 1,
                "engine_id": 7,
                "band": "critical",
                "cycle": 180,
                "rul_pred": 12.0,
                "raised_at": NOW,
                "acknowledged_by": None,
                "acknowledged_at": None,
            },
        }

    def list_engines(self, band: str | None) -> list[dict[str, Any]]:
        rows = [
            {
                "engine_id": 7,
                "cycle": 180,
                "rul_pred": 12.0,
                "band": "critical",
                "model_version": "v",
                "scored_at": NOW,
            },
            {
                "engine_id": 3,
                "cycle": 90,
                "rul_pred": 88.0,
                "band": "healthy",
                "model_version": "v",
                "scored_at": NOW,
            },
        ]
        return [r for r in rows if band in (None, r["band"])]

    def engine_history(self, engine_id: int, sensors: list[str]) -> dict[str, Any] | None:
        if engine_id != 7:
            return None
        return {
            "engine_id": 7,
            "predictions": [{"cycle": 180, "rul_pred": 12.0, "band": "critical"}],
            "readings": [{"cycle": 180, **{s: 1.0 for s in sensors}}],
            "alerts": list(self.alerts.values()),
        }

    def list_alerts(self, status: str = "open", engine_id: int | None = None) -> list[dict[str, Any]]:
        return [
            a
            for a in self.alerts.values()
            if status == "all" or (a["acknowledged_at"] is None) == (status == "open")
        ]

    def acknowledge_alert(self, alert_id: int, user: str, when: datetime) -> dict[str, Any] | None:
        a = self.alerts.get(alert_id)
        if a and a["acknowledged_at"] is None:
            a.update(acknowledged_by=user, acknowledged_at=when)
        return a

    def pipeline_counts(self) -> dict[str, Any]:
        return {
            "readings": 10,
            "predictions": 10,
            "dead_letters": 1,
            "open_alerts": 1,
            "last_ingested_at": NOW,
        }

    def recent_dead_letters(self, limit: int = 20) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def client() -> TestClient:
    verifier = TokenVerifier(ISSUER, AUDIENCE, key_resolver=lambda _t: KEY.public_key())
    app = create_app(repo=FakeRepo(), verifier=verifier, status_fn=lambda: {"total_lag": 0, "partitions": []})
    return TestClient(app)


def auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_health_is_public(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_missing_token_is_401(client: TestClient) -> None:
    r = client.get("/api/engines")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "bad",
    [
        token(["viewer"], key=OTHER_KEY),  # signed by someone else
        token(["viewer"], iss="http://evil.test/realms/x"),  # wrong issuer
        token(["viewer"], aud="another-api"),  # token meant for another API
        token(["viewer"], exp=int(time.time()) - 3600),  # expired
    ],
)
def test_untrusted_tokens_are_rejected(client: TestClient, bad: str) -> None:
    assert client.get("/api/engines", headers=auth(bad)).status_code == 401


def test_token_without_roles_is_403(client: TestClient) -> None:
    assert client.get("/api/engines", headers=auth(token([]))).status_code == 403


def test_viewer_reads_fleet_sorted_by_risk(client: TestClient) -> None:
    r = client.get("/api/engines", headers=auth(token(["viewer"])))
    assert r.status_code == 200
    assert [e["engine_id"] for e in r.json()] == [7, 3]
    r = client.get("/api/engines", params={"band": "critical"}, headers=auth(token(["viewer"])))
    assert [e["engine_id"] for e in r.json()] == [7]


def test_band_filter_is_validated(client: TestClient) -> None:
    r = client.get("/api/engines", params={"band": "purple"}, headers=auth(token(["viewer"])))
    assert r.status_code == 422


def test_unknown_engine_is_404(client: TestClient) -> None:
    assert client.get("/api/engines/999", headers=auth(token(["viewer"]))).status_code == 404


def test_viewer_cannot_acknowledge(client: TestClient) -> None:
    r = client.post("/api/alerts/1/acknowledge", headers=auth(token(["viewer"])))
    assert r.status_code == 403


def test_engineer_acknowledges_once(client: TestClient) -> None:
    t = token(["viewer", "engineer"])
    first = client.post("/api/alerts/1/acknowledge", headers=auth(t)).json()
    assert first["acknowledged_by"] == "sam"
    again = client.post(
        "/api/alerts/1/acknowledge", headers=auth(token(["viewer", "engineer"], preferred_username="kim"))
    )
    assert again.json()["acknowledged_by"] == "sam"  # idempotent: first acknowledgement wins
    assert client.get("/api/alerts", params={"status": "open"}, headers=auth(t)).json() == []


def test_graphql_requires_auth_and_returns_engines(client: TestClient) -> None:
    query = {"query": '{ engines(band: "critical") { engineId rulPred alerts { band } } }'}
    assert client.post("/graphql", json=query).status_code == 401
    r = client.post("/graphql", json=query, headers=auth(token(["viewer"])))
    assert r.status_code == 200
    assert r.json()["data"]["engines"] == [{"engineId": 7, "rulPred": 12.0, "alerts": [{"band": "critical"}]}]


def test_me_returns_roles(client: TestClient) -> None:
    r = client.get("/api/me", headers=auth(token(["viewer", "engineer"])))
    assert r.json() == {"username": "sam", "roles": ["engineer", "viewer"]}

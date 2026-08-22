"""API-boundary identity tests: the server verifies identity, never the client body.

Every route depends on a verified :class:`Principal`. Under the local profile the persona
is chosen by ``X-Dev-Persona`` (default = first persona); an unknown persona is a 401; and
the resolved persona subject (never a client-supplied actor) is the audit actor recorded
for the run.

``deps.get_container`` is ``lru_cache``d, so we monkeypatch it to inject an in-memory
container (SQLite ``:memory:`` stores) instead of mutating the environment.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from creative_studio.api import deps
from creative_studio.api.app import app
from creative_studio.config import Container
from tests.conftest import LOOPBACK_PEER

_CREATIVE_BODY = {
    "topic": "high-yield savings",
    "market": "SG",
    "vertical": "banking",
    "channel": "email",
    "offer": "4.10% p.a.",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, local_container: Container) -> TestClient:
    # Inject one shared in-memory container so the API and the assertions read the same
    # audit store; avoids mutating MKT_CREATIVE_PROFILE / touching the real filesystem.
    monkeypatch.setattr(deps, "get_container", lambda: local_container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_unknown_persona_is_401(client: TestClient) -> None:
    res = client.post("/v1/creative", json=_CREATIVE_BODY, headers={"X-Dev-Persona": "nope"})
    assert res.status_code == 401


def test_default_persona_is_the_audit_actor(client: TestClient, local_container: Container) -> None:
    # No X-Dev-Persona header => the first seeded persona (analyst) is the verified actor.
    res = client.post("/v1/creative", json=_CREATIVE_BODY)
    assert res.status_code == 200
    events = local_container.audit.read_all()
    actors = {e["actor"] for e in events if e["action"] == "generate_creative"}
    assert actors == {"demo.analyst@bank.example"}


def test_selected_persona_is_the_audit_actor(
    client: TestClient, local_container: Container
) -> None:
    res = client.post("/v1/creative", json=_CREATIVE_BODY, headers={"X-Dev-Persona": "auditor"})
    assert res.status_code == 200
    events = local_container.audit.read_all()
    actors = {e["actor"] for e in events if e["action"] == "generate_creative"}
    assert actors == {"demo.auditor@bank.example"}


def test_personas_endpoint_lists_seeded_personas(client: TestClient) -> None:
    res = client.get("/v1/personas")
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert {"analyst", "approver", "auditor", "other-tenant"} <= ids

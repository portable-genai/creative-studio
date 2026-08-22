"""Import-safety + wiring tests for the D3 ADK agent layer.

The local / on-prem / test profile installs **no Google Cloud SDK**, so importing the agent
wiring modules (and building the AgentCard, and calling the plain tool callables) must never
pull in ``google.adk`` / ``google-cloud-*``. The agent-card endpoint is also exercised
end-to-end against the local SDK-free stack via a monkeypatched in-memory container.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from creative_studio.api import deps
from creative_studio.api.app import app
from creative_studio.config import Container, Settings
from tests.conftest import LOOPBACK_PEER

_EXPECTED_SKILLS = {"generate_creative", "review_variant"}


# --------------------------------------------------------------------------- #
# Import safety (no ADK installed)
# --------------------------------------------------------------------------- #
def test_agent_package_imports_without_adk() -> None:
    module = importlib.import_module("creative_studio.agent")
    assert module.build_root_agent is not None
    assert module.build_agent_card is not None
    assert "google.adk" not in sys.modules


def test_agent_root_imports_without_adk() -> None:
    module = importlib.import_module("creative_studio.agent.root_agent")
    assert repr(module.root_agent)  # touching the lazy proxy must not build the agent
    assert "google.adk" not in sys.modules


def test_mcp_toolset_is_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    ra = importlib.import_module("creative_studio.agent.root_agent")

    monkeypatch.delenv(ra.MCP_SERVER_URL_ENV, raising=False)
    assert ra._build_mcp_toolset() is None
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The AgentCard is pure domain (no ADK)
# --------------------------------------------------------------------------- #
def test_agent_card_is_pure(local_settings: Settings) -> None:
    from creative_studio.agent.agent_card import build_agent_card

    card = build_agent_card(local_settings)
    assert card.name == "creative-studio"
    assert {s.id for s in card.skills} == _EXPECTED_SKILLS


def test_governed_tools_match_card_skills() -> None:
    """Least privilege (R4): the tool surface and the advertised skills stay in step."""
    from creative_studio.agent import tools
    from creative_studio.agent.agent_card import SKILLS

    assert tools.governed_tool_names() == {s.id for s in SKILLS}


# --------------------------------------------------------------------------- #
# The plain tool callables run offline against the local stack (no ADK)
# --------------------------------------------------------------------------- #
def test_generate_creative_tool_offline(local_settings: Settings) -> None:
    from creative_studio.agent.tools import generate_creative

    result = generate_creative(
        "spring savings push",
        market="SG",
        vertical="banking",
        channel="email",
        offer="4.10% p.a.",
        actor="creative@brand.example",
        settings=local_settings,
    )
    assert result["requires_human_review"] is True
    assert "google.adk" not in sys.modules


def test_review_variant_tool_offline(local_settings: Settings) -> None:
    from creative_studio.agent.tools import review_variant

    result = review_variant(
        "Save more this spring",
        body="Open a high-yield account today.",
        cta="Open now",
        market="SG",
        vertical="banking",
        channel="email",
        settings=local_settings,
    )
    assert "findings" in result or "checks" in result or result
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The agent-card endpoint end-to-end (local stack)
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, local_settings: Settings) -> TestClient:
    container = Container(local_settings)
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_agent_card_endpoint(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "creative-studio"
    assert {s["id"] for s in body["skills"]} == _EXPECTED_SKILLS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

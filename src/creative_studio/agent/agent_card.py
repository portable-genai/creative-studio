"""A2A AgentCard for the D3 Creative Studio agent (A3 Registry & Governance).

This builds the agent's discovery card (the same minimal A2A shape the ``agent-registry``
service stores and serves, SPEC §6). It is published at ``/.well-known/agent-card.json``;
:func:`agent_card_document` returns the JSON-safe body the API layer serves there, and the
``platform`` registry adapter registers the same card in agent-registry (rule R4).

The card advertises the two skills D3 produces (generate_creative, review_variant), mirroring
the ADK FunctionTools so a peer agent or the registry sees one consistent capability surface.

This module is pure (domain models only) and imports without ADK or any Google Cloud SDK
installed (SPEC §4).
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.models import AgentCard, AgentSkill

SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="generate_creative",
        name="Brand-safe creative generation",
        description=(
            "Generate on-brand ad copy variants (optionally with an image) for a market "
            "(JP / AU / SG) and vertical (banking / online retail), each run through the "
            "deterministic brand-guideline, advertising-claim and policy checks before it "
            "ships. Always flagged for human review (P-06)."
        ),
    ),
    AgentSkill(
        id="review_variant",
        name="Creative claim / brand review",
        description=(
            "Run the four deterministic checks (brand-guideline, advertising-claim, policy, "
            "dedup) on a single externally-supplied variant and return the findings with "
            "citations, so an external draft can be gated before it ships."
        ),
    ),
)

_DESCRIPTION = (
    "Brand-safe creative studio agent for a bank or online retailer. Generates on-brand ad "
    "copy and image variants and reviews them against per-market advertising-claim rules, "
    "brand guidelines and policy before anything ships, generic across banking and online "
    "retail and the JP / AU / SG markets. Built ports-and-adapters on the Gemini Enterprise "
    "Agent Platform. The model drafts copy; the deterministic engines decide brand-safety and "
    "claim compliance, and every finding carries a citation."
)


def build_agent_card(settings: Settings) -> AgentCard:
    """Construct the A2A :class:`AgentCard` for this agent."""
    return AgentCard(
        name="creative-studio",
        description=_DESCRIPTION,
        url=_resolve_url(settings),
        version="0.1.0",
        skills=SKILLS,
        provider="creative-studio",
    )


def agent_card_document(settings: Settings) -> dict[str, Any]:
    """Return the JSON-safe body to serve at ``/.well-known/agent-card.json``."""
    from ..domain.serialization import to_jsonable

    return to_jsonable(build_agent_card(settings))


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-pinned to the active market."""
    resource = settings.agent_engine.resource_name
    if resource:
        return f"https://aiplatform.googleapis.com/v1/{resource}"
    return "https://creative-studio.mkt.internal/a2a"

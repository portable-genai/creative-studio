"""A2A registry adapter (AgentRegistryPort) — agent discovery and governance for D3 (A3).

Backs the domain ``AgentRegistryPort`` with an in-process, **A2A v1.0**-style registry of
:class:`AgentCard` objects. In a standalone deployment D3 registers its own card here and
can serve it at the well-known A2A discovery path; inside the full platform the ``platform``
profile swaps this for a thin client to the shared agent registry.

A2A discovery contract: an agent publishes its capabilities as an **AgentCard** served at
``/.well-known/agent-card.json``; peers fetch that card to learn the agent's skills,
endpoint URL and version before initiating an A2A task. ``agent_card_dict`` produces that
JSON body. No external call is required: this adapter is pure, in-memory governance, so it
needs no Google import and constructs cleanly under any profile.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AgentCard, AgentSkill

AGENT_CARD_PATH = "/.well-known/agent-card.json"

_D3_SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="generate_creative",
        name="Brand-safe creative generation",
        description=(
            "Draft creative variants (Gemini copy + Imagen image) and run deterministic "
            "brand, advertising-claim, per-market policy and asset-spec checks, for any of "
            "banking / online retail across JP/AU/SG."
        ),
    ),
    AgentSkill(
        id="review_variant",
        name="Brand-safety review",
        description=(
            "Run the deterministic brand, claim, policy and asset checks on a supplied "
            "variant and return cited findings with a maker-checker verdict."
        ),
    ),
)


class A2ARegistryAdapter:
    """In-process A2A AgentCard registry: register / get / list, plus card export."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cards: dict[str, AgentCard] = {}
        self.register(self._self_card())

    def register(self, card: AgentCard) -> None:
        self._cards[card.name] = card

    def get(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def list(self) -> list[AgentCard]:
        return list(self._cards.values())

    def agent_card_dict(self, name: str | None = None) -> dict:
        """Return the ``/.well-known/agent-card.json`` body for ``name`` (default: D3's)."""
        card = self.get(name) if name else self._cards.get(self._self_name())
        if card is None:
            raise KeyError(f"No AgentCard registered for '{name}'.")
        return {
            "name": card.name,
            "description": card.description,
            "url": card.url,
            "version": card.version,
            "provider": card.provider,
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description} for s in card.skills
            ],
        }

    def _self_name(self) -> str:
        return self._settings.agent_engine.display_name or "creative-studio"

    def _self_card(self) -> AgentCard:
        return AgentCard(
            name=self._self_name(),
            description=(
                "D3 Brand-Safe Creative and Content Studio — Gemini copy + Imagen image with "
                "deterministic brand-guideline, advertising-claim, per-market policy and "
                "asset-spec validation, generic across banking and online retail and the "
                "JP/AU/SG markets, with cited findings."
            ),
            url=f"https://creative-studio.{self._settings.region}.example/a2a",
            version="1.0.0",
            skills=_D3_SKILLS,
            provider="creative-studio",
        )

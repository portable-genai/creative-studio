"""MCP tool-catalog adapter (ToolCatalogPort) — the governed tool surface for D3.

Backs the domain ``ToolCatalogPort`` by exposing D3's governed, least-privilege
capabilities as :class:`ToolSpec` objects: ``generate_creative``, ``review_variant`` and
``search_brand_corpus``. These are the tools the agent (or a peer agent) may invoke, each
with an explicit JSON input schema so access is scoped and auditable (least privilege).

Interop: the catalog speaks **MCP 2026-07-28**. In an ADK deployment these specs are
surfaced to the agent through an ``McpToolset`` connected to an MCP server fronting the
domain services; here the adapter only *declares* the governed catalog (declarative, no live
MCP connection required to list). The ``mcp`` package is imported LAZILY and only when an
actual MCP wire object is requested.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import ToolSpec

MCP_PROTOCOL_VERSION = "2026-07-28"

_SCOPE_SCHEMA: dict[str, Any] = {
    "market": {
        "type": "string",
        "enum": ["JP", "AU", "SG"],
        "description": "Restrict to a single market.",
    },
    "vertical": {
        "type": "string",
        "enum": ["banking", "online_retail"],
        "description": "Restrict to a single vertical.",
    },
}

# A channel is a property of a CREATIVE, not of the brand corpus, and it used to live in the
# scope fragment that all three tools shared. `search_brand_corpus` therefore advertised a
# channel it could not use: `RetrievalQuery` has no channel field and nothing downstream reads
# one. Declared separately so the two tools that DO build a creative ask for it and the one
# that searches a corpus does not.
_CHANNEL_SCHEMA: dict[str, Any] = {
    "channel": {
        "type": "string",
        "enum": ["email", "sms", "push", "display", "search", "social", "web"],
        "description": "The marketing channel.",
    },
}

# The brief both creative tools build, declared once. `review_variant` runs the checks with the
# SAME `_brief` `generate_creative` does -- a claim is judged against the campaign theme, the
# product and the offer -- so it needs the brief keys, and until 2026-08-31 it declared none of
# them under `additionalProperties: False`. A reviewer was reviewing against an empty brief and
# could not say otherwise. `n_variants` is deliberately NOT here: it is how many drafts to
# produce, which is meaningless when reviewing one supplied variant.
_BRIEF_SCHEMA: dict[str, Any] = {
    "topic": {"type": "string", "description": "Campaign theme."},
    "product": {"type": "string"},
    "offer": {"type": "string"},
    **_SCOPE_SCHEMA,
    **_CHANNEL_SCHEMA,
}


def _build_catalog() -> dict[str, ToolSpec]:
    """Declare the governed tools with explicit, least-privilege input schemas."""
    return {
        "generate_creative": ToolSpec(
            name="generate_creative",
            description=(
                "Draft creative variants (Gemini copy + optional Imagen image) and run the "
                "deterministic brand, claim, policy and asset checks. Output requires human "
                "review (maker-checker)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "n_variants": {"type": "integer", "minimum": 1, "maximum": 8, "default": 3},
                    **_BRIEF_SCHEMA,
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
        ),
        "review_variant": ToolSpec(
            name="review_variant",
            description=(
                "Run the deterministic brand, claim, policy and asset checks on a supplied "
                "variant and return cited findings."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "cta": {"type": "string"},
                    **_BRIEF_SCHEMA,
                },
                "required": ["headline", "body"],
                "additionalProperties": False,
            },
        ),
        "search_brand_corpus": ToolSpec(
            name="search_brand_corpus",
            description=(
                "Search the internal brand / creative corpus (File Search) and return cited "
                "passages."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language query."},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    **_SCOPE_SCHEMA,
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    }


class McpToolCatalogAdapter:
    """Declarative MCP 2026-07-28 catalog of D3's governed tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._catalog: dict[str, ToolSpec] = _build_catalog()

    def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._catalog.get(name)

    def as_mcp_tools(self) -> list[Any]:
        """Render the catalog as MCP ``Tool`` objects (MCP 2026-07-28 schema)."""
        from mcp import types as mcp_types  # noqa: PLC0415 — lazy

        # verify: https://modelcontextprotocol.io/specification/2026-07-28
        return [
            mcp_types.Tool(name=s.name, description=s.description, input_schema=s.input_schema)
            for s in self._catalog.values()
        ]

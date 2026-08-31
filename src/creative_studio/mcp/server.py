"""Serve the governed tool catalog Mkt4 already declares, over MCP 2026-07-28.

The catalog declared three governed tools and served none of them: there was no MCP server
process anywhere in the fleet. This supplies the callables that answer the existing catalog and
declares nothing new. `hex_service_kit.mcpserve.bind` refuses a mismatch in either direction at
start-up.

`search_brand_corpus` reaches the knowledge-base port directly, because it IS a retrieval;
routing it through generation would produce creative nobody asked for. The other two are the
studio service's own entry points.

**This is the one tree in the fleet that samples on purpose**, and serving it changes nothing
about that: variation is the product here, and the deliberate temperature lives on the request
type with its own guard. A tool call gets the same non-deterministic generation a UI caller
gets, which is the honest behaviour rather than a quietly different one.

MCP stdio verifies no end user, so the caller is recorded as a SERVICE caller and no tenant is
asserted.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit import mcpserve

from ..config import build_container
from ..domain.models import Channel, CreativeBrief, Market, RetrievalQuery, Variant, Vertical

#: The tools this module answers, as data, so a test can hold it against the catalog.
HANDLER_NAMES: tuple[str, ...] = ("generate_creative", "review_variant", "search_brand_corpus")


def _brief(arguments: dict[str, Any], *, n_variants: int) -> CreativeBrief:
    """The brief both creative tools work from.

    ``n_variants`` is passed rather than read out of ``arguments`` because it means something
    on only one of the two paths: it is how many drafts to GENERATE. The review path used to
    reach it through this helper, so reviewing one supplied variant read a draft count the
    reviewer's own schema never offered -- an argument that could change nothing and that no
    caller could set.
    """
    return CreativeBrief(
        topic=str(arguments.get("topic", "") or ""),
        market=Market(str(arguments.get("market", ""))),
        vertical=Vertical(str(arguments.get("vertical", ""))),
        channel=Channel(str(arguments.get("channel", ""))),
        product=str(arguments.get("product", "") or ""),
        offer=str(arguments.get("offer", "") or ""),
        n_variants=n_variants,
    )


def _optional_market(arguments: dict[str, Any]) -> Market | None:
    """The requested market, or None when the caller named none. Never a guessed default."""
    raw = str(arguments.get("market", "") or "")
    return Market(raw) if raw else None


def _optional_vertical(arguments: dict[str, Any]) -> Vertical | None:
    raw = str(arguments.get("vertical", "") or "")
    return Vertical(raw) if raw else None


def build_handlers(actor: str) -> dict[str, mcpserve.Handler]:
    """Bind each declared tool to the service or port that already performs it."""
    from ..api.app import make_studio_service

    def generate_creative(**arguments: Any) -> Any:
        return make_studio_service().generate(
            _brief(arguments, n_variants=int(arguments.get("n_variants") or 3)), actor=actor
        )

    def review_variant(**arguments: Any) -> Any:
        variant = Variant(
            id="",
            headline=str(arguments.get("headline", "") or ""),
            body=str(arguments.get("body", "") or ""),
            cta=str(arguments.get("cta", "") or ""),
            channel=Channel(str(arguments.get("channel", ""))),
        )
        # One variant is supplied and one variant is reviewed.
        return make_studio_service().review(_brief(arguments, n_variants=1), variant, actor=actor)

    def search_brand_corpus(**arguments: Any) -> Any:
        # The scope is PASSED, not merely declared. This tool advertised `market` and
        # `vertical` and then built an unscoped RetrievalQuery, so a caller asking for one
        # market's brand corpus was served every market's. `RetrievalQuery` has carried both
        # fields all along. An absent value stays None, which is the port's own "no partition"
        # and a different thing from a value the caller chose.
        return build_container().knowledge_base.search(
            RetrievalQuery(
                text=str(arguments.get("query", "") or ""),
                top_k=int(arguments.get("top_k") or 5),
                market=_optional_market(arguments),
                vertical=_optional_vertical(arguments),
            )
        )

    return {
        "generate_creative": generate_creative,
        "review_variant": review_variant,
        "search_brand_corpus": search_brand_corpus,
    }


def build_server(actor: str, *, with_audit_tools: bool = True) -> Any:
    """Build the MCP server for Mkt4's catalog, refusing on any catalog/handler mismatch."""
    container = build_container()
    return mcpserve.build_server(
        name="creative-studio",
        version=str(getattr(container.settings, "version", "") or "0.0.1"),
        catalog=container.tool_catalog,
        handlers=build_handlers(actor),
        audit_store=getattr(container, "audit", None) if with_audit_tools else None,
    )

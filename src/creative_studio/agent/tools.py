"""ADK FunctionTools that expose the D3 domain services to the agent.

Each tool is a thin, side-effect-honest wrapper: it builds the :class:`CreativeStudioService`
from a :class:`~creative_studio.config.Container` (so every port is bound to the adapter
selected by the active profile), invokes one domain method, and returns a JSON-safe dict via
:func:`~creative_studio.domain.serialization.result_jsonable` /
:func:`~creative_studio.domain.serialization.review_jsonable`, which carry the derived
verdicts the plain field walker drops.

Design notes
------------
* The domain service owns orchestration and the deterministic checks (brand-guideline, claim,
  policy, dedup; SPEC §5). These tools add **no** business logic of their own: the model
  drafts copy and decides *which* artifact to produce, the deterministic engines decide
  whether it is brand-safe and claim-compliant.
* ``google.adk`` is imported lazily inside :func:`build_function_tools` so this module imports
  cleanly under the on-prem / local / test profile with no ADK installed (SPEC §4). The plain
  Python tool callables are importable and unit-testable without ADK at all.
* Every callable carries a precise type-hinted signature and docstring: ADK derives the
  tool's name, description and JSON parameter schema from them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Container, Settings, build_container

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

_DEFAULT_ACTOR = "creative-studio-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def generate_creative(
    topic: str,
    market: str = "SG",
    vertical: str = "banking",
    channel: str = "email",
    product: str = "",
    offer: str = "",
    audience: str = "",
    tone: str = "clear and trustworthy",
    n_variants: int = 3,
    with_image: bool = False,
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate brand-safe, claim-checked ad copy variants (optionally with an image).

    Drafts ``n_variants`` copy variants for the brief, then runs the four deterministic checks
    (brand-guideline adherence, advertising-claim compliance, policy, dedup) on each. Always
    flagged for human review (maker-checker); every finding carries a citation.

    Args:
      topic: The campaign theme, e.g. "spring savings push".
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      channel: Channel, e.g. "email", "sms", "push", "display".
      product: Product or offer subject, e.g. "high-yield savings account".
      offer: The headline offer, e.g. "4.10% p.a." or "20% off".
      audience: Target audience description.
      tone: Desired tone of voice.
      n_variants: Number of variants to draft (1..8).
      with_image: Also generate an image asset per variant.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``CreativeStudioResult`` dict.
    """
    from ..api.deps import make_studio_service
    from ..domain.models import Channel, CreativeBrief, Market, Vertical
    from ..domain.serialization import result_jsonable

    c = _container(settings)
    brief = CreativeBrief(
        topic=topic,
        market=Market(market),
        vertical=Vertical(vertical),
        channel=Channel(channel),
        product=product,
        offer=offer,
        audience=audience,
        tone=tone,
        n_variants=n_variants,
    )
    return result_jsonable(
        make_studio_service(c).generate(brief, actor=actor, with_image=with_image)
    )


def review_variant(
    headline: str,
    body: str = "",
    cta: str = "",
    market: str = "SG",
    vertical: str = "banking",
    channel: str = "email",
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the four deterministic checks on a single externally-supplied variant.

    Returns a ``VariantReview`` (brand-guideline, advertising-claim, policy and dedup findings
    with citations) for an ad variant, so an external draft can be gated before it ships.

    Args:
      headline: Variant headline.
      body: Variant body copy.
      cta: Variant call to action.
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      channel: Channel, e.g. "email", "sms", "push", "display".
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``VariantReview`` dict.
    """
    from ..api.deps import make_studio_service
    from ..domain.models import Channel, CreativeBrief, Market, Variant, Vertical
    from ..domain.serialization import review_jsonable

    c = _container(settings)
    brief = CreativeBrief(
        topic="ad-hoc review",
        market=Market(market),
        vertical=Vertical(vertical),
        channel=Channel(channel),
    )
    variant = Variant(id="", headline=headline, body=body, cta=cta, channel=Channel(channel))
    return review_jsonable(make_studio_service(c).review(brief, variant, actor=actor))


TOOL_FUNCTIONS = (
    generate_creative,
    review_variant,
)


def governed_tool_names() -> frozenset[str]:
    """The tool names this agent exposes (mirrors the governed MCP catalog, rule R4)."""
    return frozenset(fn.__name__ for fn in TOOL_FUNCTIONS)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each domain-service callable as an ADK ``FunctionTool``.

    ADK introspects each function's signature and docstring to derive the tool name,
    description and parameter JSON schema. ``google.adk`` is imported here (lazily) so the
    module is import-safe without ADK installed (SPEC §4).
    """
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=fn) for fn in TOOL_FUNCTIONS]

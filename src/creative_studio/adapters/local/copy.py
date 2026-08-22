"""Local copy adapter (CopyGenerationPort) — deterministic templated copy generator.

The ``local`` profile's stand-in for **Gemini** copy generation: no model, no network,
fully reproducible. It drafts ``brief.n_variants`` creative variants from per-vertical
templates seeded to be brand-safe (calm tone, qualified claims with 't&cs apply', within
channel length limits), so a local run produces real, mostly-compliant creative offline and
the unit tests stay deterministic. There is no Google emulator for Gemini, so this path is
unconditional. The LLM never decides the verdicts: the deterministic engines do.

``generate`` (used by the orchestrator for narration) reads ``request.response_schema`` and
emits a deterministic JSON object whose keys match it, mapping ``used_rule_ids`` from the
``[rule_id]`` headers in the rendered evidence block.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ...config import Settings
from ...domain.models import (
    Channel,
    CreativeBrief,
    LlmRequest,
    LlmResponse,
    TokenUsage,
    Variant,
    Vertical,
)
from ...domain.rules import asset_spec_for

_RULE_HEADER_RE = re.compile(r"\[([a-z0-9][a-z0-9:_\-]*?)\]")


def _truncate(text: str, limit: int) -> str:
    """Truncate to ``limit`` chars (0 => unconstrained) without cutting mid-word badly."""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    return cut


# Per-vertical, brand-safe copy angles. Each angle yields (headline, body, cta) templates.
# The bodies include qualifiers ('t&cs apply', 'as at', 'rrp') so the claim/policy engines
# pass on the seeded output; the templates are calm and avoid forbidden brand terms.
_ANGLES: dict[Vertical, tuple[tuple[str, str, str], ...]] = {
    Vertical.BANKING: (
        (
            "Grow your savings with {product}",
            "Open {product} and earn {offer} on your balance. Rate as at today; t&cs apply.",
            "See the details",
        ),
        (
            "A simple way to save",
            "{product} gives you {offer}, with no monthly account fee. T&cs apply.",
            "Learn more",
        ),
        (
            "Plan ahead with confidence",
            "Set money aside in {product} and earn {offer}. Variable rate; t&cs apply.",
            "Get started",
        ),
        (
            "Save on your terms",
            "Move money in and out of {product} freely while earning {offer}. T&cs apply.",
            "Open an account",
        ),
    ),
    Vertical.ONLINE_RETAIL: (
        (
            "Refresh your home with {product}",
            "Shop {product} and save {offer} this season. Was rrp; t&cs apply.",
            "Shop the sale",
        ),
        (
            "Style that lasts",
            "Pick up {product} with {offer} off the rrp. T&cs apply.",
            "Browse now",
        ),
        (
            "Treat yourself this week",
            "Enjoy {offer} off {product}, based on the rrp. T&cs apply.",
            "See the range",
        ),
        (
            "More for less",
            "Get {product} for {offer} less than the was price. T&cs apply.",
            "Start shopping",
        ),
    ),
}


class LocalTemplatedCopyAdapter:
    """Deterministic, SDK-free copy generator over per-vertical brand-safe templates."""

    REASONING_MODEL = "gemini-3.5-flash"
    TRIAGE_MODEL = "gemini-3.1-flash-lite"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._reasoning_model = settings.models.reasoning or self.REASONING_MODEL
        self._triage_model = settings.models.triage or self.TRIAGE_MODEL

    # ------------------------------------------------------------------ #
    # CopyGenerationPort
    # ------------------------------------------------------------------ #
    def generate_variants(self, brief: CreativeBrief) -> tuple[Variant, ...]:
        angles = _ANGLES.get(brief.vertical, _ANGLES[Vertical.BANKING])
        spec = asset_spec_for(brief.channel)
        product = brief.product or brief.topic or "our latest offer"
        offer = brief.offer or "a great deal"
        n = max(1, min(brief.n_variants, len(angles)))
        variants: list[Variant] = []
        for i in range(n):
            headline_t, body_t, cta_t = angles[i]
            headline = _truncate(
                headline_t.format(product=product, offer=offer), spec.max_headline_chars
            )
            body = _truncate(body_t.format(product=product, offer=offer), spec.max_body_chars)
            wants_cta = self._wants_cta(spec, brief.channel)
            cta = _truncate(cta_t, spec.max_cta_chars) if wants_cta else ""
            variants.append(
                Variant(
                    id="",  # the dedupe engine assigns a stable content id
                    headline=headline,
                    body=body,
                    cta=cta,
                    channel=brief.channel,
                    rationale=f"Angle {i + 1} for {brief.vertical.value} ({brief.market.value}).",
                )
            )
        return tuple(variants)

    def generate(self, request: LlmRequest) -> LlmResponse:
        rule_ids = self._rule_ids_from_request(request)
        body = self._body_for_schema(request.response_schema, rule_ids)
        return LlmResponse(
            text=json.dumps(body),
            usage=TokenUsage(input_tokens=96, output_tokens=48, thinking_tokens=24),
            model=request.model or self._reasoning_model,
            raw=body,
        )

    def classify(self, text: str, labels: list[str]) -> str:
        return labels[0] if labels else ""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _wants_cta(spec: Any, channel: Channel) -> bool:
        # Provide a CTA when the channel requires one or allows headline+body+cta.
        return spec.requires_cta or spec.max_cta_chars > 0

    @staticmethod
    def _rule_ids_from_request(request: LlmRequest) -> list[str]:
        user = ""
        for message in reversed(request.messages):
            if message.role == "user":
                user = message.content
                break
        seen: list[str] = []
        for rid in _RULE_HEADER_RE.findall(user):
            if rid not in seen:
                seen.append(rid)
        return seen

    @staticmethod
    def _body_for_schema(schema: dict | None, rule_ids: list[str]) -> dict[str, Any]:
        props = (schema or {}).get("properties", {}) if isinstance(schema, dict) else {}
        if "summary" in props:
            n = len(rule_ids)
            summary = (
                "The deterministic brand, claim, policy and asset engines reviewed every "
                f"variant; {n} rule reference(s) were flagged across the set. This summary is "
                "grounded in the cited rules and requires human review before publishing."
                if n
                else (
                    "Every variant passed the deterministic brand, claim, policy and asset "
                    "checks. This summary requires human review before publishing."
                )
            )
            return {"summary": summary, "used_rule_ids": list(rule_ids)}
        return {"reviewed": True, "flagged_rules": len(rule_ids)}

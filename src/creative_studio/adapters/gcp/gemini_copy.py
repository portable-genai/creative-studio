"""Gemini copy adapter (CopyGenerationPort) — GCP managed stack.

Wraps the unified **Google GenAI SDK** (``google-genai``) against the **Gemini Enterprise
Agent Platform** (Vertex backend). Drafting / narration uses ``gemini-3.5-flash``;
triage/classification uses ``gemini-3.5-flash`` (both pinned from settings).

In D3 the LLM only drafts copy and variant ideas and narrates the already-computed
deterministic checks (brand / claim / policy / asset). It never decides whether a variant is
brand-safe: the deterministic engines do. ``generate_variants`` asks the model for
structured JSON variants (headline / body / cta) which are mapped onto the domain
:class:`Variant` (ids are assigned later by the deterministic dedupe engine).

The residency region is resolved from the requested market and **validated** against the
per-market allow-list, so generation stays inside the configured residency boundary.

All Google Cloud / GenAI SDK imports are LAZY so the on-prem / local / test profile imports
this module without ``google-genai`` installed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import (
    CreativeBrief,
    LlmRequest,
    LlmResponse,
    ThinkingLevel,
    TokenUsage,
    Variant,
)
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google import genai

_VARIANTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "cta": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["headline", "body"],
            },
        }
    },
    "required": ["variants"],
}


class GeminiCopyAdapter:
    """Draft creative variants and narrate via Gemini on the Agent Platform."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._models = settings.models
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Lazy, region-validated client construction
    # ------------------------------------------------------------------ #
    def _get_client(self, market: Any | None = None) -> genai.Client:
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google import genai  # noqa: PLC0415 — lazy: gcp profile only

            self._client = genai.Client(
                vertexai=True,
                project=self._settings.project_id,
                location=region,
            )
        return self._client

    # ------------------------------------------------------------------ #
    # CopyGenerationPort
    # ------------------------------------------------------------------ #
    def generate_variants(self, brief: CreativeBrief) -> tuple[Variant, ...]:
        """Ask Gemini for ``brief.n_variants`` structured creative variants."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client(brief.market)
        prompt = self._variants_prompt(brief)
        response = client.models.generate_content(
            model=self._models.reasoning,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.6,
                response_mime_type="application/json",
                response_schema=_VARIANTS_SCHEMA,
            ),
        )
        return self._to_variants(brief, response)

    def generate(self, request: LlmRequest) -> LlmResponse:
        """Generate a completion (narration over the computed checks)."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client()
        model = request.model or self._models.reasoning
        contents = self._to_contents(request, types)
        config = self._build_config(request, types)
        response = client.models.generate_content(model=model, contents=contents, config=config)
        return LlmResponse(
            text=getattr(response, "text", "") or "",
            usage=self._map_usage(getattr(response, "usage_metadata", None)),
            model=model,
        )

    def classify(self, text: str, labels: list[str]) -> str:
        """Cheap single-label classification using the triage-tier model."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client()
        label_list = ", ".join(labels)
        prompt = (
            f"Classify the text into exactly one of these labels: {label_list}.\n"
            "Reply with the single label only, no punctuation or explanation.\n\n"
            f"Text:\n{text}"
        )
        response = client.models.generate_content(
            model=self._models.triage,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=16),
        )
        raw = (getattr(response, "text", "") or "").strip()
        return self._match_label(raw, labels)

    # ------------------------------------------------------------------ #
    # Prompt / mapping
    # ------------------------------------------------------------------ #
    def _variants_prompt(self, brief: CreativeBrief) -> str:
        profile = self._settings.market_profile(brief.market)
        return (
            "You are a brand-safe marketing copywriter. Draft "
            f"{max(brief.n_variants, 1)} distinct creative variants and return ONLY "
            "structured JSON matching the schema.\n"
            f"Campaign: {brief.topic}\n"
            f"Product / offer: {brief.product} / {brief.offer}\n"
            f"Market: {profile.display_name} ({brief.market.value}); "
            f"locales: {', '.join(profile.locales)}\n"
            f"Vertical: {brief.vertical.value}; channel: {brief.channel.value}\n"
            f"Audience: {brief.audience}; tone: {brief.tone}\n"
            "Qualify every claim (e.g. add 't&cs apply'); keep a calm, honest tone. "
            "Do not invent guarantees."
        )

    def _to_variants(self, brief: CreativeBrief, response: Any) -> tuple[Variant, ...]:
        raw = getattr(response, "text", "") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        out: list[Variant] = []
        for item in payload.get("variants", [])[: max(brief.n_variants, 1)]:
            out.append(
                Variant(
                    id="",  # assigned by the deterministic dedupe engine
                    headline=str(item.get("headline", "")),
                    body=str(item.get("body", "")),
                    cta=str(item.get("cta", "")),
                    channel=brief.channel,
                    rationale=str(item.get("rationale", "")),
                )
            )
        return tuple(out)

    @staticmethod
    def _to_contents(request: LlmRequest, types: Any) -> list[Any]:
        contents: list[Any] = []
        for message in request.messages:
            role = "model" if message.role == "model" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=message.content)])
            )
        return contents

    def _build_config(self, request: LlmRequest, types: Any) -> Any:
        kwargs: dict[str, Any] = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens,
            "thinking_config": types.ThinkingConfig(
                thinking_level=self._thinking_level(request.thinking, types)
            ),
        }
        if request.system_instruction:
            kwargs["system_instruction"] = request.system_instruction
        if request.response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = request.response_schema
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _thinking_level(level: ThinkingLevel, types: Any) -> Any:
        mapping = {
            ThinkingLevel.MINIMAL: types.ThinkingLevel.LOW,
            ThinkingLevel.LOW: types.ThinkingLevel.LOW,
            ThinkingLevel.MEDIUM: types.ThinkingLevel.HIGH,
            ThinkingLevel.HIGH: types.ThinkingLevel.HIGH,
        }
        return mapping.get(level, types.ThinkingLevel.HIGH)

    @staticmethod
    def _map_usage(usage_metadata: Any) -> TokenUsage:
        if usage_metadata is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
            thinking_tokens=int(getattr(usage_metadata, "thoughts_token_count", 0) or 0),
        )

    @staticmethod
    def _match_label(raw: str, labels: list[str]) -> str:
        if not labels:
            return raw
        lowered = raw.lower()
        for label in labels:
            if label.lower() == lowered:
                return label
        for label in labels:
            if label.lower() in lowered:
                return label
        return labels[0]

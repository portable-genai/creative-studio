"""Live copy adapter (CopyGenerationPort): the fleet's one local open-weight model, on the laptop.

The ``live`` profile's copywriter. It delegates every call to the shared
:class:`hex_service_kit.localmodel.LocalModelClient`, which reaches an OpenAI-compatible
``/chat/completions`` server (``LOCAL_MODEL_URL``, default ``http://127.0.0.1:8001``) serving
``LOCAL_MODEL`` (default Gemma 4 31B). That client states the response schema in the prompt,
strips a markdown fence, validates the answer and asks again with the problem named, so this
adapter only builds the messages and maps the completion back onto the domain types.

As under every profile, the model drafts copy and variant ideas and narrates the computed
checks; the deterministic brand, claim, policy and asset engines decide every verdict.
"""

from __future__ import annotations

import json
from typing import Any

from hex_service_kit.localmodel import (
    LocalCompletion,
    LocalModelClient,
    LocalModelOutputError,
    LocalModelSettings,
    LocalModelUnavailable,
)

from ...config import Settings
from ...domain.errors import ModelOutputError, ModelUnavailableError
from ...domain.models import CreativeBrief, LlmRequest, LlmResponse, TokenUsage, Variant

#: The structured shape a variant draft must take, the same one the Gemini adapter requests.
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

#: The drafting temperature the Gemini adapter uses for variants, so both profiles sample alike.
_VARIANTS_TEMPERATURE = 0.6
_VARIANTS_MAX_TOKENS = 2048
_CLASSIFY_MAX_TOKENS = 16


class LocalModelCopyAdapter:
    """Draft creative variants, narrate and triage with the local open-weight model."""

    def __init__(self, settings: Settings, *, client: LocalModelClient | None = None) -> None:
        self._settings = settings
        self._client = client or LocalModelClient(LocalModelSettings.from_env())

    # ------------------------------------------------------------------ #
    # CopyGenerationPort
    # ------------------------------------------------------------------ #
    def generate_variants(self, brief: CreativeBrief) -> tuple[Variant, ...]:
        messages = [{"role": "user", "content": self._variants_prompt(brief)}]
        completion = self._call(
            messages,
            schema=_VARIANTS_SCHEMA,
            temperature=_VARIANTS_TEMPERATURE,
            max_tokens=_VARIANTS_MAX_TOKENS,
        )
        items = completion.data.get("variants", []) if isinstance(completion.data, dict) else []
        return tuple(
            Variant(
                id="",  # assigned by the deterministic dedupe engine
                headline=str(item.get("headline", "")),
                body=str(item.get("body", "")),
                cta=str(item.get("cta", "")),
                channel=brief.channel,
                rationale=str(item.get("rationale", "")),
            )
            for item in items[: max(brief.n_variants, 1)]
            if isinstance(item, dict)
        )

    def generate(self, request: LlmRequest) -> LlmResponse:
        completion = self._call(
            self._to_messages(request),
            schema=request.response_schema,
            temperature=request.temperature,
            max_tokens=request.max_output_tokens,
        )
        return self._to_response(completion)

    def classify(self, text: str, labels: list[str]) -> str:
        prompt = (
            f"Classify the text into exactly one of these labels: {', '.join(labels)}.\n"
            "Reply with the single label only, no punctuation or explanation.\n\n"
            f"Text:\n{text}"
        )
        completion = self._call(
            [{"role": "user", "content": prompt}],
            schema=None,
            temperature=0.0,
            max_tokens=_CLASSIFY_MAX_TOKENS,
        )
        return _match_label(completion.text.strip(), labels)

    # ------------------------------------------------------------------ #
    # Client call and mapping
    # ------------------------------------------------------------------ #
    def _call(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None,
        temperature: float | None,
        max_tokens: int,
    ) -> LocalCompletion:
        """One model call: structured when a schema is given, plain text otherwise."""
        try:
            if schema is not None:
                return self._client.complete_json(
                    messages, schema=schema, temperature=temperature, max_tokens=max_tokens
                )
            return self._client.complete(messages, temperature=temperature, max_tokens=max_tokens)
        except LocalModelUnavailable as exc:
            raise ModelUnavailableError(str(exc)) from exc
        except LocalModelOutputError as exc:
            raise ModelOutputError(str(exc)) from exc

    def _variants_prompt(self, brief: CreativeBrief) -> str:
        profile = self._settings.market_profile(brief.market)
        return (
            "You are a brand-safe marketing copywriter. Draft "
            f"{max(brief.n_variants, 1)} distinct creative variants.\n"
            f"Campaign: {brief.topic}\n"
            f"Product / offer: {brief.product} / {brief.offer}\n"
            f"Market: {profile.display_name} ({brief.market.value}); "
            f"locales: {', '.join(profile.locales)}\n"
            f"Vertical: {brief.vertical.value}; channel: {brief.channel.value}\n"
            f"Audience: {brief.audience}; tone: {brief.tone}\n"
            "Qualify every claim (e.g. add 't&cs apply'); keep a calm, honest tone. "
            "Do not invent guarantees."
        )

    @staticmethod
    def _to_messages(request: LlmRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        for message in request.messages:
            role = {"model": "assistant", "system": "system"}.get(message.role, "user")
            messages.append({"role": role, "content": message.content})
        return messages

    @staticmethod
    def _to_response(completion: LocalCompletion) -> LlmResponse:
        # LlmResponse.usage is a required TokenUsage, so a server that reports no usage (MLX
        # reports none) reads as zeros here; the kit client itself returns None, never zeros.
        usage = completion.usage or TokenUsage()
        raw: dict[str, Any] | None = None
        text = completion.text
        if isinstance(completion.data, dict):
            raw = completion.data
            # Hand the domain the validated JSON, not the fenced or prefixed original.
            text = json.dumps(completion.data)
        return LlmResponse(text=text, usage=usage, model=completion.model, raw=raw)


def _match_label(raw: str, labels: list[str]) -> str:
    """Coerce the reply to one of ``labels`` (case-insensitive), as the Gemini adapter does."""
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

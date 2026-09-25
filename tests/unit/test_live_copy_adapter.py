"""The ``live`` profile: the local open-weight model behind the copy port, proved offline.

Every call goes through the shared ``hex_service_kit.localmodel`` client with a FAKE transport,
so this runs in the normal offline suite with no model server. What is proved: variant drafting
retries a fenced and then schema-invalid answer until it validates, narration maps the request
onto chat messages with its temperature unchanged, the response names the model that answered,
the kit's two failure types become the domain errors the API maps to 503 and 502, the container
builds every port under ``live``, and the image port stays on the deterministic stub.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit.localmodel import LocalModelClient, LocalModelSettings

from creative_studio.adapters.live.copy import LocalModelCopyAdapter
from creative_studio.adapters.local.image import LocalDeterministicImageAdapter
from creative_studio.config import Container
from creative_studio.domain.errors import ModelOutputError, ModelUnavailableError
from creative_studio.domain.models import (
    Channel,
    CreativeBrief,
    LlmMessage,
    LlmRequest,
    Market,
    Vertical,
)
from tests.conftest import LOOPBACK_PEER, _settings

_ANSWERED_BY = "fake-org/fake-local-model"
_BRIEF = CreativeBrief(
    topic="spring savings push",
    market=Market.SG,
    vertical=Vertical.BANKING,
    channel=Channel.EMAIL,
    product="Everyday Saver FICTIONAL",
    offer="2.10% p.a.",
    n_variants=2,
)


class _FakeTransport:
    """Answers each POST with the next scripted content and records every request body."""

    def __init__(self, *answers: str, usage: dict[str, int] | None = None) -> None:
        self._answers = list(answers)
        self._usage = usage
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes | None, timeout: float) -> bytes:
        assert body is not None
        self.bodies.append(json.loads(body))
        reply: dict[str, Any] = {
            "model": _ANSWERED_BY,
            "choices": [{"message": {"role": "assistant", "content": self._answers.pop(0)}}],
        }
        if self._usage is not None:
            reply["usage"] = self._usage
        return json.dumps(reply).encode()


def _refused(url: str, body: bytes | None, timeout: float) -> bytes:
    raise ConnectionRefusedError("connection refused")


def _adapter(transport: Any) -> LocalModelCopyAdapter:
    client = LocalModelClient(LocalModelSettings(url="http://127.0.0.1:1/x"), transport=transport)
    return LocalModelCopyAdapter(_settings("live"), client=client)


def test_a_fenced_then_invalid_variant_draft_is_retried_until_it_validates() -> None:
    good = {
        "variants": [
            {"headline": "Save steadily", "body": "Earn 2.10% p.a. T&cs apply.", "cta": "Open"},
            {"headline": "A calm way to save", "body": "2.10% p.a., t&cs apply."},
        ]
    }
    transport = _FakeTransport(
        '```json\n{"variants": [{"headline": "no body"}]}\n```',  # fenced, and missing `body`
        json.dumps(good),
    )

    variants = _adapter(transport).generate_variants(_BRIEF)

    assert len(transport.bodies) == 2, "the invalid first answer must be asked again"
    assert "body" in transport.bodies[1]["messages"][-1]["content"]
    assert [v.headline for v in variants] == ["Save steadily", "A calm way to save"]
    assert all(v.channel is Channel.EMAIL and v.id == "" for v in variants)
    assert transport.bodies[0]["temperature"] == 0.6


def test_narration_maps_the_request_with_its_temperature_unchanged() -> None:
    transport = _FakeTransport(
        'Here it is: {"summary": "All variants passed.", "used_rule_ids": []}',
        usage={"prompt_tokens": 30, "completion_tokens": 9},
    )
    request = LlmRequest(
        messages=(LlmMessage(role="user", content="Summarise the review."),),
        system_instruction="You narrate brand-safety reviews.",
        temperature=0.25,
        max_output_tokens=300,
        response_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    )

    response = _adapter(transport).generate(request)

    body = transport.bodies[0]
    assert body["temperature"] == 0.25
    assert body["max_tokens"] == 300
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"].startswith("You narrate brand-safety reviews.")
    assert body["messages"][1] == {"role": "user", "content": "Summarise the review."}
    assert json.loads(response.text)["summary"] == "All variants passed."
    assert response.model == _ANSWERED_BY
    assert (response.usage.input_tokens, response.usage.output_tokens) == (30, 9)


def test_a_draft_that_never_validates_is_a_model_output_error() -> None:
    transport = _FakeTransport("no", "still no", "never")
    with pytest.raises(ModelOutputError):
        _adapter(transport).generate_variants(_BRIEF)
    assert len(transport.bodies) == 3


def test_an_unreachable_server_is_a_model_unavailable_error_naming_the_recipe() -> None:
    with pytest.raises(ModelUnavailableError, match="mlx_vlm.server"):
        _adapter(_refused).generate_variants(_BRIEF)


def test_classify_coerces_the_answer_to_a_label() -> None:
    transport = _FakeTransport("It is: Banking")
    assert _adapter(transport).classify("text", ["retail", "banking"]) == "banking"
    assert transport.bodies[0]["temperature"] == 0.0


def test_the_container_builds_every_port_under_live_and_keeps_the_image_stub() -> None:
    settings = _settings("live")
    container = Container(settings)
    assert settings.adapters, "no port is bound, so this test would prove nothing"
    for port in settings.adapters:
        assert getattr(container, port) is not None, port
    assert isinstance(container.copy, LocalModelCopyAdapter)
    # A local open-weight text model cannot draw: images stay deterministic under live.
    assert isinstance(container.image, LocalDeterministicImageAdapter)


def test_the_banner_names_the_local_model_under_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_MODEL", _ANSWERED_BY)
    settings = _settings("live")
    assert settings.runtime == "local"
    assert settings.generator_model == _ANSWERED_BY


def test_the_api_answers_503_when_the_live_model_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from creative_studio.api import app as app_module
    from creative_studio.api import deps

    container = Container(_settings("live"))
    container.__dict__["copy"] = _adapter(_refused)
    monkeypatch.setattr(deps, "get_container", lambda: container)
    client = TestClient(app_module.app, client=LOOPBACK_PEER)

    reply = client.post("/v1/creative", json={"topic": "spring savings push"})

    assert reply.status_code == 503, reply.text
    assert "model unavailable" in reply.json()["detail"]

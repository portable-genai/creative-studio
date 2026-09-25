"""Sampling is decided per model call: pinned where the output is compared, free everywhere else.

History. This file was ``test_grounded_requests_do_not_sample.py`` and held the opposite of the
rest of the fleet: every other grounded tree pinned ``temperature`` to 0.0, and this one asserted
a deliberate 0.4 default on the request type, because a creative brief is not a consequential
number and the whole product is variation. That guard kept a fleet-wide pinning sweep from
quietly pinning this repository too.

What changed (owner decision, 2026-09-23): sampling is no longer a per-repository default at all.
Each call decides. A call whose output is extracted, classified, scored or compared pins 0.0 at
the call site; drafting, narration, summaries and explanations send NO temperature, so the model
samples at its own default. "Free" means the parameter is omitted, never 1.0, because some models
(Opus 5, Fable 5) reject it outright. The variation this repository exists for is kept, and is
now the model's own rather than a number somebody picked.

Pinned here, and why:

* ``classify`` (Gemini and live): a label is matched against a fixed list, so the same text must
  come back with the same label.
* File Search retrieval: what is kept is the grounding chunks, and the same query must retrieve
  the same evidence.

Free: variant drafting (Gemini and live), the narration summary, and the ADK agent's own turns.

The adapters are driven against a fake ``google.genai`` (no SDK), and the narration call site
through the real service with a recording copy port, so each assertion is about what a call
actually sends.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from creative_studio.adapters.gcp.file_search_kb import FileSearchKnowledgeBaseAdapter
from creative_studio.adapters.gcp.gemini_copy import GeminiCopyAdapter
from creative_studio.adapters.live.copy import LocalModelCopyAdapter
from creative_studio.adapters.local.copy import LocalTemplatedCopyAdapter
from creative_studio.api.deps import make_studio_service
from creative_studio.config import Container, Settings
from creative_studio.domain.models import (
    Channel,
    CreativeBrief,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    Market,
    RetrievalQuery,
    Vertical,
)
from tests.conftest import _settings
from tests.fixtures import fake_genai

_BRIEF = CreativeBrief(
    topic="spring savings push",
    market=Market.SG,
    vertical=Vertical.BANKING,
    channel=Channel.EMAIL,
    product="Everyday Saver FICTIONAL",
    offer="2.10% p.a.",
    n_variants=2,
)


def test_the_request_type_samples_freely_unless_a_call_pins_it() -> None:
    assert LlmRequest.__dataclass_fields__["temperature"].default is None


class _RecordingCopy(LocalTemplatedCopyAdapter):
    """The offline stub, recording every request the service hands the copy port."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.requests: list[LlmRequest] = []

    def generate(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        return super().generate(request)


def test_the_narration_summary_sends_no_temperature(local_settings: Settings) -> None:
    container = Container(local_settings)
    copy = _RecordingCopy(local_settings)
    container.__dict__["copy"] = copy

    make_studio_service(container).generate(_BRIEF, actor="demo.analyst@bank.example")

    assert copy.requests, "the service never narrated, so this test would prove nothing"
    assert all(request.temperature is None for request in copy.requests)


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> GeminiCopyAdapter:
    fake_genai.install(monkeypatch)
    adapter = GeminiCopyAdapter(_settings("gcp"))
    adapter._client = fake_genai.client(fake_genai.VARIANTS_REPLY)
    return adapter


def _configs(adapter: Any) -> list[dict[str, Any]]:
    return [call.config for call in adapter._client.models.calls]


def test_gemini_drafting_omits_temperature(gemini: GeminiCopyAdapter) -> None:
    assert gemini.generate_variants(_BRIEF)
    (config,) = _configs(gemini)
    assert "temperature" not in config
    assert config["response_mime_type"] == "application/json"


def test_gemini_classification_stays_pinned(gemini: GeminiCopyAdapter) -> None:
    gemini.classify("Save with us", ["banking", "retail"])
    (config,) = _configs(gemini)
    assert config["temperature"] == 0.0


@pytest.mark.parametrize(("temperature", "sent"), [(None, False), (0.0, True), (0.3, True)])
def test_gemini_omits_an_unset_temperature_and_keeps_a_pinned_one(
    gemini: GeminiCopyAdapter, temperature: float | None, sent: bool
) -> None:
    request = LlmRequest(
        messages=(LlmMessage(role="user", content="Summarise."),), temperature=temperature
    )
    gemini.generate(request)
    (config,) = _configs(gemini)
    assert ("temperature" in config) is sent
    if sent:
        assert config["temperature"] == temperature


def test_file_search_retrieval_stays_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_genai.install(monkeypatch)
    adapter = FileSearchKnowledgeBaseAdapter(_settings("gcp"))
    adapter._client = fake_genai.client()
    adapter.search(RetrievalQuery(text="brand tone of voice"))
    (config,) = _configs(adapter)
    assert config["temperature"] == 0.0


class _Transport:
    """A local-model server that answers every call and records the body it was sent."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes | None, timeout: float) -> bytes:
        assert body is not None
        self.bodies.append(json.loads(body))
        message = {"role": "assistant", "content": self.content}
        return json.dumps({"model": "fake-local", "choices": [{"message": message}]}).encode()


def _live(transport: _Transport) -> LocalModelCopyAdapter:
    from hex_service_kit.localmodel import LocalModelClient, LocalModelSettings

    client = LocalModelClient(LocalModelSettings(url="http://127.0.0.1:1/x"), transport=transport)
    return LocalModelCopyAdapter(_settings("live"), client=client)


def test_live_drafting_omits_temperature_and_classification_pins_it() -> None:
    drafting = _Transport(fake_genai.VARIANTS_REPLY)
    assert _live(drafting).generate_variants(_BRIEF)
    assert "temperature" not in drafting.bodies[0]

    labelling = _Transport("banking")
    _live(labelling).classify("Save with us", ["banking", "retail"])
    assert labelling.bodies[0]["temperature"] == 0.0

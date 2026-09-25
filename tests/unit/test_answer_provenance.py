"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool (owner decision, 2026-09-23). Both come
from response headers the kit emits (``install_answer_provenance`` in ``api/app.py``) for
whatever the model adapters NOTED as they called. Before a request is answered the pill shows
``generator_model`` from ``/healthz``, so that value must be the model the bound adapter calls,
never one a configuration flag names while the adapter calls another.

Here the copy port is the model: the offline stub notes the same string ``generator_model``
reports under ``local``, and under ``gcp`` the Gemini copy adapter notes its text model and the
Imagen adapter the image model, so a request that drew an image answers with both. Nothing in
this repository attaches an online search tool, so the search half is proved by standing a
noting adapter in for the real one on the real route.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from creative_studio.adapters.gcp.gemini_copy import GeminiCopyAdapter
from creative_studio.adapters.gcp.imagen_image import ImagenImageAdapter
from creative_studio.adapters.local.copy import LocalTemplatedCopyAdapter
from creative_studio.api import deps
from creative_studio.api.app import app
from creative_studio.config import Container, ModelSettings, Settings
from creative_studio.domain.models import CreativeBrief, LlmMessage, LlmRequest
from tests.conftest import LOOPBACK_PEER, _settings
from tests.fixtures import fake_genai

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
_CREATIVE_BODY = {
    "topic": "high-yield savings",
    "market": "SG",
    "vertical": "banking",
    "channel": "email",
    "offer": "4.10% p.a.",
}


def _client(monkeypatch: pytest.MonkeyPatch, container: Container) -> TestClient:
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def _create(client: TestClient, **extra: object) -> dict[str, str]:
    response = client.post("/v1/creative", json={**_CREATIVE_BODY, **extra})
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_offline_stub_answers_as_the_model_the_pill_already_names(
    monkeypatch: pytest.MonkeyPatch, local_container: Container
) -> None:
    """Under ``local`` the pill must not move from the configured string to another one.

    The image port is a deterministic stub under ``local`` and notes nothing, so a request that
    drew an image still names only the copy stub.
    """
    headers = _create(_client(monkeypatch, local_container), with_image=True)
    assert headers[ANSWERED_BY] == local_container.settings.generator_model
    assert headers[ANSWERED_BY] == "deterministic-offline-stub"
    assert SEARCH_USED not in headers


def test_a_request_that_called_no_model_sends_neither_header(
    monkeypatch: pytest.MonkeyPatch, local_container: Container
) -> None:
    """Nothing noted, nothing sent: the pill never invents a model nothing called."""
    response = _client(monkeypatch, local_container).get("/healthz")
    assert response.status_code == 200, response.text
    assert ANSWERED_BY not in response.headers
    assert SEARCH_USED not in response.headers


class _SearchingCopy(LocalTemplatedCopyAdapter):
    """The real stub, plus what a copy adapter that attached a search tool would note."""

    def generate_variants(self, brief: CreativeBrief) -> tuple:  # type: ignore[type-arg]
        provenance.note_model("fake-searching-model")
        provenance.note_search()
        return super().generate_variants(brief)


def test_the_route_says_when_an_answer_searched_and_forgets_it_next_request(
    monkeypatch: pytest.MonkeyPatch, local_settings: Settings
) -> None:
    container = Container(local_settings)
    container.__dict__["copy"] = _SearchingCopy(local_settings)
    client = _client(monkeypatch, container)
    headers = _create(client)
    assert headers[ANSWERED_BY] == "fake-searching-model, deterministic-offline-stub"
    assert headers[SEARCH_USED] == "true"

    # The next request is a fresh record: a search never leaks into a later response.
    container.__dict__["copy"] = LocalTemplatedCopyAdapter(local_settings)
    headers = _create(client)
    assert headers[ANSWERED_BY] == "deterministic-offline-stub"
    assert SEARCH_USED not in headers


def test_the_cross_origin_console_can_read_both_headers(
    monkeypatch: pytest.MonkeyPatch, local_container: Container
) -> None:
    """This console calls the service directly, so a cross-origin response must EXPOSE them.

    A header not named in ``Access-Control-Expose-Headers`` is invisible to the page's
    JavaScript, and the pill would sit on the configured model forever with every server-side
    assertion above still green.
    """
    response = _client(monkeypatch, local_container).post(
        "/v1/creative", json=_CREATIVE_BODY, headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200, response.text
    exposed = {
        h.strip().lower() for h in response.headers["access-control-expose-headers"].split(",")
    }
    assert {ANSWERED_BY, SEARCH_USED} <= exposed


def test_under_gcp_a_request_that_drew_an_image_answers_with_both_models(
    monkeypatch: pytest.MonkeyPatch, local_settings: Settings
) -> None:
    """The managed adapters note the ids they PASSED to the model call, copy and image both."""
    fake_genai.install(monkeypatch)
    container = Container(local_settings)
    copy = GeminiCopyAdapter(local_settings)
    copy._client = fake_genai.client(fake_genai.VARIANTS_REPLY)
    image = ImagenImageAdapter(local_settings)
    image._client = fake_genai.client()
    container.__dict__["copy"] = copy
    container.__dict__["image"] = image

    headers = _create(_client(monkeypatch, container), with_image=True)

    called = [call.model for call in copy._client.models.calls]
    called += [call.model for call in image._client.models.calls]
    assert called, "no managed call was made, so this test would prove nothing"
    assert headers[ANSWERED_BY] == ", ".join(dict.fromkeys(called))
    assert headers[ANSWERED_BY] == (
        f"{local_settings.models.reasoning}, {local_settings.models.image_model}"
    )
    assert SEARCH_USED not in headers


def test_a_failed_managed_call_notes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model that never answered must not appear on the pill."""
    fake_genai.install(monkeypatch)
    adapter = GeminiCopyAdapter(_settings("gcp"))
    client = fake_genai.client()

    def refuse(**_: object) -> object:
        raise RuntimeError("quota exceeded")

    client.models.generate_content = refuse
    adapter._client = client
    request = LlmRequest(messages=(LlmMessage(role="user", content="Summarise."),))
    with provenance.scope() as record, pytest.raises(RuntimeError):
        adapter.generate(request)
    assert record.models == []


def test_generator_model_under_gcp_is_the_model_the_adapter_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pill before an answer and the pill after one must name the same model."""
    fake_genai.install(monkeypatch)
    settings = _settings("gcp")
    adapter = GeminiCopyAdapter(settings)
    adapter._client = fake_genai.client()
    request = LlmRequest(messages=(LlmMessage(role="user", content="Summarise."),))

    with provenance.scope() as record:
        adapter.generate(request)

    assert adapter._client.models.calls[0].model == settings.generator_model
    assert record.models == [settings.generator_model]


def test_the_hard_reasoning_flag_is_gone() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered.

    ``generator_model`` once named ``models.hard_reasoning`` when ``models.use_hard_reasoning``
    was set, while the Gemini adapter called ``request.model or models.reasoning`` and never read
    the flag. The pill would then have named a model that never answered. Both settings are
    deleted rather than wired, so nothing can put that model on screen again.
    """
    fields = {f.name for f in dataclasses.fields(ModelSettings)}
    assert "use_hard_reasoning" not in fields
    assert "hard_reasoning" not in fields
    assert "hard_reasoning" not in Path("config/settings.yaml").read_text(encoding="utf-8")
    for source in sorted(Path("src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source

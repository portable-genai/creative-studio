"""The Model Armor adapter allows ONLY a complete, clean screen, and fails closed otherwise.

The adapter calls Model Armor's REST API, so it reads the proto3 JSON mapping of
``modelarmor_v1.SanitizationResult``: enums arrive as member NAMES, and a zero-valued enum
(``..._UNSPECIFIED``) is omitted. The old mapping was
``allowed = match_state != "MATCH_FOUND" if match_state is not None else not findings``, which
failed OPEN three ways:

* an explicit ``FILTER_MATCH_STATE_UNSPECIFIED`` (or any unknown value) was "not MATCH_FOUND";
* a missing or empty ``sanitizationResult`` has no parsed findings, so ``not findings`` allowed;
* ``invocationResult`` was never read, so ``NO_MATCH_FOUND`` with ``PARTIAL`` or ``FAILURE``
  (a screen where some or all filters were skipped, e.g. a prompt padded past the
  prompt-injection filter's token limit) allowed text that was never screened.

Only ``filterMatchState == "NO_MATCH_FOUND"`` with ``invocationResult == "SUCCESS"`` allows.

This module tests at two levels:

* **SDK-free** (always runs, including CI's SDK-free ``make test``): JSON bodies built from
  ``_MirrorState`` / ``_MirrorInvocation``, stdlib enums with the real member names and
  numbers, are screened through ``screen()`` with a fake HTTP client.
* **Real SDK** (runs where ``google-cloud-modelarmor`` is installed, skips otherwise): the
  bodies are real ``modelarmor_v1`` messages rendered to JSON exactly as the REST API sends
  them, screened the same way. The first of these tests pins the mirror to the real enums, so
  the SDK-free half cannot drift.
"""

from __future__ import annotations

import enum
import json
from typing import Any

import httpx
import pytest

from creative_studio.adapters.gcp.model_armor_guardrail import ModelArmorGuardrailAdapter
from creative_studio.config import Settings
from creative_studio.domain.models import Direction, GuardrailCategory

TEXT = "Write a launch headline for the new savings account."
DIRECTIONS = [Direction.INPUT, Direction.OUTPUT]


class _MirrorState(enum.IntEnum):
    """``modelarmor_v1.FilterMatchState``'s members, by name and number."""

    FILTER_MATCH_STATE_UNSPECIFIED = 0
    NO_MATCH_FOUND = 1
    MATCH_FOUND = 2


class _MirrorInvocation(enum.IntEnum):
    """``modelarmor_v1.InvocationResult``'s members, by name and number."""

    INVOCATION_RESULT_UNSPECIFIED = 0
    SUCCESS = 1
    PARTIAL = 2
    FAILURE = 3


# --------------------------------------------------------------------------- #
# Fake transport: the adapter's own screen() runs, nothing touches the network
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, body: Any, status: int = 200) -> None:
        self._body = body
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            request = httpx.Request("POST", "https://modelarmor.test")
            raise httpx.HTTPStatusError(
                f"{self._status}",
                request=request,
                response=httpx.Response(self._status, request=request),
            )

    def json(self) -> Any:
        return self._body


class _FakeClient:
    """Answers every sanitize POST with a canned body, status or error."""

    def __init__(
        self, body: Any = None, *, status: int = 200, error: Exception | None = None
    ) -> None:
        self._body = body
        self._status = status
        self._error = error
        self.urls: list[str] = []
        self.timeouts: list[Any] = []

    def post(self, url: str, *, json: Any, headers: Any, timeout: Any = None) -> _FakeResponse:
        self.urls.append(url)
        self.timeouts.append(timeout)
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._body, self._status)


def _adapter(client: _FakeClient, monkeypatch: pytest.MonkeyPatch) -> ModelArmorGuardrailAdapter:
    adapter = ModelArmorGuardrailAdapter(Settings(project_id="p", profile="gcp"))
    adapter._client = client  # skip the real client; the mapping is what is under test
    monkeypatch.setattr(adapter, "_bearer_token", lambda: "test-token")
    return adapter


def _screen(
    body: Any, monkeypatch: pytest.MonkeyPatch, direction: Direction = Direction.INPUT
) -> Any:
    return _adapter(_FakeClient(body), monkeypatch).screen(TEXT, direction)


def _mirror_body(
    state: _MirrorState | None,
    invocation: _MirrorInvocation | None = _MirrorInvocation.SUCCESS,
    filter_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A REST body as proto3 JSON renders it: names, and zero-valued enums omitted."""
    result: dict[str, Any] = {}
    if state is not None and state.value != 0:
        result["filterMatchState"] = state.name
    if invocation is not None and invocation.value != 0:
        result["invocationResult"] = invocation.name
    if filter_results:
        result["filterResults"] = filter_results
    return {"sanitizationResult": result}


_PI_MATCH = {
    "pi_and_jailbreak": {
        "piAndJailbreakFilterResult": {
            "executionState": "EXECUTION_SUCCESS",
            "matchState": "MATCH_FOUND",
            "confidenceLevel": "HIGH",
        }
    }
}


# --------------------------------------------------------------------------- #
# SDK-free: the mapping itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks_sdk_free(direction: Direction, monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = _screen(
        _mirror_body(_MirrorState.MATCH_FOUND, filter_results=_PI_MATCH), monkeypatch, direction
    )
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert [f.category for f in verdict.findings] == [GuardrailCategory.PROMPT_INJECTION]


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows_sdk_free(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND), monkeypatch, direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT
    assert verdict.findings == ()


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation", list(_MirrorInvocation), ids=lambda m: m.name)
def test_match_found_blocks_however_many_filters_ran_sdk_free(
    direction: Direction, invocation: _MirrorInvocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_mirror_body(_MirrorState.MATCH_FOUND, invocation), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert verdict.findings


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "invocation",
    [
        _MirrorInvocation.PARTIAL,
        _MirrorInvocation.FAILURE,
        _MirrorInvocation.INVOCATION_RESULT_UNSPECIFIED,
        None,
    ],
    ids=["PARTIAL", "FAILURE", "UNSPECIFIED", "absent"],
)
def test_no_match_from_an_incomplete_screen_blocks_sdk_free(
    direction: Direction, invocation: _MirrorInvocation | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skipped filter reports no match. That is not a pass: the text was not screened."""
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND, invocation), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_exactly_one_combination_allows_sdk_free(monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = [
        (state.name, invocation.name)
        for state in _MirrorState
        for invocation in _MirrorInvocation
        if _screen(_mirror_body(state, invocation), monkeypatch).allowed
    ]
    assert allowed == [("NO_MATCH_FOUND", "SUCCESS")]


@pytest.mark.parametrize(
    "body",
    [
        _mirror_body(_MirrorState.FILTER_MATCH_STATE_UNSPECIFIED),
        {"sanitizationResult": {"filterMatchState": "FILTER_MATCH_STATE_UNSPECIFIED"}},
        {
            "sanitizationResult": {
                "filterMatchState": "SOMETHING_NEW",
                "invocationResult": "SUCCESS",
            }
        },
        # An integer-encoded body is not the wire shape this adapter requests; it must not pass.
        {"sanitizationResult": {"filterMatchState": 1, "invocationResult": 1}},
        {"sanitizationResult": {}},
        {"sanitizationResult": None},
        {},
        None,
        [],
    ],
    ids=[
        "unspecified-omitted",
        "unspecified-explicit",
        "unknown-state",
        "integer-encoded",
        "empty-result",
        "null-result",
        "no-result",
        "null-body",
        "non-object-body",
    ],
)
def test_no_verdict_fails_closed_sdk_free(body: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = _screen(body, monkeypatch)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_call_carries_the_deadline(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FakeClient(_mirror_body(_MirrorState.NO_MATCH_FOUND))
    _adapter(client, monkeypatch).screen(TEXT, direction)
    assert client.timeouts == [Settings().model_armor.timeout_seconds]
    assert client.timeouts[0] > 0


@pytest.mark.parametrize(
    "client",
    [
        _FakeClient(status=503),
        _FakeClient(status=403),
        _FakeClient(error=httpx.ReadTimeout("deadline exceeded")),
        _FakeClient(error=httpx.ConnectError("unreachable")),
    ],
    ids=["503", "403", "timeout", "connect-error"],
)
def test_api_errors_propagate(client: _FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """An API failure must not turn into an allow; it reaches the caller, which audits it."""
    with pytest.raises(httpx.HTTPError):
        _adapter(client, monkeypatch).screen(TEXT, Direction.INPUT)


# --------------------------------------------------------------------------- #
# Real SDK: real modelarmor_v1 messages, rendered to JSON as the REST API sends them
# --------------------------------------------------------------------------- #
def _ma() -> Any:
    return pytest.importorskip("google.cloud.modelarmor_v1")


def _to_wire(cls: Any, message: Any) -> Any:
    """Render a message as the REST API's proto3 JSON: enum names, camelCase, defaults omitted."""
    return json.loads(
        cls.to_json(
            message, use_integers_for_enums=False, always_print_fields_with_no_presence=False
        )
    )


def _real_body(
    direction: Direction,
    state_name: str | None,
    invocation_name: str = "SUCCESS",
    *,
    skipped: bool = False,
) -> Any:
    """A real sanitize response as REST JSON; ``state_name=None`` leaves the result unset.

    ``skipped`` adds the prompt-injection filter as not having run, the shape a prompt padded
    past that filter's token limit produces.
    """
    ma = _ma()
    cls = (
        ma.SanitizeUserPromptResponse
        if direction is Direction.INPUT
        else ma.SanitizeModelResponseResponse
    )
    if state_name is None:
        message = cls()
    else:
        filter_results = {}
        if skipped:
            filter_results["pi_and_jailbreak"] = ma.FilterResult(
                pi_and_jailbreak_filter_result=ma.PiAndJailbreakFilterResult(
                    execution_state=ma.FilterExecutionState.EXECUTION_SKIPPED,
                    match_state=ma.FilterMatchState.NO_MATCH_FOUND,
                )
            )
        message = cls(
            sanitization_result=ma.SanitizationResult(
                filter_match_state=ma.FilterMatchState[state_name],
                invocation_result=ma.InvocationResult[invocation_name],
                filter_results=filter_results,
            )
        )
    return _to_wire(cls, message)


@pytest.mark.parametrize(
    ("mirror", "real_name"),
    [(_MirrorState, "FilterMatchState"), (_MirrorInvocation, "InvocationResult")],
    ids=["FilterMatchState", "InvocationResult"],
)
def test_the_mirror_matches_the_real_enum(mirror: Any, real_name: str) -> None:
    real = getattr(_ma(), real_name)
    assert {m.name: int(m) for m in real} == {m.name: int(m) for m in mirror}


def test_the_mirror_body_is_the_real_wire_shape() -> None:
    """The SDK-free bodies are exactly what the real messages render to."""
    ma = _ma()
    for state in _MirrorState:
        for invocation in _MirrorInvocation:
            message = ma.SanitizeUserPromptResponse(
                sanitization_result=ma.SanitizationResult(
                    filter_match_state=ma.FilterMatchState[state.name],
                    invocation_result=ma.InvocationResult[invocation.name],
                )
            )
            real = _to_wire(ma.SanitizeUserPromptResponse, message)
            real.setdefault("sanitizationResult", {})
            assert real == _mirror_body(state, invocation)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks(direction: Direction, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(_real_body(direction, "MATCH_FOUND"))
    verdict = _adapter(client, monkeypatch).screen(TEXT, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert len(client.urls) == 1


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_real_body(direction, "NO_MATCH_FOUND"), monkeypatch, direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "state_name",
    [None, "FILTER_MATCH_STATE_UNSPECIFIED"],
    ids=["missing-result", "unspecified-state"],
)
def test_no_verdict_fails_closed(
    direction: Direction, state_name: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_real_body(direction, state_name), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation_name", ["PARTIAL", "FAILURE", "INVOCATION_RESULT_UNSPECIFIED"])
def test_no_match_from_a_screen_where_filters_did_not_run_blocks(
    direction: Direction, invocation_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _real_body(direction, "NO_MATCH_FOUND", invocation_name, skipped=True)
    verdict = _screen(body, monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason

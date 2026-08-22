"""Both studio request paths open ONE span each, and those spans carry no content.

A trace backend is not the WORM audit trail: it has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. The value of tracing the studio pipeline therefore depends on each span carrying
structural attributes only (which market), never the brief's topic or offer, a drafted
headline, or any identifier a marketer typed in.

The container's local tracer only logs span names, so a leaked attribute would be invisible
to the rest of the suite; this module swaps in a tracer that records the attributes too and
drives BOTH real request paths (generate and review) with a planted, obviously fictional
identifier in the brief so a leak would actually show.
"""

from __future__ import annotations

from contextlib import contextmanager

from creative_studio.config import Container
from creative_studio.domain.models import (
    Channel,
    CreativeBrief,
    Market,
    Variant,
    Vertical,
)
from creative_studio.domain.services import CreativeStudioService

#: The full attribute allowlist per span name. A new attribute is a deliberate decision
#: made here, not a drive-by keyword argument.
_ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "creative.generate": frozenset({"market"}),
    "creative.review": frozenset({"market"}),
}

#: Planted content markers (all obviously fictional). If any span attribute value carried
#: the brief or variant content, one of these would surface in the recorded attributes.
_PLANTED_IDENTIFIER = "S1234567D"
_PLANTED_TOPIC = f"seasonal offer for customer {_PLANTED_IDENTIFIER} (PLANTED, FICTIONAL)"
_PLANTED_HEADLINE = f"A headline naming {_PLANTED_IDENTIFIER} (PLANTED, FICTIONAL)"


class _RecordingTracer:
    """Records every span name AND its attributes, unlike the name-only local tracer."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str):  # type: ignore[no-untyped-def]
        self.spans.append((name, dict(attributes)))
        yield


def _service(container: Container, tracer: _RecordingTracer) -> CreativeStudioService:
    return CreativeStudioService(
        copy=container.copy,
        image=container.image,
        knowledge_base=container.knowledge_base,
        guardrail=container.guardrail,
        tracer=tracer,
        audit=container.audit,
    )


def _brief() -> CreativeBrief:
    return CreativeBrief(
        topic=_PLANTED_TOPIC,
        market=Market.SG,
        vertical=Vertical.BANKING,
        channel=Channel.EMAIL,
        product="our product",
        offer="a clear offer",
    )


def _generate_spans(container: Container) -> _RecordingTracer:
    tracer = _RecordingTracer()
    _service(container, tracer).generate(_brief(), actor="span-test-bot (FICTIONAL)")
    return tracer


def _review_spans(container: Container) -> _RecordingTracer:
    tracer = _RecordingTracer()
    variant = Variant(
        id="",
        headline=_PLANTED_HEADLINE,
        body="A balanced, brand-safe body with no guarantees.",
        cta="Learn more",
        channel=Channel.EMAIL,
    )
    _service(container, tracer).review(_brief(), variant, actor="span-test-bot (FICTIONAL)")
    return tracer


def _all_spans(container: Container) -> list[tuple[str, dict[str, str]]]:
    return _generate_spans(container).spans + _review_spans(container).spans


def test_each_request_path_opens_exactly_one_named_span(local_container: Container) -> None:
    assert [n for n, _ in _generate_spans(local_container).spans] == ["creative.generate"]
    assert [n for n, _ in _review_spans(local_container).spans] == ["creative.review"]


def test_every_span_attribute_set_is_a_fixed_allowlist(local_container: Container) -> None:
    """No span may start attaching brief or variant content to explain itself."""
    for name, attributes in _all_spans(local_container):
        assert name in _ALLOWED_ATTRIBUTES, f"unexpected span {name!r}"
        assert set(attributes) == _ALLOWED_ATTRIBUTES[name], name


def test_no_span_attribute_value_carries_planted_content(local_container: Container) -> None:
    """The brief topic and the reviewed headline carry planted markers, so a leak shows."""
    emitted = " ".join(
        value for _, attributes in _all_spans(local_container) for value in attributes.values()
    )
    assert _PLANTED_IDENTIFIER not in emitted
    assert _PLANTED_IDENTIFIER.lower() not in emitted.lower()
    assert _PLANTED_TOPIC not in emitted
    assert _PLANTED_HEADLINE not in emitted


def test_the_market_attribute_is_structural_not_content(local_container: Container) -> None:
    """The one allowed attribute answers "which market", nothing about the request text."""
    for name, attributes in _all_spans(local_container):
        assert attributes["market"] == Market.SG.value, name

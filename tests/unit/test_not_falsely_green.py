"""Prove every eval metric can go RED: a degraded result must score below its threshold.

A metric that cannot fail proves nothing. Each scorer in ``eval/run_eval.py`` is fed the SAME
studio output twice: once as the pipeline produced it (green) and once carrying exactly the
defect the metric exists to catch (red). The scorers are imported rather than re-implemented,
so a scorer that silently became a constant 1.0 breaks this build.

The groundedness and citation cases deliberately use a brief that RAISES findings: a brief
with no findings scores a vacuous 1.0, which would make the proof itself meaningless.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from agent_eval_kit import assert_can_go_red
from eval.run_eval import (
    _BAD_VARIANT,
    THRESHOLDS,
    _make_service,
    score_brand_safety_detection,
    score_citation_accuracy,
    score_groundedness,
    score_review_safety,
)

from creative_studio.domain.models import (
    Channel,
    CreativeBrief,
    CreativeStudioResult,
    Market,
    SourceType,
    Variant,
    Vertical,
)

_ACTOR = "eval-bot"

#: A brief that provably raises findings, so the citation metrics score something real.
_BRIEF = CreativeBrief(
    topic="home loan refinance",
    market=Market.AU,
    vertical=Vertical.BANKING,
    channel=Channel.SEARCH,
    product="home loan refinance",
    offer="a clear offer",
)

#: Carries the disclosure the AU/SG financial-promotion rules require, so it is approvable.
_CLEAN_VARIANT = Variant(
    id="",
    headline="Refinance your home loan",
    body="Interest rates vary by lender. T&Cs apply.",
    cta="Compare rates",
)


@pytest.fixture(scope="module")
def result() -> CreativeStudioResult:
    """One real studio result off the local (SDK-free) stack: the green case."""
    generated = _make_service().generate(_BRIEF, actor=_ACTOR)
    assert generated.all_findings, "the proof needs a brief that raises findings"
    return generated


def _map_checks(res: CreativeStudioResult, fn):  # type: ignore[no-untyped-def]
    """Rebuild the result with ``fn`` applied to every check on every review."""
    return replace(
        res,
        reviews=tuple(
            replace(r, brand=fn(r.brand), claim=fn(r.claim), policy=fn(r.policy), asset=fn(r.asset))
            for r in res.reviews
        ),
    )


def test_check_groundedness_can_go_red(result: CreativeStudioResult) -> None:
    uncited = _map_checks(
        result,
        lambda c: replace(c, findings=tuple(replace(f, citations=()) for f in c.findings)),
    )
    assert_can_go_red(
        score_groundedness,
        green=result,
        red=uncited,  # findings raised against nothing citable
        threshold=THRESHOLDS["check_groundedness"],
        metric="check_groundedness",
    )


def test_citation_accuracy_can_go_red(result: CreativeStudioResult) -> None:
    off_namespace = _map_checks(
        result,
        lambda c: replace(
            c,
            findings=tuple(
                replace(
                    f,
                    citations=tuple(
                        replace(cit, source_type=SourceType.OTHER) for cit in f.citations
                    ),
                )
                for f in c.findings
            ),
        ),
    )
    assert_can_go_red(
        score_citation_accuracy,
        green=result,
        red=off_namespace,  # cited outside the brand/claim/policy/asset namespaces
        threshold=THRESHOLDS["citation_accuracy"],
        metric="citation_accuracy",
    )


def test_brand_safety_detection_can_go_red() -> None:
    """A detector that flags everything is as useless as one that flags nothing.

    Green is the deliberately non-compliant variant the eval scores; red is a compliant one,
    which must be APPROVED. A studio that refused everything would keep scoring 1.0 here.
    """
    service = _make_service()
    assert_can_go_red(
        lambda variant: score_brand_safety_detection(service.review(_BRIEF, variant, actor=_ACTOR)),
        green=_BAD_VARIANT,
        red=_CLEAN_VARIANT,
        threshold=THRESHOLDS["brand_safety_detection"],
        metric="brand_safety_detection",
    )


def test_review_safety_can_go_red(result: CreativeStudioResult) -> None:
    assert_can_go_red(
        score_review_safety,
        green=result,
        red=replace(result, requires_human_review=False),  # the human gate quietly dropped
        threshold=THRESHOLDS["review_safety"],
        metric="review_safety",
    )

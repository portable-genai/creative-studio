"""The wire/audit view must carry the verdicts the deterministic engines computed.

``to_jsonable`` walks ``dataclasses.fields``, and ``VariantReview.status`` / ``.approved``
are properties, so the bare walker silently dropped both. Every consumer then fell back to
its own default: the console rendered "warn" for variants the engines passed and reported
"0/N passed". These tests pin the derived verdicts onto the serialized shape, so a review
that the engines pass can never be served as a warn again.
"""

from __future__ import annotations

from creative_studio.domain.models import (
    AssetCheck,
    BrandCheck,
    Channel,
    CheckStatus,
    Citation,
    ClaimCheck,
    CreativeBrief,
    CreativeStudioResult,
    Finding,
    Market,
    PolicyCheck,
    RuleSeverity,
    SourceType,
    Variant,
    VariantReview,
    Vertical,
)
from creative_studio.domain.serialization import result_jsonable, review_jsonable, to_jsonable


def _variant(vid: str) -> Variant:
    return Variant(
        id=vid,
        headline="A clear headline",
        body="Obviously fictional body copy.",
        cta="Learn more",
        channel=Channel.EMAIL,
    )


def _review(vid: str, *, findings: tuple[Finding, ...] = ()) -> VariantReview:
    """A review whose four checks are clean unless ``findings`` says otherwise."""
    worst = CheckStatus.PASS
    for finding in findings:
        if finding.severity in (RuleSeverity.HIGH, RuleSeverity.CRITICAL):
            worst = CheckStatus.FAIL
        elif worst is CheckStatus.PASS:
            worst = CheckStatus.WARN
    return VariantReview(
        variant=_variant(vid),
        brand=BrandCheck(variant_id=vid, status=worst, findings=findings),
        claim=ClaimCheck(variant_id=vid, status=CheckStatus.PASS),
        policy=PolicyCheck(
            variant_id=vid,
            market=Market.SG,
            vertical=Vertical.BANKING,
            status=CheckStatus.PASS,
        ),
        asset=AssetCheck(variant_id=vid, channel=Channel.EMAIL, status=CheckStatus.PASS),
    )


def test_bare_walker_drops_the_derived_verdicts() -> None:
    """Characterizes the defect this module exists to correct."""
    review = _review("v1")
    assert review.status is CheckStatus.PASS
    assert review.approved is True

    bare = to_jsonable(review)
    assert "status" not in bare
    assert "approved" not in bare


def test_review_jsonable_carries_the_engine_verdict() -> None:
    review = _review("v1")
    data = review_jsonable(review)

    assert data["status"] == "pass"
    assert data["approved"] is True
    # The four checks and the variant still serialize exactly as before.
    assert data["variant"]["id"] == "v1"
    assert data["brand"]["status"] == "pass"


def test_review_jsonable_carries_a_failing_verdict() -> None:
    finding = Finding(
        rule_id="brand.tone",
        severity=RuleSeverity.CRITICAL,
        message="Prohibited superlative.",
        citations=(
            Citation(
                source_id="brand-guide-001",
                source_type=SourceType.BRAND_GUIDELINE,
                title="Tone of voice",
            ),
        ),
    )
    data = review_jsonable(_review("v2", findings=(finding,)))

    assert data["status"] == "fail"
    assert data["approved"] is False


def test_result_jsonable_reports_every_passing_variant_as_passing() -> None:
    """The regression: three clean variants must serialize as 3 approved, not 0."""
    result = CreativeStudioResult(
        id="creative-test",
        brief=CreativeBrief(
            topic="high-yield savings",
            market=Market.SG,
            vertical=Vertical.BANKING,
            channel=Channel.EMAIL,
        ),
        reviews=tuple(_review(f"v{n}") for n in range(1, 4)),
        summary="All three variants cleared every deterministic check.",
    )
    data = result_jsonable(result)

    assert [r["status"] for r in data["reviews"]] == ["pass", "pass", "pass"]
    assert sum(1 for r in data["reviews"] if r["approved"]) == 3
    assert sum(1 for r in result.reviews if r.approved) == 3
    # Plain fields keep their existing shape.
    assert data["id"] == "creative-test"
    assert data["requires_human_review"] is True

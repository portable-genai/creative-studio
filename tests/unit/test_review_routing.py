"""R8 routing: an escalated creative result is routed to Hrz7 via the shared review-kit.

Every ``CreativeStudioResult`` requires human review (P-06), so rule R8 says it MUST be handed to
the Hrz7 maker-checker console rather than left as a boolean. These tests prove the producer half
of that loop end-to-end against the offline local router (an in-memory outbox), prove the
redact-before-wire boundary so no stray contact identifier reaches the console, and prove that a
failed / high-severity result maps to dual control. All data is fictional.
"""

from __future__ import annotations

import pytest

from creative_studio.adapters._review_payload import result_to_review
from creative_studio.adapters.local.review_router import LocalReviewRouter
from creative_studio.api.deps import make_studio_service
from creative_studio.config import Container
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

ACTOR = "planner@studio.test"
TENANT = "demo-brand"


def test_generate_routes_escalated_result_to_outbox(local_container: Container) -> None:
    """A completed generation enqueues exactly one review to the router's outbox (R8)."""
    service = make_studio_service(local_container)
    router = local_container.review_router
    assert isinstance(router, LocalReviewRouter)
    assert not router.outbox.pending()

    brief = CreativeBrief(
        topic="seasonal savings push",
        market=Market.SG,
        vertical=Vertical.BANKING,
        channel=Channel.EMAIL,
        product="high-yield savings account",
        offer="a clear offer",
    )
    result = service.generate(brief, actor=ACTOR, with_image=True, tenant=TENANT)
    assert result.requires_human_review

    pending = router.outbox.pending()
    assert len(pending) == 1, "the escalated creative must be routed to Hrz7 exactly once"
    review = pending[0].review
    assert review.action == f"creative_asset:{brief.channel.value}"
    assert review.case_ref == result.id
    assert review.maker == ACTOR
    assert review.tenant == TENANT


def _failed_result_with_pii() -> CreativeStudioResult:
    brief = CreativeBrief(
        topic="spring apparel sale",
        market=Market.AU,
        vertical=Vertical.ONLINE_RETAIL,
        channel=Channel.EMAIL,
        product="spring apparel",
        offer="20% off",
    )
    # A citation snippet carrying a fictional contact identifier: it must be masked before the wire.
    cite = Citation(
        source_id="policy-au-01",
        source_type=SourceType.AD_POLICY,
        title="AU advertising policy",
        snippet="Escalate to reviewer promo-desk@studio.test or call +61 2 5550 1234.",
    )
    finding = Finding(
        rule_id="AU-CLAIM-3",
        severity=RuleSeverity.HIGH,
        message="Unsubstantiated superlative claim.",
        citations=(cite,),
    )
    variant = Variant(
        id="var-1", headline="Best deal ever", body="Shop now.", channel=Channel.EMAIL
    )
    review = VariantReview(
        variant=variant,
        brand=BrandCheck(variant_id="var-1", status=CheckStatus.PASS),
        claim=ClaimCheck(variant_id="var-1", status=CheckStatus.FAIL, findings=(finding,)),
        policy=PolicyCheck(
            variant_id="var-1",
            market=Market.AU,
            vertical=Vertical.ONLINE_RETAIL,
            status=CheckStatus.PASS,
        ),
        asset=AssetCheck(variant_id="var-1", channel=Channel.EMAIL, status=CheckStatus.PASS),
    )
    return CreativeStudioResult(
        id="creative-au-online_retail-email",
        brief=brief,
        reviews=(review,),
        summary="1 variant failed the claim check.",
        citations=(cite,),
    )


def test_payload_is_redacted_and_carries_tenant_and_severity() -> None:
    """The wire payload masks identifiers, carries the tenant, and maps the worst severity (R8)."""
    review = result_to_review(_failed_result_with_pii(), maker=ACTOR, tenant=TENANT)

    assert review.tenant == TENANT
    assert review.severity == "high"
    assert review.required_approvals == 2, "a failed / HIGH-severity result warrants dual control"
    # No raw contact identifier survives into the payload the console receives.
    assert "promo-desk@studio.test" not in review.subject
    assert "promo-desk@studio.test" not in review.summary
    for citation in review.citations:
        assert "promo-desk@studio.test" not in citation.snippet
        assert "5550 1234" not in citation.snippet
    assert any(c.title == "AU advertising policy" for c in review.citations)


def test_clean_result_maps_to_single_approval() -> None:
    """A clean creative (no failed variants) escalates with single-control severity."""
    brief = CreativeBrief(
        topic="welcome offer",
        market=Market.SG,
        vertical=Vertical.BANKING,
        channel=Channel.EMAIL,
    )
    variant = Variant(id="var-1", headline="Welcome", body="Join today.", channel=Channel.EMAIL)
    review = VariantReview(
        variant=variant,
        brand=BrandCheck(variant_id="var-1", status=CheckStatus.PASS),
        claim=ClaimCheck(variant_id="var-1", status=CheckStatus.PASS),
        policy=PolicyCheck(
            variant_id="var-1", market=Market.SG, vertical=Vertical.BANKING, status=CheckStatus.PASS
        ),
        asset=AssetCheck(variant_id="var-1", channel=Channel.EMAIL, status=CheckStatus.PASS),
    )
    result = CreativeStudioResult(id="creative-clean", brief=brief, reviews=(review,))
    payload = result_to_review(result, maker=ACTOR, tenant=TENANT)
    assert payload.required_approvals == 1
    assert payload.severity == "low"


def test_no_router_still_assembles_result(local_container: Container) -> None:
    """Routing is optional: with no router bound, generation still returns an escalated result."""
    service = make_studio_service(local_container)
    service._review_router = None  # type: ignore[attr-defined]  # simulate an unbound router
    brief = CreativeBrief(
        topic="seasonal offer",
        market=Market.SG,
        vertical=Vertical.BANKING,
        channel=Channel.EMAIL,
        offer="a clear offer",
    )
    result = service.generate(brief, actor=ACTOR, with_image=True)
    assert result.requires_human_review


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

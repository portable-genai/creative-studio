"""Unit tests for the deterministic ClaimValidationService (pure, replayable)."""

from __future__ import annotations

from creative_studio.domain.claim_service import ClaimValidationService, _contains
from creative_studio.domain.models import Channel, CheckStatus, Market, Variant, Vertical
from creative_studio.domain.rules import claim_rules_for


def _variant(headline: str, body: str = "", cta: str = "") -> Variant:
    return Variant(id="v1", headline=headline, body=body, cta=cta, channel=Channel.EMAIL)


def test_substantiated_superlative_passes() -> None:
    svc = ClaimValidationService()
    result = svc.check(
        _variant("The best rate", "Based on the published comparison; t&cs apply."),
        claim_rules_for(Market.SG, Vertical.BANKING),
    )
    assert result.status is CheckStatus.PASS


def test_unsubstantiated_superlative_fails() -> None:
    svc = ClaimValidationService()
    result = svc.check(
        _variant("The cheapest deal anywhere", "Sign up today."),
        claim_rules_for(Market.AU, Vertical.ONLINE_RETAIL),
    )
    assert result.failed
    assert any(f.rule_id == "claim-superlative" for f in result.findings)
    assert all(f.citations for f in result.findings)


def test_unqualified_guarantee_critical_in_banking() -> None:
    svc = ClaimValidationService()
    result = svc.check(
        _variant("Risk-free returns", "Open now."),
        claim_rules_for(Market.JP, Vertical.BANKING),
    )
    assert result.failed
    assert any(f.rule_id == "claim-bank-guarantee" for f in result.findings)


def test_qualified_free_passes() -> None:
    svc = ClaimValidationService()
    result = svc.check(
        _variant("Free delivery", "No fees on your first order. T&cs apply."),
        claim_rules_for(Market.SG, Vertical.ONLINE_RETAIL),
    )
    # 'free' is qualified by 't&cs apply'; no claim finding for the free rule.
    assert all(f.rule_id != "claim-unqualified-free" for f in result.findings)


def test_one_finding_per_rule() -> None:
    svc = ClaimValidationService()
    result = svc.check(
        _variant("best best best", "cheapest lowest"),
        claim_rules_for(Market.SG, Vertical.BANKING),
    )
    superlatives = [f for f in result.findings if f.rule_id == "claim-superlative"]
    assert len(superlatives) == 1


def test_percent_off_trigger_fires_in_natural_copy() -> None:
    """Regression: '% off' followed-by-digit (e.g. '50% off') must trigger the discount rule.

    A whole-word guard that puts a ``(?<!\\w)`` lookbehind before the leading ``%`` is
    defeated by the preceding digit, so an unsubstantiated '50% off' silently passes.
    """
    svc = ClaimValidationService()
    result = svc.check(
        _variant("Spring sale", "Get 50% off everything this week."),
        claim_rules_for(Market.AU, Vertical.ONLINE_RETAIL),
    )
    assert any(f.rule_id == "claim-retail-discount" for f in result.findings)
    # With a reference price it is substantiated and the discount rule must NOT fire.
    ok = svc.check(
        _variant("Spring sale", "Get 50% off the rrp this week. T&cs apply."),
        claim_rules_for(Market.AU, Vertical.ONLINE_RETAIL),
    )
    assert all(f.rule_id != "claim-retail-discount" for f in ok.findings)


def test_percent_interest_and_return_triggers_fire_in_natural_copy() -> None:
    """Regression: '% interest' / '% return' adjacent to a digit must trigger the rate rule."""
    svc = ClaimValidationService()
    for copy in ("Earn 5% interest on savings.", "Up to 8% return on deposits."):
        result = svc.check(
            _variant("Grow your money", copy),
            claim_rules_for(Market.SG, Vertical.BANKING),
        )
        assert any(f.rule_id == "claim-bank-performance" for f in result.findings), copy


def test_contains_word_boundary_only_on_word_edges() -> None:
    """The matcher anchors boundaries only on word-character edges of the phrase."""
    # Leading non-word: matches despite an adjacent digit.
    assert _contains("save 50% off now", "% off") is not None
    # Word-bounded phrase still respects boundaries (no substring false positives).
    assert _contains("earnings grow", "earn") is None
    assert _contains("learn more", "earn") is None
    assert _contains("you earn interest", "earn") is not None

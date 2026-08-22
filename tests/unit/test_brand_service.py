"""Unit tests for the deterministic BrandGuidelineService (pure, replayable)."""

from __future__ import annotations

from creative_studio.domain.brand_service import BrandGuidelineService
from creative_studio.domain.models import (
    BrandRule,
    BrandRuleKind,
    Channel,
    CheckStatus,
    Market,
    RuleSeverity,
    Variant,
    Vertical,
)
from creative_studio.domain.rules import brand_rules_for


def _variant(headline: str, body: str = "", cta: str = "") -> Variant:
    return Variant(id="v1", headline=headline, body=body, cta=cta, channel=Channel.EMAIL)


def test_clean_copy_passes() -> None:
    svc = BrandGuidelineService()
    result = svc.check(
        _variant("Grow your savings", "Earn a steady rate; t&cs apply.", "See details"),
        brand_rules_for(Market.SG, Vertical.BANKING),
    )
    assert result.status is CheckStatus.PASS
    assert not result.findings


def test_forbidden_term_high_severity_fails() -> None:
    svc = BrandGuidelineService()
    result = svc.check(
        _variant("Get rich quick with us", "Open today."),
        brand_rules_for(Market.SG, Vertical.BANKING),
    )
    assert result.failed
    assert any(f.rule_id == "brand-bank-trust" for f in result.findings)
    assert all(f.citations for f in result.findings)


def test_forbidden_term_with_nonword_edge_matches_natural_copy() -> None:
    """Regression: a FORBIDDEN_TERM whose pattern starts with a non-word char (e.g. '% back')
    must still match adjacent to a digit ('5% back'); the boundary guard only applies to
    word-character edges of the pattern."""
    svc = BrandGuidelineService()
    rule = BrandRule(
        id="brand-no-percent-back",
        kind=BrandRuleKind.FORBIDDEN_TERM,
        pattern="% back",
        message="Avoid cashback phrasing in brand copy.",
        severity=RuleSeverity.HIGH,
    )
    result = svc.check(_variant("Get 5% back today", "Open now."), (rule,))
    assert result.failed
    assert any(f.rule_id == "brand-no-percent-back" for f in result.findings)


def test_required_term_missing_flags() -> None:
    svc = BrandGuidelineService()
    rule = BrandRule(
        id="brand-need-disclaimer",
        kind=BrandRuleKind.REQUIRED_TERM,
        pattern="t&cs apply",
        message="Must include the t&cs notice.",
        severity=RuleSeverity.HIGH,
    )
    result = svc.check(_variant("A great deal", "Open today."), (rule,))
    assert result.failed
    assert result.findings[0].rule_id == "brand-need-disclaimer"


def test_tone_all_caps_and_exclamations_warn() -> None:
    svc = BrandGuidelineService()
    result = svc.check(_variant("BUY NOW!!!", "GREAT OFFER"), ())
    assert result.status is CheckStatus.WARN
    rule_ids = {f.rule_id for f in result.findings}
    assert "tone:all_caps" in rule_ids
    assert "tone:exclamation" in rule_ids


def test_determinism_same_input_same_output() -> None:
    svc = BrandGuidelineService()
    v = _variant("Get rich quick", "amazing offer")
    rules = brand_rules_for(Market.SG, Vertical.BANKING)
    a = svc.check(v, rules)
    b = svc.check(v, rules)
    assert a == b

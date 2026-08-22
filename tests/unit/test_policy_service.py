"""Unit tests for the deterministic PolicyValidationService (per-market + per-vertical)."""

from __future__ import annotations

from creative_studio.domain.models import Channel, CheckStatus, Market, Variant, Vertical
from creative_studio.domain.policy_service import PolicyValidationService
from creative_studio.domain.rules import policy_rules_for


def _variant(headline: str, body: str = "", cta: str = "") -> Variant:
    return Variant(id="v1", headline=headline, body=body, cta=cta, channel=Channel.EMAIL)


def test_banking_requires_tcs_disclosure() -> None:
    svc = PolicyValidationService()
    result = svc.check(
        _variant("Open a savings account", "Earn a great rate."),
        Market.SG,
        Vertical.BANKING,
        policy_rules_for(Market.SG, Vertical.BANKING),
    )
    assert result.failed
    assert any("financial promotion" in f.message.lower() for f in result.findings)


def test_banking_with_tcs_passes() -> None:
    svc = PolicyValidationService()
    result = svc.check(
        _variant("Open a savings account", "Earn a steady rate; t&cs apply."),
        Market.SG,
        Vertical.BANKING,
        policy_rules_for(Market.SG, Vertical.BANKING),
    )
    assert result.status is CheckStatus.PASS


def test_misleading_forbidden_phrase_critical() -> None:
    svc = PolicyValidationService()
    result = svc.check(
        _variant("100% guaranteed returns", "t&cs apply"),
        Market.AU,
        Vertical.BANKING,
        policy_rules_for(Market.AU, Vertical.BANKING),
    )
    assert result.failed
    assert any(f.severity.value == "critical" for f in result.findings)
    assert all(f.citations for f in result.findings)


def test_rules_are_market_scoped() -> None:
    """A JP rule set never fires on an AU variant: rules are keyed by (market, vertical)."""
    svc = PolicyValidationService()
    jp_rules = policy_rules_for(Market.JP, Vertical.BANKING)
    # Apply JP rules but declare the variant as AU: the engine skips non-AU rules.
    result = svc.check(
        _variant("100% guaranteed returns"),
        Market.AU,
        Vertical.BANKING,
        jp_rules,
    )
    assert result.status is CheckStatus.PASS  # JP rules do not apply to an AU check


def test_retail_passes_clean() -> None:
    svc = PolicyValidationService()
    result = svc.check(
        _variant("Spring sale", "Save on the rrp; t&cs apply."),
        Market.SG,
        Vertical.ONLINE_RETAIL,
        policy_rules_for(Market.SG, Vertical.ONLINE_RETAIL),
    )
    assert result.status is CheckStatus.PASS

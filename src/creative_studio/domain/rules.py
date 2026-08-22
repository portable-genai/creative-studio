"""Built-in, OBVIOUSLY-FICTIONAL rule sets for D3 (config + seed defaults).

The deterministic engines (brand, claim, policy, asset) need rules to check against.
These are the bundled defaults, keyed by (market, vertical) where it matters, so D3 is
generic and APAC out of the box: BOTH verticals (banking AND online retail) across ALL
THREE markets (JP, AU, SG). They are seed-style data, not hard-coded engine branches: the
engines take a rule set as an argument, and a deployment can override these via the corpus
/ config without touching engine code.

Rules reference fictional, illustrative policy names (JP Act on Specified Commercial
Transactions and Premiums & Representations Act; AU Australian Consumer Law / ASIC; SG PDPA
and advertising standards; banking adds local financial-promotion rules as ONE set among
others). Nothing here is legal advice; the names anchor provenance for the demo.
"""

from __future__ import annotations

from .models import (
    AssetSpec,
    BrandRule,
    BrandRuleKind,
    Channel,
    Citation,
    ClaimRule,
    ClaimRuleKind,
    Market,
    PolicyRule,
    RuleSeverity,
    SourceType,
    Vertical,
)

_Key = tuple[Market, Vertical]


def _policy_cit(sid: str, title: str) -> Citation:
    return Citation(
        source_id=sid,
        source_type=SourceType.AD_POLICY,
        title=title,
        url=f"https://policy.example.test/{sid}",
        snippet=f"{title} (FICTIONAL illustrative clause).",
    )


def _claim_cit(sid: str, title: str) -> Citation:
    return Citation(
        source_id=sid,
        source_type=SourceType.CLAIM_RULE,
        title=title,
        url=f"https://policy.example.test/{sid}",
        snippet=f"{title} (FICTIONAL illustrative clause).",
    )


# --------------------------------------------------------------------------- #
# Brand guidelines (per vertical; some shared)
# --------------------------------------------------------------------------- #
_SHARED_BRAND: tuple[BrandRule, ...] = (
    BrandRule(
        id="brand-no-shouting-free",
        kind=BrandRuleKind.FORBIDDEN_TERM,
        pattern="act now",
        message="Brand voice avoids high-pressure phrases like 'act now'.",
        severity=RuleSeverity.LOW,
        suggestion="Use a calm CTA such as 'See the details'.",
    ),
    BrandRule(
        id="brand-no-amazing",
        kind=BrandRuleKind.FORBIDDEN_TERM,
        pattern="amazing",
        message="Brand voice avoids hype words like 'amazing'.",
        severity=RuleSeverity.LOW,
        suggestion="Describe the concrete benefit instead.",
    ),
)

BRAND_RULES: dict[Vertical, tuple[BrandRule, ...]] = {
    Vertical.BANKING: _SHARED_BRAND
    + (
        BrandRule(
            id="brand-bank-trust",
            kind=BrandRuleKind.FORBIDDEN_TERM,
            pattern="get rich",
            message="Banking brand voice never promises wealth ('get rich').",
            severity=RuleSeverity.HIGH,
            suggestion="Focus on steady, transparent value.",
        ),
        BrandRule(
            id="brand-bank-readinglevel",
            kind=BrandRuleKind.READING_LEVEL,
            pattern="",
            message="Banking copy must stay plain-language (keep words short).",
            severity=RuleSeverity.MEDIUM,
        ),
    ),
    Vertical.ONLINE_RETAIL: _SHARED_BRAND
    + (
        BrandRule(
            id="brand-retail-no-fakescarcity",
            kind=BrandRuleKind.FORBIDDEN_TERM,
            pattern="last chance ever",
            message="Retail brand voice avoids false-scarcity ('last chance ever').",
            severity=RuleSeverity.MEDIUM,
            suggestion="State the real end date of the offer.",
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Advertising-claim rules (per vertical; markets share the catalogue)
# --------------------------------------------------------------------------- #
_SHARED_CLAIM: tuple[ClaimRule, ...] = (
    ClaimRule(
        id="claim-superlative",
        kind=ClaimRuleKind.SUPERLATIVE,
        triggers=("best", "cheapest", "number one", "no.1", "lowest"),
        message="Superlative claim needs substantiation or a qualifier.",
        requires_tokens=("based on", "as at", "t&cs apply", "*"),
        severity=RuleSeverity.HIGH,
        citation=_claim_cit("claim-superlative", "Superlatives must be substantiated"),
    ),
    ClaimRule(
        id="claim-unqualified-free",
        kind=ClaimRuleKind.UNQUALIFIED_FREE,
        triggers=("free",),
        message="'Free' must be qualified with the conditions that apply.",
        requires_tokens=("t&cs apply", "conditions apply", "*", "no fees"),
        severity=RuleSeverity.MEDIUM,
        citation=_claim_cit("claim-free", "Unqualified 'free' is misleading"),
    ),
)

CLAIM_RULES: dict[Vertical, tuple[ClaimRule, ...]] = {
    Vertical.BANKING: _SHARED_CLAIM
    + (
        ClaimRule(
            id="claim-bank-guarantee",
            kind=ClaimRuleKind.GUARANTEE,
            triggers=("guaranteed", "risk-free", "risk free", "no risk"),
            message="Financial 'guaranteed / risk-free' claims need a clear qualifier.",
            requires_tokens=("t&cs apply", "capital at risk", "*"),
            severity=RuleSeverity.CRITICAL,
            citation=_claim_cit("claim-bank-guarantee", "No unqualified guarantees in finance"),
        ),
        ClaimRule(
            id="claim-bank-performance",
            kind=ClaimRuleKind.PERFORMANCE,
            triggers=("p.a.", "per annum", "% interest", "% return", "earn"),
            message="Rate / return claims need a basis and a disclaimer.",
            requires_tokens=("t&cs apply", "as at", "variable", "*"),
            severity=RuleSeverity.HIGH,
            citation=_claim_cit("claim-bank-performance", "Rate claims need a basis"),
        ),
    ),
    Vertical.ONLINE_RETAIL: _SHARED_CLAIM
    + (
        ClaimRule(
            id="claim-retail-comparative",
            kind=ClaimRuleKind.COMPARATIVE,
            triggers=("cheaper than", "beats", "better than"),
            message="Comparative claim needs a stated basis of comparison.",
            requires_tokens=("based on", "compared with", "*"),
            severity=RuleSeverity.HIGH,
            citation=_claim_cit("claim-retail-comparative", "Comparatives need a basis"),
        ),
        ClaimRule(
            id="claim-retail-discount",
            kind=ClaimRuleKind.PERFORMANCE,
            triggers=("% off", "save", "discount"),
            message="Discount claims need the reference price / conditions.",
            requires_tokens=("was", "rrp", "t&cs apply", "*"),
            severity=RuleSeverity.MEDIUM,
            citation=_claim_cit("claim-retail-discount", "Discounts need a reference price"),
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Per-market + per-vertical advertising / consumer-protection policy rules
# --------------------------------------------------------------------------- #
def _policy_rules() -> dict[_Key, tuple[PolicyRule, ...]]:
    out: dict[_Key, tuple[PolicyRule, ...]] = {}
    # Per-market consumer-protection baselines (apply to every vertical in the market).
    market_names = {
        Market.JP: "JP Act on Specified Commercial Transactions / Premiums & Representations Act",
        Market.AU: "AU Australian Consumer Law (ACCC)",
        Market.SG: "SG advertising standards and PDPA",
    }
    for market, name in market_names.items():
        for vertical in (Vertical.BANKING, Vertical.ONLINE_RETAIL):
            base: list[PolicyRule] = [
                PolicyRule(
                    id=f"policy-{market.value.lower()}-misleading",
                    name=name,
                    market=market,
                    vertical=None,
                    forbidden_patterns=("100% guaranteed", "unlimited free money"),
                    message="Misleading or deceptive representations are prohibited.",
                    severity=RuleSeverity.CRITICAL,
                    citation=_policy_cit(f"policy-{market.value.lower()}-misleading", name),
                ),
            ]
            if vertical is Vertical.BANKING:
                base.append(
                    PolicyRule(
                        id=f"policy-{market.value.lower()}-bank-promo",
                        name=f"{name} — financial promotion",
                        market=market,
                        vertical=Vertical.BANKING,
                        required_patterns=("t&cs apply",),
                        message="A financial promotion must carry the terms-and-conditions notice.",
                        severity=RuleSeverity.HIGH,
                        citation=_policy_cit(
                            f"policy-{market.value.lower()}-bank-promo",
                            f"{name} — financial promotion",
                        ),
                    )
                )
            if vertical is Vertical.ONLINE_RETAIL:
                base.append(
                    PolicyRule(
                        id=f"policy-{market.value.lower()}-retail-pricing",
                        name=f"{name} — pricing display",
                        market=market,
                        vertical=Vertical.ONLINE_RETAIL,
                        forbidden_patterns=("was $0",),
                        message="Reference ('was') prices must be genuine.",
                        severity=RuleSeverity.HIGH,
                        citation=_policy_cit(
                            f"policy-{market.value.lower()}-retail-pricing",
                            f"{name} — pricing display",
                        ),
                    )
                )
            out[(market, vertical)] = tuple(base)
    return out


POLICY_RULES: dict[_Key, tuple[PolicyRule, ...]] = _policy_rules()


# --------------------------------------------------------------------------- #
# Per-channel asset specs (config + seed)
# --------------------------------------------------------------------------- #
ASSET_SPECS: dict[Channel, AssetSpec] = {
    Channel.EMAIL: AssetSpec(
        channel=Channel.EMAIL,
        max_headline_chars=80,
        max_body_chars=600,
        max_cta_chars=40,
        requires_headline=True,
        requires_cta=True,
    ),
    Channel.SMS: AssetSpec(
        channel=Channel.SMS,
        max_headline_chars=0,
        max_body_chars=160,
        requires_headline=False,
        requires_cta=False,
    ),
    Channel.PUSH: AssetSpec(
        channel=Channel.PUSH,
        max_headline_chars=50,
        max_body_chars=120,
        requires_headline=True,
        requires_cta=False,
    ),
    Channel.DISPLAY: AssetSpec(
        channel=Channel.DISPLAY,
        max_headline_chars=40,
        max_body_chars=90,
        max_cta_chars=20,
        requires_headline=True,
        requires_cta=True,
        requires_image=True,
        image_width=1200,
        image_height=628,
        allowed_aspect_ratios=("16:9", "1.91:1"),
    ),
    Channel.SEARCH: AssetSpec(
        channel=Channel.SEARCH,
        max_headline_chars=30,
        max_body_chars=90,
        requires_headline=True,
        requires_cta=False,
    ),
    Channel.SOCIAL: AssetSpec(
        channel=Channel.SOCIAL,
        max_headline_chars=60,
        max_body_chars=280,
        max_cta_chars=30,
        requires_headline=True,
        requires_cta=False,
        requires_image=True,
        image_width=1080,
        image_height=1080,
        allowed_aspect_ratios=("1:1", "4:5"),
    ),
    Channel.WEB: AssetSpec(
        channel=Channel.WEB,
        max_headline_chars=120,
        max_body_chars=2000,
        requires_headline=True,
        requires_cta=True,
    ),
}


def brand_rules_for(market: Market, vertical: Vertical) -> tuple[BrandRule, ...]:
    """Brand rules active for a (market, vertical), filtered by their own scoping."""
    rules = BRAND_RULES.get(vertical, ())
    return tuple(
        r
        for r in rules
        if (r.market is None or r.market is market)
        and (r.vertical is None or r.vertical is vertical)
    )


def claim_rules_for(market: Market, vertical: Vertical) -> tuple[ClaimRule, ...]:
    """Claim rules active for a (market, vertical)."""
    rules = CLAIM_RULES.get(vertical, ())
    return tuple(
        r
        for r in rules
        if (r.market is None or r.market is market)
        and (r.vertical is None or r.vertical is vertical)
    )


def policy_rules_for(market: Market, vertical: Vertical) -> tuple[PolicyRule, ...]:
    """Policy rules active for a (market, vertical)."""
    return POLICY_RULES.get((market, vertical), ())


def asset_spec_for(channel: Channel) -> AssetSpec:
    """The asset spec for a channel (defaults to an unconstrained email-like spec)."""
    return ASSET_SPECS.get(channel, AssetSpec(channel=channel))

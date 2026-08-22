"""PolicyValidationService — deterministic per-market + per-vertical policy validation.

The third deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Each market (JP / AU / SG) and vertical has advertising and
consumer-protection rules (generic marketing rules, NOT bank-only: banking financial-
promotion rules are simply one configured set). Given a variant's copy and the
:class:`PolicyRule` set selected for its (market, vertical), this engine flags forbidden
patterns that appear and required patterns (mandated disclosures) that are missing.

This is the consequential "does this meet the market's advertising law" check an auditor
must re-run, so it is code, not an LLM call. Every :class:`Finding` cites the policy clause
it enforces. Region/locale/vertical are config + seed: the rule set comes from the seed,
keyed by (market, vertical); no market is hard-coded into a branch here.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    CheckStatus,
    Citation,
    Finding,
    Market,
    PolicyCheck,
    PolicyRule,
    RuleSeverity,
    SourceType,
    Variant,
    Vertical,
)

_FAIL_SEVERITIES = frozenset({RuleSeverity.HIGH, RuleSeverity.CRITICAL})


def _contains(text: str, phrase: str) -> re.Match[str] | None:
    """Case-insensitive whole-word/phrase search.

    The word-boundary guard is applied only on phrase edges that are word characters, so a
    pattern beginning or ending with a non-word character (e.g. ``"was $0"``, ``"100%
    guaranteed"``) still matches in natural copy. See ``claim_service._contains``.
    """
    stripped = phrase.strip()
    if not stripped:
        return None
    escaped = re.escape(stripped)
    prefix = r"(?<!\w)" if stripped[0].isalnum() or stripped[0] == "_" else ""
    suffix = r"(?!\w)" if stripped[-1].isalnum() or stripped[-1] == "_" else ""
    return re.search(rf"{prefix}{escaped}{suffix}", text, re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PolicyValidationService:
    """Pure, deterministic per-market + per-vertical advertising-policy validation."""

    def check(
        self,
        variant: Variant,
        market: Market,
        vertical: Vertical,
        rules: tuple[PolicyRule, ...] | list[PolicyRule],
    ) -> PolicyCheck:
        """Check a variant against the policy rules for its market and vertical."""
        text = self._copy_text(variant)
        findings: list[Finding] = []
        for rule in rules:
            if not self._applies(rule, market, vertical):
                continue
            findings.extend(self._apply(rule, text))
        return PolicyCheck(
            variant_id=variant.id,
            market=market,
            vertical=vertical,
            status=self._status(findings),
            findings=tuple(findings),
        )

    # ------------------------------------------------------------------ #
    # Rule application
    # ------------------------------------------------------------------ #
    @staticmethod
    def _applies(rule: PolicyRule, market: Market, vertical: Vertical) -> bool:
        if rule.market is not market:
            return False
        return rule.vertical is None or rule.vertical is vertical

    def _apply(self, rule: PolicyRule, text: str) -> list[Finding]:
        out: list[Finding] = []
        for forbidden in rule.forbidden_patterns:
            match = _contains(text, forbidden)
            if match is not None:
                out.append(
                    self._finding(
                        rule,
                        message=f"{rule.name}: forbidden phrase '{forbidden}'. {rule.message}",
                        span=match.group(0),
                    )
                )
        for required in rule.required_patterns:
            if _contains(text, required) is None:
                out.append(
                    self._finding(
                        rule,
                        message=(
                            f"{rule.name}: required disclosure '{required}' is missing. "
                            f"{rule.message}"
                        ),
                        span="",
                        suggestion=f"Include '{required}'.",
                    )
                )
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy_text(variant: Variant) -> str:
        return " ".join(p for p in (variant.headline, variant.body, variant.cta) if p)

    @staticmethod
    def _finding(rule: PolicyRule, message: str, span: str, suggestion: str = "") -> Finding:
        citation = rule.citation or Citation(
            source_id=rule.id,
            source_type=SourceType.AD_POLICY,
            title=rule.name,
            snippet=rule.message,
        )
        return Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=message,
            span=span,
            suggestion=suggestion,
            citations=(citation,),
        )

    @staticmethod
    def _status(findings: list[Finding]) -> CheckStatus:
        if any(f.severity in _FAIL_SEVERITIES for f in findings):
            return CheckStatus.FAIL
        if findings:
            return CheckStatus.WARN
        return CheckStatus.PASS

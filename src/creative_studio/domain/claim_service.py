"""ClaimValidationService — deterministic advertising-claim validation.

The second deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Advertising claims (superlatives like "best", guarantees like
"risk-free", comparatives, performance promises, unqualified "free") must be substantiated
or qualified, and the rules differ per market and per vertical. Given a variant's copy and
the active :class:`ClaimRule` set, this engine flags every triggered claim that lacks at
least one of its required substantiation tokens (e.g. "T&Cs apply", a disclaimer marker).

This is the consequential "can we legally say this" check an auditor must re-run, so it is
code, not an LLM call. Every :class:`Finding` cites the claim rule (and, through it, the
advertising-policy clause) it enforces.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    CheckStatus,
    Citation,
    ClaimCheck,
    ClaimRule,
    Finding,
    RuleSeverity,
    SourceType,
    Variant,
)

_FAIL_SEVERITIES = frozenset({RuleSeverity.HIGH, RuleSeverity.CRITICAL})


def _contains(text: str, phrase: str) -> re.Match[str] | None:
    """Case-insensitive whole-word/phrase search.

    Word boundaries are applied only on the edges of ``phrase`` that are themselves word
    characters. A phrase that begins or ends with a non-word character (e.g. ``"% off"``,
    ``"p.a."``) must still match in natural copy like ``"50% off"`` — a ``(?<!\\w)``
    lookbehind in front of ``%`` would wrongly reject the preceding digit, so it is omitted
    when the leading (or trailing) character is not a word character.
    """
    stripped = phrase.strip()
    if not stripped:
        return None
    escaped = re.escape(stripped)
    prefix = r"(?<!\w)" if stripped[0].isalnum() or stripped[0] == "_" else ""
    suffix = r"(?!\w)" if stripped[-1].isalnum() or stripped[-1] == "_" else ""
    return re.search(rf"{prefix}{escaped}{suffix}", text, re.IGNORECASE)


def _token_present(text: str, token: str) -> bool:
    """A substantiation token is present (substring, case-insensitive, e.g. '*' or 'T&Cs')."""
    return token.strip().lower() in text.lower()


@dataclass(frozen=True, slots=True)
class ClaimValidationService:
    """Pure, deterministic advertising-claim validation."""

    def check(
        self,
        variant: Variant,
        rules: tuple[ClaimRule, ...] | list[ClaimRule],
    ) -> ClaimCheck:
        """Check a variant's claims against the active rules; return a cited result."""
        text = self._copy_text(variant)
        findings: list[Finding] = []
        for rule in rules:
            findings.extend(self._apply(rule, text))
        return ClaimCheck(
            variant_id=variant.id,
            status=self._status(findings),
            findings=tuple(findings),
        )

    # ------------------------------------------------------------------ #
    # Rule application
    # ------------------------------------------------------------------ #
    def _apply(self, rule: ClaimRule, text: str) -> list[Finding]:
        out: list[Finding] = []
        for trigger in rule.triggers:
            match = _contains(text, trigger)
            if match is None:
                continue
            # Triggered. Substantiated only if at least one required token is present
            # (a rule with no required tokens is always a flag when triggered).
            substantiated = bool(rule.requires_tokens) and any(
                _token_present(text, tok) for tok in rule.requires_tokens
            )
            if substantiated:
                continue
            out.append(self._finding(rule, span=match.group(0)))
            break  # one finding per rule is enough; do not double-flag the same rule
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy_text(variant: Variant) -> str:
        return " ".join(p for p in (variant.headline, variant.body, variant.cta) if p)

    @staticmethod
    def _finding(rule: ClaimRule, span: str) -> Finding:
        citation = rule.citation or Citation(
            source_id=rule.id,
            source_type=SourceType.CLAIM_RULE,
            title=rule.message,
            snippet=", ".join(rule.triggers),
        )
        need = f" Add one of: {', '.join(rule.requires_tokens)}." if rule.requires_tokens else ""
        return Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=rule.message + need,
            span=span,
            suggestion=need.strip(),
            citations=(citation,),
        )

    @staticmethod
    def _status(findings: list[Finding]) -> CheckStatus:
        if any(f.severity in _FAIL_SEVERITIES for f in findings):
            return CheckStatus.FAIL
        if findings:
            return CheckStatus.WARN
        return CheckStatus.PASS

"""BrandGuidelineService — deterministic brand-guideline validation.

The first deterministic engine in the D3 pipeline (see the ``deterministic-domain-service``
skill): pure, stdlib-only, replayable. Given a variant's copy and the brand rules for its
(market, vertical), it flags forbidden terms, missing required terms, tone violations (e.g.
all-caps shouting, excessive exclamation) and reading-level breaches. The consequential
"is this on-brand" judgement an auditor must be able to re-run, so it is code, not an LLM
call. The LLM only drafts the copy; this engine decides whether it is on-brand.

Determinism: same inputs (copy + rules) -> same output. No LLM, no clock, no network, no
randomness. Every :class:`Finding` carries the :class:`Citation` of the brand rule it
enforces, so the brand check is auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    BrandCheck,
    BrandRule,
    BrandRuleKind,
    CheckStatus,
    Citation,
    Finding,
    RuleSeverity,
    SourceType,
    Variant,
)

_WORD_RE = re.compile(r"[A-Za-z]+")
_FAIL_SEVERITIES = frozenset({RuleSeverity.HIGH, RuleSeverity.CRITICAL})


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """A case-insensitive whole-word/phrase matcher for ``phrase``.

    \\b is unreliable around non-word phrase edges, so word boundaries are anchored with
    lookarounds — but only on edges that are themselves word characters. A pattern that
    starts or ends with a non-word character (e.g. ``"50% off"``) would otherwise never
    match because the lookbehind/lookahead rejects the adjacent digit/letter in real copy.
    """
    stripped = phrase.strip()
    escaped = re.escape(stripped)
    prefix = r"(?<!\w)" if stripped and (stripped[0].isalnum() or stripped[0] == "_") else ""
    suffix = r"(?!\w)" if stripped and (stripped[-1].isalnum() or stripped[-1] == "_") else ""
    return re.compile(rf"{prefix}{escaped}{suffix}", re.IGNORECASE)


def _rule_citation(rule: BrandRule) -> Citation:
    return Citation(
        source_id=rule.id,
        source_type=SourceType.BRAND_GUIDELINE,
        title=rule.message,
        snippet=rule.pattern,
    )


@dataclass(frozen=True, slots=True)
class BrandGuidelineService:
    """Pure, deterministic brand-guideline validation.

    Tunables (not magic numbers): ``max_exclamations`` and ``caps_word_threshold`` bound
    the tone heuristic; ``max_avg_word_length`` bounds the reading-level heuristic.
    """

    max_exclamations: int = 1
    caps_word_threshold: int = 2  # this many ALL-CAPS words (len>=3) is shouting
    max_avg_word_length: float = 7.5  # average word length above this reads as dense

    def check(
        self,
        variant: Variant,
        rules: tuple[BrandRule, ...] | list[BrandRule],
    ) -> BrandCheck:
        """Check one variant against the brand rules; return a cited result."""
        text = self._copy_text(variant)
        findings: list[Finding] = []
        for rule in rules:
            finding = self._apply(rule, text)
            if finding is not None:
                findings.append(finding)
        findings.extend(self._tone_findings(text))
        return BrandCheck(
            variant_id=variant.id,
            status=self._status(findings),
            findings=tuple(findings),
        )

    # ------------------------------------------------------------------ #
    # Rule application
    # ------------------------------------------------------------------ #
    def _apply(self, rule: BrandRule, text: str) -> Finding | None:
        if rule.kind is BrandRuleKind.FORBIDDEN_TERM:
            match = _phrase_pattern(rule.pattern).search(text)
            if match:
                return self._finding(rule, span=match.group(0))
            return None
        if rule.kind is BrandRuleKind.REQUIRED_TERM:
            if not _phrase_pattern(rule.pattern).search(text):
                return self._finding(rule, span="")
            return None
        if rule.kind is BrandRuleKind.READING_LEVEL:
            if self._too_dense(text):
                return self._finding(rule, span="")
            return None
        # TONE rules without a pattern are handled by the tone heuristic below.
        return None

    def _tone_findings(self, text: str) -> list[Finding]:
        out: list[Finding] = []
        exclamations = text.count("!")
        if exclamations > self.max_exclamations:
            out.append(
                Finding(
                    rule_id="tone:exclamation",
                    severity=RuleSeverity.LOW,
                    message=(
                        f"Copy uses {exclamations} exclamation marks (max "
                        f"{self.max_exclamations}); tone reads as over-excited."
                    ),
                    citations=(
                        Citation(
                            source_id="tone:exclamation",
                            source_type=SourceType.BRAND_GUIDELINE,
                            title="Tone: avoid over-excited punctuation",
                        ),
                    ),
                )
            )
        caps_words = [w for w in _WORD_RE.findall(text) if len(w) >= 3 and w.isupper()]
        if len(caps_words) >= self.caps_word_threshold:
            out.append(
                Finding(
                    rule_id="tone:all_caps",
                    severity=RuleSeverity.LOW,
                    message=(
                        f"Copy shouts in all-caps ({', '.join(caps_words[:4])}); use sentence case."
                    ),
                    span=" ".join(caps_words[:4]),
                    citations=(
                        Citation(
                            source_id="tone:all_caps",
                            source_type=SourceType.BRAND_GUIDELINE,
                            title="Tone: avoid all-caps shouting",
                        ),
                    ),
                )
            )
        return out

    def _too_dense(self, text: str) -> bool:
        words = _WORD_RE.findall(text)
        if not words:
            return False
        avg = sum(len(w) for w in words) / len(words)
        return avg > self.max_avg_word_length

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy_text(variant: Variant) -> str:
        return " ".join(p for p in (variant.headline, variant.body, variant.cta) if p)

    @staticmethod
    def _finding(rule: BrandRule, span: str) -> Finding:
        return Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=rule.message,
            span=span,
            suggestion=rule.suggestion,
            citations=(_rule_citation(rule),),
        )

    @staticmethod
    def _status(findings: list[Finding]) -> CheckStatus:
        if any(f.severity in _FAIL_SEVERITIES for f in findings):
            return CheckStatus.FAIL
        if findings:
            return CheckStatus.WARN
        return CheckStatus.PASS

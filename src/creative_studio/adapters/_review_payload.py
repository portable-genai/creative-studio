"""Shared conversion from an escalated creative result to an ``review-kit`` Review payload.

Lives in the adapter layer (not the pure domain) because it depends on the kit. creative-studio
handles a brief and brand context and has no customer-PII surface (R1: PII redaction n/a), but the
review console is a shared sink, so the descriptor, summary and citation snippets are still scrubbed
defensively for stray contact identifiers before they leave the process (P-04 boundary, defense in
depth); human-review-console redacts again before its own audit write. The repo carries no redaction
adapter or ``pii-kit`` dependency, so the masking here is a small, self-contained local pattern set
(email / phone), not a shared pack. The maker (the agent that originated the creative) and the
tenant are asserted here and trusted by human-review-console because this is an authenticated S2S
caller (per-hop OBO is the deferred next layer).
"""

from __future__ import annotations

import re

from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.models import CreativeStudioResult, Finding, RuleSeverity

# Cap the citations carried on the wire: enough to let a reviewer trace the creative without
# copying the entire evidence set into the review console.
_MAX_CITATIONS = 8

# Defensive local redaction: creative-studio has no customer-PII surface and no redaction adapter,
# so this
# is a minimal contact-identifier mask (email + international/local phone), applied so no stray
# identifier that slipped into a brief or brand snippet reaches the shared console over the wire.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")

# Ordered weakest -> strongest so the worst finding severity drives the review severity.
_SEVERITY_ORDER: tuple[RuleSeverity, ...] = (
    RuleSeverity.INFO,
    RuleSeverity.LOW,
    RuleSeverity.MEDIUM,
    RuleSeverity.HIGH,
    RuleSeverity.CRITICAL,
)


def _redact(text: str) -> str:
    """Mask stray email/phone identifiers and collapse whitespace before the wire."""
    redacted = _EMAIL_RE.sub("[email]", text)
    redacted = _PHONE_RE.sub("[phone]", redacted)
    return re.sub(r"\s+", " ", redacted).strip()


def _overall_severity(result: CreativeStudioResult) -> RuleSeverity:
    """The most severe finding across the whole result, or LOW when the creative is clean."""
    present = [f.severity for f in result.all_findings if f.severity in _SEVERITY_ORDER]
    if not present:
        return RuleSeverity.LOW
    return max(present, key=_SEVERITY_ORDER.index)


def _escalated(result: CreativeStudioResult) -> bool:
    """A failed variant or a HIGH/CRITICAL finding warrants dual control (maker-checker gate)."""
    if result.failed_reviews:
        return True
    return _overall_severity(result) in (RuleSeverity.HIGH, RuleSeverity.CRITICAL)


def _kit_citations(result: CreativeStudioResult) -> tuple[KitCitation, ...]:
    seen: set[str] = set()
    out: list[KitCitation] = []
    for c in result.citations:
        if c.source_id in seen:
            continue
        seen.add(c.source_id)
        out.append(KitCitation(source_id=c.source_id, title=c.title, snippet=_redact(c.snippet)))
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def _findings_count(result: CreativeStudioResult) -> int:
    findings: tuple[Finding, ...] = result.all_findings
    return len(findings)


def result_to_review(result: CreativeStudioResult, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to human-review-console when a
    creative result escalates.
    """
    brief = result.brief
    descriptor = (
        f"Creative for {brief.vertical.value}/{brief.market.value} via {brief.channel.value}: "
        f"topic={brief.topic}; product={brief.product or 'n/a'}"
    )
    summary = (
        f"variants={len(result.reviews)}; approved={len(result.approved_reviews)}; "
        f"failed={len(result.failed_reviews)}; findings={_findings_count(result)}"
    )
    severity = _overall_severity(result)
    dual = _escalated(result) or severity in (RuleSeverity.HIGH, RuleSeverity.CRITICAL)
    return Review(
        action=f"creative_asset:{brief.channel.value}",
        subject=_redact(descriptor),
        maker=maker,
        tenant=tenant,
        summary=_redact(summary),
        severity=severity.value,
        required_approvals=2 if dual else 1,
        sod_group="creative-maker-checker",
        case_ref=result.id,
        citations=_kit_citations(result),
    )

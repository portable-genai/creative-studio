"""VariantDedupService — deterministic variant dedupe.

The fifth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. The LLM may draft near-identical variants (same angle, reworded);
shipping a "test" of two copies of the same idea wastes spend. This engine collapses
near-duplicate variants by a transparent token-overlap (Jaccard) similarity over their
combined copy, keeping the first-seen variant of each cluster so the surviving set is
genuinely distinct. It also assigns each variant a stable, content-derived id so dedupe and
audit are reproducible.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness. The
LLM never decides which variants are duplicates; this engine does, by a transparent rule
with a tunable threshold.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from .models import Variant

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "get",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "now",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "up",
        "we",
        "with",
        "you",
        "your",
    }
)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def variant_id(headline: str, body: str, cta: str) -> str:
    """A stable, content-derived id for a variant (reproducible across runs)."""
    digest = hashlib.sha1(  # noqa: S324 — non-crypto, just a stable content fingerprint
        "␟".join((headline or "", body or "", cta or "")).encode("utf-8")
    ).hexdigest()
    return f"var-{digest[:10]}"


@dataclass(frozen=True, slots=True)
class VariantDedupService:
    """Pure, deterministic variant dedupe by token-overlap similarity.

    ``similarity_threshold`` is a tunable, not a magic number: two variants whose combined
    copy exceeds it (Jaccard) are treated as the same idea.
    """

    similarity_threshold: float = 0.7

    def assign_ids(self, variants: tuple[Variant, ...] | list[Variant]) -> tuple[Variant, ...]:
        """Re-id every variant from its content so ids are stable and reproducible."""
        return tuple(replace(v, id=variant_id(v.headline, v.body, v.cta)) for v in variants)

    def dedup(self, variants: tuple[Variant, ...] | list[Variant]) -> tuple[Variant, ...]:
        """Drop near-duplicate variants, keeping the first-seen of each cluster."""
        kept: list[Variant] = []
        kept_tokens: list[frozenset[str]] = []
        seen_ids: set[str] = set()
        for variant in variants:
            if variant.id in seen_ids:
                continue
            toks = _tokens(self._copy_text(variant))
            if any(_jaccard(toks, kt) >= self.similarity_threshold for kt in kept_tokens):
                continue
            kept.append(variant)
            kept_tokens.append(toks)
            seen_ids.add(variant.id)
        return tuple(kept)

    @staticmethod
    def _copy_text(variant: Variant) -> str:
        return " ".join(p for p in (variant.headline, variant.body, variant.cta) if p)

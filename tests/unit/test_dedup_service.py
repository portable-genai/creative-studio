"""Unit tests for the deterministic VariantDedupService (stable ids + dedupe)."""

from __future__ import annotations

from creative_studio.domain.dedup_service import VariantDedupService, variant_id
from creative_studio.domain.models import Channel, Variant


def _v(headline: str, body: str = "", cta: str = "") -> Variant:
    return Variant(id="", headline=headline, body=body, cta=cta, channel=Channel.EMAIL)


def test_stable_content_id() -> None:
    assert variant_id("a", "b", "c") == variant_id("a", "b", "c")
    assert variant_id("a", "b", "c") != variant_id("a", "b", "d")


def test_assign_ids_is_content_derived() -> None:
    svc = VariantDedupService()
    out = svc.assign_ids((_v("Save more today", "Open an account; t&cs apply."),))
    assert out[0].id.startswith("var-")


def test_near_duplicates_collapse() -> None:
    svc = VariantDedupService(similarity_threshold=0.7)
    a = _v("Grow your savings now", "Earn a steady rate; t&cs apply.")
    b = _v("Grow your savings today", "Earn a steady rate; t&cs apply.")  # reworded twin
    c = _v("Refinance your home loan", "Compare rates; t&cs apply.")  # distinct
    kept = svc.dedup(svc.assign_ids((a, b, c)))
    assert len(kept) == 2  # the twin is dropped, the distinct one stays


def test_exact_duplicate_ids_dropped() -> None:
    svc = VariantDedupService()
    a = _v("Same copy", "Identical body; t&cs apply.")
    kept = svc.dedup(svc.assign_ids((a, a)))
    assert len(kept) == 1


def test_determinism() -> None:
    svc = VariantDedupService()
    variants = svc.assign_ids((_v("one offer", "body a"), _v("two offer", "body b")))
    assert svc.dedup(variants) == svc.dedup(variants)

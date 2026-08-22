"""Unit tests for the deterministic AssetSpecService (channel asset checks)."""

from __future__ import annotations

from creative_studio.domain.asset_service import AssetSpecService
from creative_studio.domain.models import (
    AssetSpec,
    Channel,
    CheckStatus,
    GeneratedImage,
    Variant,
)
from creative_studio.domain.rules import asset_spec_for


def _variant(
    headline: str,
    body: str = "",
    cta: str = "",
    image: GeneratedImage | None = None,
    channel: Channel = Channel.EMAIL,
) -> Variant:
    return Variant(id="v1", headline=headline, body=body, cta=cta, channel=channel, image=image)


def test_within_email_limits_passes() -> None:
    svc = AssetSpecService()
    result = svc.check(
        _variant("A short headline", "A concise body.", "Learn more"),
        asset_spec_for(Channel.EMAIL),
    )
    assert result.status is CheckStatus.PASS


def test_headline_too_long_fails() -> None:
    svc = AssetSpecService()
    spec = AssetSpec(channel=Channel.SEARCH, max_headline_chars=30)
    result = svc.check(_variant("x" * 50, channel=Channel.SEARCH), spec)
    assert result.failed
    assert any("max_headline_chars" in f.rule_id for f in result.findings)


def test_missing_required_image_fails() -> None:
    svc = AssetSpecService()
    result = svc.check(
        _variant("Banner", "copy", "Shop", channel=Channel.DISPLAY),
        asset_spec_for(Channel.DISPLAY),
    )
    assert result.failed
    assert any("requires_image" in f.rule_id for f in result.findings)


def test_image_dimensions_checked() -> None:
    svc = AssetSpecService()
    image = GeneratedImage(prompt="x", width=800, height=600, aspect_ratio="4:3")
    spec = AssetSpec(
        channel=Channel.SOCIAL,
        requires_image=True,
        image_width=1080,
        image_height=1080,
        allowed_aspect_ratios=("1:1",),
    )
    result = svc.check(_variant("h", "b", image=image, channel=Channel.SOCIAL), spec)
    rule_ids = {f.rule_id for f in result.findings}
    assert any("image_width" in r for r in rule_ids)
    assert any("allowed_aspect_ratios" in r for r in rule_ids)


def test_mandatory_disclaimer_token_missing_fails() -> None:
    svc = AssetSpecService()
    spec = AssetSpec(channel=Channel.WEB, mandatory_disclaimer_tokens=("t&cs apply",))
    result = svc.check(_variant("Headline", "Body without the notice.", channel=Channel.WEB), spec)
    assert result.failed
    assert any("mandatory_disclaimer_tokens" in f.rule_id for f in result.findings)


def test_determinism() -> None:
    svc = AssetSpecService()
    v = _variant("x" * 50, channel=Channel.SEARCH)
    spec = asset_spec_for(Channel.SEARCH)
    assert svc.check(v, spec) == svc.check(v, spec)

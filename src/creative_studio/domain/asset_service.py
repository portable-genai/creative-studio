"""AssetSpecService — deterministic asset-spec checks.

The fourth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Each channel has hard asset constraints (max headline / body / CTA
lengths, whether a CTA or image is required, image dimensions and allowed aspect ratios,
mandatory disclaimer tokens). Given a variant and the :class:`AssetSpec` for its channel,
this engine flags every constraint the variant breaches.

This is the consequential "will the channel accept this asset" check an auditor (or the ad
platform) re-runs, so it is code, not an LLM call. Findings cite the asset-spec requirement
they enforce.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    AssetCheck,
    AssetSpec,
    CheckStatus,
    Citation,
    Finding,
    RuleSeverity,
    SourceType,
    Variant,
)


def _spec_citation(spec: AssetSpec, requirement: str) -> Citation:
    return Citation(
        source_id=f"asset:{spec.channel.value}:{requirement}",
        source_type=SourceType.ASSET_SPEC,
        title=f"{spec.channel.value} asset spec: {requirement}",
    )


@dataclass(frozen=True, slots=True)
class AssetSpecService:
    """Pure, deterministic asset-spec validation for a variant's channel."""

    def check(self, variant: Variant, spec: AssetSpec) -> AssetCheck:
        """Check a variant against the asset spec for its channel; cited result."""
        findings: list[Finding] = []
        findings.extend(self._length_findings(variant, spec))
        findings.extend(self._presence_findings(variant, spec))
        findings.extend(self._image_findings(variant, spec))
        findings.extend(self._disclaimer_findings(variant, spec))
        return AssetCheck(
            variant_id=variant.id,
            channel=spec.channel,
            status=self._status(findings),
            findings=tuple(findings),
        )

    # ------------------------------------------------------------------ #
    # Constraint groups
    # ------------------------------------------------------------------ #
    def _length_findings(self, variant: Variant, spec: AssetSpec) -> list[Finding]:
        out: list[Finding] = []
        checks = (
            ("headline", variant.headline, spec.max_headline_chars),
            ("body", variant.body, spec.max_body_chars),
            ("cta", variant.cta, spec.max_cta_chars),
        )
        for name, value, limit in checks:
            if limit and len(value) > limit:
                out.append(
                    self._finding(
                        spec,
                        requirement=f"max_{name}_chars",
                        severity=RuleSeverity.HIGH,
                        message=(
                            f"{name.capitalize()} is {len(value)} chars; the "
                            f"{spec.channel.value} spec allows {limit}."
                        ),
                        span=value[: limit + 10],
                    )
                )
        return out

    def _presence_findings(self, variant: Variant, spec: AssetSpec) -> list[Finding]:
        out: list[Finding] = []
        if spec.requires_headline and not variant.headline.strip():
            out.append(
                self._finding(
                    spec,
                    requirement="requires_headline",
                    severity=RuleSeverity.HIGH,
                    message=f"The {spec.channel.value} spec requires a headline; none provided.",
                )
            )
        if spec.requires_cta and not variant.cta.strip():
            out.append(
                self._finding(
                    spec,
                    requirement="requires_cta",
                    severity=RuleSeverity.MEDIUM,
                    message=f"The {spec.channel.value} spec requires a call to action.",
                )
            )
        return out

    def _image_findings(self, variant: Variant, spec: AssetSpec) -> list[Finding]:
        out: list[Finding] = []
        if spec.requires_image and variant.image is None:
            out.append(
                self._finding(
                    spec,
                    requirement="requires_image",
                    severity=RuleSeverity.HIGH,
                    message=f"The {spec.channel.value} spec requires an image; none attached.",
                )
            )
            return out
        image = variant.image
        if image is None:
            return out
        if spec.image_width and image.width and image.width != spec.image_width:
            out.append(
                self._finding(
                    spec,
                    requirement="image_width",
                    severity=RuleSeverity.MEDIUM,
                    message=(
                        f"Image width {image.width}px does not match the required "
                        f"{spec.image_width}px."
                    ),
                )
            )
        if spec.image_height and image.height and image.height != spec.image_height:
            out.append(
                self._finding(
                    spec,
                    requirement="image_height",
                    severity=RuleSeverity.MEDIUM,
                    message=(
                        f"Image height {image.height}px does not match the required "
                        f"{spec.image_height}px."
                    ),
                )
            )
        if (
            spec.allowed_aspect_ratios
            and image.aspect_ratio
            and image.aspect_ratio not in spec.allowed_aspect_ratios
        ):
            out.append(
                self._finding(
                    spec,
                    requirement="allowed_aspect_ratios",
                    severity=RuleSeverity.MEDIUM,
                    message=(
                        f"Image aspect ratio {image.aspect_ratio} is not in the allowed set "
                        f"{', '.join(spec.allowed_aspect_ratios)}."
                    ),
                )
            )
        return out

    def _disclaimer_findings(self, variant: Variant, spec: AssetSpec) -> list[Finding]:
        out: list[Finding] = []
        text = " ".join(p for p in (variant.headline, variant.body, variant.cta) if p).lower()
        for token in spec.mandatory_disclaimer_tokens:
            if token.strip().lower() not in text:
                out.append(
                    self._finding(
                        spec,
                        requirement="mandatory_disclaimer_tokens",
                        severity=RuleSeverity.HIGH,
                        message=f"Mandatory disclaimer token '{token}' is missing from the asset.",
                        suggestion=f"Include '{token}'.",
                    )
                )
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _finding(
        spec: AssetSpec,
        requirement: str,
        severity: RuleSeverity,
        message: str,
        span: str = "",
        suggestion: str = "",
    ) -> Finding:
        return Finding(
            rule_id=f"asset:{spec.channel.value}:{requirement}",
            severity=severity,
            message=message,
            span=span,
            suggestion=suggestion,
            citations=(_spec_citation(spec, requirement),),
        )

    @staticmethod
    def _status(findings: list[Finding]) -> CheckStatus:
        if any(f.severity in (RuleSeverity.HIGH, RuleSeverity.CRITICAL) for f in findings):
            return CheckStatus.FAIL
        if findings:
            return CheckStatus.WARN
        return CheckStatus.PASS

"""CreativeStudioService — the brand-safe creative orchestrator.

Owns the full creative pipeline and calls only ports plus the deterministic engines. The
LLM (copy port) drafts the variants and the image port renders an image; the deterministic
engines (dedupe, brand, claim, policy, asset) decide everything consequential. Every
consequential output is maker-checker gated: the result always requires human review.

Pipeline (each step wrapped in ``tracer.span``; audited at the end):

    tracer.span("creative.generate"):
      guardrail.screen(INPUT)                  [blocked -> audit BLOCKED + raise]
      -> copy.generate_variants(brief)          (LLM drafts copy + variant ideas)
      -> dedup.assign_ids + dedup.dedup         [empty -> NoVariantsError]
      -> [optional] image.generate per variant   (Imagen on GCP; stub locally)
      -> for each variant: brand / claim / policy / asset checks (deterministic)
      -> assemble CreativeStudioResult (requires_human_review=True)
      -> copy.narrate(summary)                   (narration only, over computed checks)
      -> guardrail.screen(OUTPUT)               [blocked -> audit BLOCKED + raise]
      -> audit.record

Defensive: a degraded corpus / image call is tolerated, but a blocked input and an empty
variant set are hard errors so creative is never built from screened-out or absent content.

Pure domain code: no Google Cloud / ADK / FastAPI imports.
"""

from __future__ import annotations

import contextlib
import json
from contextlib import nullcontext
from typing import Any

from .asset_service import AssetSpecService
from .brand_service import BrandGuidelineService
from .claim_service import ClaimValidationService
from .dedup_service import VariantDedupService
from .errors import GuardrailBlockedError, NoVariantsError
from .models import (
    AuditEvent,
    Citation,
    CreativeBrief,
    CreativeStudioResult,
    Decision,
    Direction,
    GuardrailVerdict,
    ImageRequest,
    RetrievalQuery,
    Variant,
    VariantReview,
)
from .policy_service import PolicyValidationService
from .rules import (
    asset_spec_for,
    brand_rules_for,
    claim_rules_for,
    policy_rules_for,
)

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "used_rule_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
}


class CreativeStudioService:
    """Generate and brand-check creative variants. Constructor takes explicit ports."""

    def __init__(
        self,
        copy: Any,
        image: Any,
        knowledge_base: Any,
        guardrail: Any,
        tracer: Any,
        audit: Any,
        brand: BrandGuidelineService | None = None,
        claim: ClaimValidationService | None = None,
        policy: PolicyValidationService | None = None,
        asset: AssetSpecService | None = None,
        dedup: VariantDedupService | None = None,
        review_router: Any = None,
    ) -> None:
        self._copy = copy
        self._image = image
        self._knowledge_base = knowledge_base
        self._guardrail = guardrail
        self._tracer = tracer
        self._audit = audit
        self._brand = brand or BrandGuidelineService()
        self._claim = claim or ClaimValidationService()
        self._policy = policy or PolicyValidationService()
        self._asset = asset or AssetSpecService()
        self._dedup = dedup or VariantDedupService()
        # Rule R8: route an escalated result to Hrz7 after it is assembled and audited. Optional
        # so a service built without a router still assembles and audits the escalated result; it
        # just is not forwarded to a console.
        self._review_router = review_router

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(
        self,
        brief: CreativeBrief,
        actor: str,
        with_image: bool = False,
        tenant: str = "",
    ) -> CreativeStudioResult:
        with self._span("creative.generate", market=brief.market.value):
            self._guard(self._brief_text(brief), Direction.INPUT, actor, action="generate_creative")

            drafted = self._copy.generate_variants(brief)
            variants = self._dedup.dedup(self._dedup.assign_ids(drafted))
            if not variants:
                raise NoVariantsError("copy generation produced no usable variants")

            if with_image:
                variants = tuple(self._attach_image(v, brief) for v in variants)

            reviews = tuple(self._review_variant(v, brief) for v in variants)
            # Ground the result in the Hrz2 brand corpus (B2): the deterministic checks decide
            # the verdicts, and the brand-book / prior-creative passages add provenance so the
            # result cites the corpus, not only the rule sets. Best-effort, never blocks.
            brand_corpus = self._ground(brief)
            citations = self._merge_citations(
                tuple(c for r in reviews for c in r.citations) + brand_corpus
            )
            summary = self._narrate(brief, reviews, actor)
            result = CreativeStudioResult(
                id=(f"creative-{brief.market.value}-{brief.vertical.value}-{brief.channel.value}"),
                brief=brief,
                reviews=reviews,
                summary=summary,
                citations=citations,
                requires_human_review=True,
            )
            self._guard(summary, Direction.OUTPUT, actor, action="generate_creative")
            self._record(result, actor)
            # Rule R8: hand the already-assembled, already-audited escalation to Hrz7 for human
            # review. Routing is a hand-off, never fatal to a result that is already assembled and
            # audited (the audit ESCALATED record is the durable escalation of record).
            if self._review_router is not None and result.requires_human_review:
                with contextlib.suppress(Exception):
                    self._review_router.route(result, maker=actor, tenant=tenant)
            return result

    def review(self, brief: CreativeBrief, variant: Variant, actor: str) -> VariantReview:
        """Run the four deterministic checks on a single, externally supplied variant."""
        with self._span("creative.review", market=brief.market.value):
            ided = self._dedup.assign_ids((variant,))[0]
            review = self._review_variant(ided, brief)
            self._audit.record(
                AuditEvent(
                    action="review_variant",
                    actor=actor,
                    decision=Decision.ESCALATED if not review.approved else Decision.ALLOWED,
                    response=review.status.value,
                    citations=review.citations,
                    metadata={
                        "market": brief.market.value,
                        "vertical": brief.vertical.value,
                        "variant_id": ided.id,
                    },
                )
            )
            return review

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _review_variant(self, variant: Variant, brief: CreativeBrief) -> VariantReview:
        brand = self._brand.check(variant, brand_rules_for(brief.market, brief.vertical))
        claim = self._claim.check(variant, claim_rules_for(brief.market, brief.vertical))
        policy = self._policy.check(
            variant,
            brief.market,
            brief.vertical,
            policy_rules_for(brief.market, brief.vertical),
        )
        asset = self._asset.check(variant, asset_spec_for(variant.channel))
        return VariantReview(variant=variant, brand=brand, claim=claim, policy=policy, asset=asset)

    def _ground(self, brief: CreativeBrief) -> tuple[Citation, ...]:
        """Consult the Hrz2 brand corpus for passages relevant to this brief (B2).

        Returns the citations of the retrieved brand-book / prior-creative passages so the
        assembled result is grounded in the corpus rather than only the deterministic rule
        sets. Best-effort: a degraded or empty corpus is tolerated and never blocks creative,
        matching the pipeline's defensive posture. The retrieved passages inform provenance
        only; the consequential brand / claim / policy verdicts stay purely deterministic.
        """
        query_text = " ".join(
            p for p in (brief.topic, brief.product, brief.offer, brief.audience) if p
        ).strip()
        if not query_text:
            return ()
        try:
            passages = self._knowledge_base.search(
                RetrievalQuery(
                    text=query_text, top_k=3, market=brief.market, vertical=brief.vertical
                )
            )
        except Exception:  # noqa: BLE001 — brand-corpus grounding is best-effort, never blocks
            return ()
        return tuple(p.citation for p in passages)

    def _attach_image(self, variant: Variant, brief: CreativeBrief) -> Variant:
        from dataclasses import replace

        try:
            spec = asset_spec_for(variant.channel)
            aspect = spec.allowed_aspect_ratios[0] if spec.allowed_aspect_ratios else "1:1"
            request = ImageRequest(
                prompt=f"{brief.product or brief.topic}: {variant.headline}",
                aspect_ratio=aspect,
                width=spec.image_width,
                height=spec.image_height,
                market=brief.market,
                vertical=brief.vertical,
            )
            image = self._image.generate(request)
        except Exception:  # noqa: BLE001 — image generation is best-effort, never blocks
            return variant
        return replace(variant, image=image)

    # ------------------------------------------------------------------ #
    # LLM narration (narration only; never decides the verdicts)
    # ------------------------------------------------------------------ #
    def _narrate(self, brief: CreativeBrief, reviews: tuple[VariantReview, ...], actor: str) -> str:
        evidence = self._render_evidence(reviews)
        prompt = (
            f"Summarise the brand-safety review for {brief.vertical.value} creative in "
            f"market {brief.market.value}, channel {brief.channel.value}. Use ONLY the "
            f"check evidence below; cite the rule ids you reference.\n\nEVIDENCE:\n{evidence}"
        )
        from .models import LlmMessage, LlmRequest

        response = self._copy.generate(
            LlmRequest(
                messages=(LlmMessage(role="user", content=prompt),),
                response_schema=_SUMMARY_SCHEMA,
            )
        )
        return self._extract_summary(response.text, brief, reviews)

    @staticmethod
    def _render_evidence(reviews: tuple[VariantReview, ...]) -> str:
        lines: list[str] = []
        for review in reviews:
            for finding in review.findings:
                lines.append(f"[{finding.rule_id}] {finding.severity.value}: {finding.message}")
        return "\n".join(lines) or "(no issues found)"

    @staticmethod
    def _extract_summary(
        text: str, brief: CreativeBrief, reviews: tuple[VariantReview, ...]
    ) -> str:
        approved = sum(1 for r in reviews if r.approved)
        try:
            obj = json.loads(text)
            summary = obj.get("summary", "")
            if isinstance(summary, str) and summary:
                return summary
        except (json.JSONDecodeError, AttributeError):
            pass
        return (
            f"{approved}/{len(reviews)} {brief.vertical.value} variant(s) for "
            f"{brief.market.value}/{brief.channel.value} passed every deterministic "
            "brand, claim, policy and asset check. Human review required before publishing."
        )

    # ------------------------------------------------------------------ #
    # Cross-cutting: guardrail, tracing, audit
    # ------------------------------------------------------------------ #
    @staticmethod
    def _brief_text(brief: CreativeBrief) -> str:
        return " ".join(
            p for p in (brief.topic, brief.product, brief.offer, brief.audience, brief.tone) if p
        )

    def _guard(self, text: str, direction: Direction, actor: str, action: str) -> None:
        verdict: GuardrailVerdict = self._guardrail.screen(text, direction)
        if not verdict.allowed:
            self._audit.record(
                AuditEvent(
                    action=action,
                    actor=actor,
                    decision=Decision.BLOCKED,
                    prompt=text if direction is Direction.INPUT else "",
                    response=text if direction is Direction.OUTPUT else "",
                    metadata={"reason": verdict.reason, "direction": direction.value},
                )
            )
            raise GuardrailBlockedError(verdict.reason or "guardrail blocked the request")

    def _span(self, name: str, **attrs: str) -> Any:
        try:
            return self._tracer.span(name, **attrs)
        except Exception:  # noqa: BLE001 — tracing must never break the pipeline
            return nullcontext()

    @staticmethod
    def _merge_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for c in citations:
            key = (c.source_id, c.page)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return tuple(out)

    def _record(self, result: CreativeStudioResult, actor: str) -> None:
        self._audit.record(
            AuditEvent(
                action="generate_creative",
                actor=actor,
                decision=Decision.ESCALATED if result.requires_human_review else Decision.ALLOWED,
                response=result.summary,
                citations=result.citations,
                metadata={
                    "market": result.brief.market.value,
                    "vertical": result.brief.vertical.value,
                    "channel": result.brief.channel.value,
                    "variants": str(len(result.reviews)),
                    "approved": str(len(result.approved_reviews)),
                },
            )
        )

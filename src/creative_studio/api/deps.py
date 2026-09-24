"""Service factories — build domain services from the DI container.

One place that wires the ports resolved by :class:`creative_studio.config.Container` into
the domain orchestrator, so the CLI, API and agent layers share identical wiring.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import Container, build_container
from ..domain.brand_service import BrandGuidelineService
from ..domain.dedup_service import VariantDedupService
from ..domain.services import CreativeStudioService


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()


def make_studio_service(
    container: Container | None = None, *, review_router: Any = None
) -> CreativeStudioService:
    """Build the studio service; ``review_router`` replaces the container's for one call.

    A caller that reports the hand-off passes a
    :class:`~creative_studio.adapters.controls.RecordingReviewRouter` wrapping the container's
    router, so what it returns can say whether the result reached the review console.
    """
    container = container or get_container()
    policy = container.settings.policy
    return CreativeStudioService(
        copy=container.copy,
        image=container.image,
        knowledge_base=container.knowledge_base,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        brand=BrandGuidelineService(
            max_exclamations=policy.max_exclamations,
            caps_word_threshold=policy.caps_word_threshold,
            max_avg_word_length=policy.max_avg_word_length,
        ),
        dedup=VariantDedupService(
            similarity_threshold=policy.variant_similarity_threshold,
        ),
        review_router=review_router or container.review_router,
    )

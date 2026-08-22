from types import SimpleNamespace

from creative_studio.api.deps import make_studio_service
from creative_studio.config import PolicySettings


def test_adopter_policy_overrides_are_wired_into_deterministic_engines() -> None:
    marker = object()
    container = SimpleNamespace(
        settings=SimpleNamespace(
            policy=PolicySettings(
                max_exclamations=3,
                caps_word_threshold=4,
                max_avg_word_length=9.0,
                variant_similarity_threshold=0.9,
            )
        ),
        copy=marker,
        image=marker,
        knowledge_base=marker,
        guardrail=marker,
        tracer=marker,
        audit=marker,
        review_router=None,
    )
    service = make_studio_service(container)
    assert service._brand.max_exclamations == 3
    assert service._brand.caps_word_threshold == 4
    assert service._dedup.similarity_threshold == 0.9

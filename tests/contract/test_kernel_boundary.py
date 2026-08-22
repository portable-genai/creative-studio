from creative_studio.domain import kernel, models


def test_kernel_is_stable_and_excludes_vertical_aggregates() -> None:
    assert models.ThinkingLevel is kernel.ThinkingLevel
    assert {"CreativeStudioResult", "CreativeBrief", "VariantReview"}.isdisjoint(kernel.__all__)

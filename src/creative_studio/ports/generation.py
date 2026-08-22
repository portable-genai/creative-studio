"""Generation ports — copy (LLM) and image (Imagen).

Primary GCP adapters: **Gemini** for copy / variant drafting and narration, and **Imagen**
for image generation, both on the Gemini Enterprise Agent Platform. The LLM only drafts the
copy and variant ideas and narrates the already-computed deterministic checks; it never
decides whether a variant is brand-safe. The image model renders an asset to spec.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import (
    CreativeBrief,
    GeneratedImage,
    ImageRequest,
    LlmRequest,
    LlmResponse,
    Variant,
)


@runtime_checkable
class CopyGenerationPort(Protocol):
    def generate_variants(self, brief: CreativeBrief) -> tuple[Variant, ...]:
        """Draft ``brief.n_variants`` creative variants for the brief (copy only)."""
        ...

    def generate(self, request: LlmRequest) -> LlmResponse:
        """Generate a completion (used for narration over the computed checks)."""
        ...

    def classify(self, text: str, labels: list[str]) -> str:
        """Cheap single-label classification (triage/routing tier model)."""
        ...


@runtime_checkable
class ImageGenerationPort(Protocol):
    def generate(self, request: ImageRequest) -> GeneratedImage:
        """Generate an image asset for ``request`` (Imagen on GCP; a stub offline)."""
        ...

"""Imagen image adapter (ImageGenerationPort) — GCP managed stack.

Wraps the unified **Google GenAI SDK** (``google-genai``) Imagen image-generation API on the
**Gemini Enterprise Agent Platform** (Vertex backend). Given an :class:`ImageRequest` it
generates an asset image to the requested aspect ratio and maps the result onto a domain
:class:`GeneratedImage` (with the prompt, dimensions and a provenance :class:`Citation` for
the generating model). The deterministic asset-spec engine then checks the image against the
channel spec.

The residency region is resolved from the requested market and **validated** against the
per-market allow-list, so image generation stays inside the configured residency boundary.

All Google Cloud / GenAI SDK imports are LAZY so the on-prem / local / test profile imports
this module without ``google-genai`` installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import Citation, GeneratedImage, ImageRequest, SourceType
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google import genai


class ImagenImageAdapter:
    """Generate asset images via Imagen on the Agent Platform."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.models.image_model
        self._client: Any | None = None

    def _get_client(self, market: Any | None = None) -> genai.Client:
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google import genai  # noqa: PLC0415 — lazy: gcp profile only

            self._client = genai.Client(
                vertexai=True,
                project=self._settings.project_id,
                location=region,
            )
        return self._client

    def generate(self, request: ImageRequest) -> GeneratedImage:
        """Generate an image for ``request`` and map it to a domain ``GeneratedImage``."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client(request.market)
        # verify: https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
        response = client.models.generate_images(
            model=self._model,
            prompt=request.prompt,
            config=types.GenerateImagesConfig(
                number_of_images=max(request.n, 1),
                aspect_ratio=request.aspect_ratio or "1:1",
            ),
        )
        return self._to_image(request, response)

    def _to_image(self, request: ImageRequest, response: Any) -> GeneratedImage:
        images = getattr(response, "generated_images", None) or []
        uri = ""
        if images:
            image = getattr(images[0], "image", None)
            uri = getattr(image, "gcs_uri", "") or getattr(image, "uri", "") or ""
        return GeneratedImage(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            aspect_ratio=request.aspect_ratio,
            uri=uri,
            alt_text=f"Asset for: {request.prompt[:120]}",
            citation=Citation(
                source_id=f"imagen:{self._model}",
                source_type=SourceType.OTHER,
                title=f"Generated asset ({self._model})",
                url=uri,
            ),
        )

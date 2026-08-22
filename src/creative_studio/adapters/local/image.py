"""Local image adapter (ImageGenerationPort) — deterministic image stub.

The ``local`` profile's stand-in for **Imagen**: no model, no network, fully reproducible.
It returns a :class:`GeneratedImage` describing the asset that would be produced (prompt,
dimensions, aspect ratio, a deterministic ``example.test`` placeholder URI and alt text),
so the asset-spec engine has a real image to check and the offline demo shows the full
flow. SDK-free and unconditional (there is no Imagen emulator).
"""

from __future__ import annotations

import hashlib

from ...config import Settings
from ...domain.models import Citation, GeneratedImage, ImageRequest, SourceType


class LocalDeterministicImageAdapter:
    """Deterministic image stub: describes the asset Imagen would render, no network."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.models.image_model

    def generate(self, request: ImageRequest) -> GeneratedImage:
        digest = hashlib.sha1(  # noqa: S324 — non-crypto, stable placeholder id
            f"{request.prompt}|{request.aspect_ratio}".encode()
        ).hexdigest()[:12]
        return GeneratedImage(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            aspect_ratio=request.aspect_ratio,
            uri=f"https://images.example.test/{digest}.png",
            alt_text=f"Brand-safe illustration for: {request.prompt[:120]}",
            citation=Citation(
                source_id=f"image:{digest}",
                source_type=SourceType.OTHER,
                title=f"Generated asset ({self._model}, FICTIONAL placeholder)",
                url=f"https://images.example.test/{digest}.png",
            ),
        )

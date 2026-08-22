"""On-prem placeholder for ``ImageGenerationPort`` — the sovereign migration target."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import GeneratedImage, ImageRequest

_MESSAGE = (
    "On-prem ImageGenerationPort adapter is a migration placeholder; implement against your "
    "on-premise image model. Core domain logic is unchanged."
)


class OnPremImageAdapter:
    """Placeholder image adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, request: ImageRequest) -> GeneratedImage:
        raise NotImplementedError(_MESSAGE)

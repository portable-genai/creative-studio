"""Domain services aggregator — one import surface for the wiring layers.

The API, CLI and agent layers import services from here so that adding or renaming a
service is a single-file change at the boundary. The orchestrator
(:class:`CreativeStudioService`) composes the five deterministic engines and the ports.
"""

from __future__ import annotations

from .asset_service import AssetSpecService
from .brand_service import BrandGuidelineService
from .claim_service import ClaimValidationService
from .dedup_service import VariantDedupService
from .policy_service import PolicyValidationService
from .studio_service import CreativeStudioService

__all__ = [
    "CreativeStudioService",
    "BrandGuidelineService",
    "ClaimValidationService",
    "PolicyValidationService",
    "AssetSpecService",
    "VariantDedupService",
]

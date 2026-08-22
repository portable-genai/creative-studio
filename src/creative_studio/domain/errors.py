"""Domain exceptions for the Creative Studio system (D3).

Pure-Python exception hierarchy raised by the orchestration services. The domain layer
never imports Google Cloud, ADK, or any framework: these errors let callers (API, CLI,
the agent runtime adapter) react to domain-level failures without coupling to any vendor
SDK error type.
"""

from __future__ import annotations


class CreativeStudioError(Exception):
    """Base class for all domain-level errors raised by D3 services."""


class GuardrailBlockedError(CreativeStudioError):
    """Flagged/raised when the A1 guardrail blocks an input or output.

    A blocked unsafe request must never yield creative: the orchestrator raises this
    rather than drafting variants from screened-out content.
    """


class NoVariantsError(CreativeStudioError):
    """Raised when copy generation produced no usable variants.

    Creative must have at least one variant to review; an empty generation is a hard
    error so the studio never returns an empty, unreviewable result.
    """


class UnsupportedMarketError(CreativeStudioError):
    """Raised when a requested market has no configured residency region / profile."""


class UnsupportedVerticalError(CreativeStudioError):
    """Raised when a requested vertical has no configured seed / taxonomy."""


class UnsupportedChannelError(CreativeStudioError):
    """Raised when a requested channel has no configured asset spec."""

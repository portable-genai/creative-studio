"""Local ReviewRouterPort: enqueue the routed review to an in-memory outbox (no live Hrz7).

Exercises the R8 routing path offline: an escalated creative result is converted to a review and
enqueued (the same transactional outbox the platform adapter flushes to Hrz7), so tests and the
offline demo can assert that an escalation is routed without a running console.
"""

from __future__ import annotations

from review_kit import InMemoryOutbox

from ...config import Settings
from ...domain.models import CreativeStudioResult
from .._review_payload import result_to_review


class LocalReviewRouter:
    """Record routed reviews in an in-memory outbox for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._outbox = InMemoryOutbox()

    def route(self, result: CreativeStudioResult, *, maker: str, tenant: str = "") -> None:
        self._outbox.enqueue(
            result_to_review(result, maker=maker, tenant=tenant), actor="creative-studio"
        )

    @property
    def outbox(self) -> InMemoryOutbox:
        """Expose the outbox for inspection in tests and the demo."""
        return self._outbox

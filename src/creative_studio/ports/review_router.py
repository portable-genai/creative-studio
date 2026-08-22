"""ReviewRouterPort: the boundary that routes an escalated creative result to Hrz7 (rule R8).

Every ``CreativeStudioResult`` is consequential customer-facing creative and always requires human
review (maker-checker, P-06): the agent is the maker that drafts and deterministically checks the
variants, a qualified brand / compliance reviewer is the checker who disposes before anything is
published. Rule R8 says a producer that sets ``requires_human_review`` MUST route the item to the
Hrz7 Human-Review & Maker-Checker Console rather than terminate the escalation in a per-repo
boolean. This port is that hand-off. The domain stays pure: the adapter (not this port) depends on
the shared ``review-kit`` client and does the S2S submission.

The ``tenant`` is a call-time parameter (the server-verified caller's tenant), not a field on the
result, because a creative brief carries no tenant of its own.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import CreativeStudioResult


@runtime_checkable
class ReviewRouterPort(Protocol):
    def route(self, result: CreativeStudioResult, *, maker: str, tenant: str = "") -> None:
        """Route an escalated creative result to Hrz7 for human review (idempotent per id ideal)."""
        ...

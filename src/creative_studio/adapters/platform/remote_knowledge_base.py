"""Remote-platform knowledge-base adapter (KnowledgeBasePort) — thin HTTP client to A2.

When D3 reuses the shared platform, the brand corpus is the **A2 Enterprise Knowledge
Base**. This adapter implements the port by POSTing to A2's ``/v1/search`` (base URL from
``HRZ_KB_URL``). Constructs cleanly with no Google Cloud SDK; the HTTP body is wired in the
platform phase.
"""

from __future__ import annotations

from ...domain.errors import CreativeStudioError
from ...domain.models import RetrievalQuery, RetrievedPassage
from ...envread import setting_or_default

_DEFAULT_URL = "http://localhost:8082"
_PHASE = "RemoteKnowledgeBaseAdapter search() is wired in the platform phase."


class RemoteKnowledgeBaseError(CreativeStudioError):
    """Raised when the A2 knowledge-base service returns a non-2xx response."""


class RemoteKnowledgeBaseAdapter:
    """HTTP client for the shared A2 enterprise knowledge base."""

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._base_url = setting_or_default("HRZ_KB_URL", _DEFAULT_URL).rstrip("/")

    def search(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        raise NotImplementedError(_PHASE)

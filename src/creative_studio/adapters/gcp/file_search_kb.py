"""File Search knowledge-base adapter (KnowledgeBasePort) — GCP managed stack.

The primary brand-corpus backend: the **Gemini API File Search** tool over the brand /
creative corpus (brand book, prior approved creative, advertising-policy notes). File Search
is the managed RAG store in the unified **Google GenAI SDK** (``google-genai``): the adapter
issues a grounded ``generate_content`` against the configured File Search store and maps each
grounding chunk back to a domain :class:`RetrievedPassage` carrying a :class:`Citation` so
brand evidence is traceable.

The residency region is resolved from the active market and **validated** against the
per-market allow-list, so brand-corpus retrieval stays inside the configured residency
boundary (JP/AU/SG).

All Google Cloud / GenAI SDK imports are LAZY so the on-prem / local / test profile imports
this module without ``google-genai`` installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import Citation, RetrievalQuery, RetrievedPassage, SourceType
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google import genai


class FileSearchKnowledgeBaseAdapter:
    """Retrieve brand-corpus passages via the Gemini File Search tool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store_id = settings.knowledge_base.data_store_id
        self._top_k = settings.knowledge_base.top_k
        self._model = settings.models.reasoning
        self._client: Any | None = None

    def _get_client(self) -> genai.Client:
        region = resolve_region(self._settings)
        if self._client is None:
            from google import genai  # noqa: PLC0415 — lazy: gcp profile only

            self._client = genai.Client(
                vertexai=True,
                project=self._settings.project_id,
                location=region,
            )
        return self._client

    def search(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        """Retrieve brand-corpus passages relevant to ``query`` via File Search."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client()
        top_k = query.top_k or self._top_k
        file_search = types.Tool(
            file_search=types.FileSearch(file_search_store_names=[self._store_id])
        )
        response = client.models.generate_content(
            model=self._model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=query.text)])],
            config=types.GenerateContentConfig(tools=[file_search], temperature=0.0),
        )
        return self._to_passages(response, top_k)

    @staticmethod
    def _to_passages(response: Any, top_k: int) -> list[RetrievedPassage]:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return []
        metadata = getattr(candidates[0], "grounding_metadata", None)
        if metadata is None:
            return []
        chunks = getattr(metadata, "grounding_chunks", None) or []
        passages: list[RetrievedPassage] = []
        for idx, chunk in enumerate(chunks):
            retrieved = getattr(chunk, "retrieved_context", None)
            if retrieved is None:
                continue
            text = getattr(retrieved, "text", "") or ""
            title = getattr(retrieved, "title", "") or f"brand-{idx}"
            uri = getattr(retrieved, "uri", "") or ""
            passages.append(
                RetrievedPassage(
                    text=text,
                    citation=Citation(
                        source_id=title,
                        source_type=SourceType.INTERNAL,
                        title=title,
                        url=uri,
                        snippet=text[:200],
                    ),
                    score=1.0 - (idx / max(len(chunks), 1)),
                )
            )
            if len(passages) >= top_k:
                break
        return passages

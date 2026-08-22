"""JSON-safe serialization for domain objects.

``to_jsonable(obj)`` converts dataclasses, enums, datetimes and nested containers into
plain JSON-serializable Python. Used by the platform HTTP clients and the audit sink.

**Sourced from the shared ``hex-service-kit`` commons.** The walker used
to live here as a copy; it is now re-exported from :mod:`hex_service_kit.serialization`
(same rules: enum ``.value``, ISO datetimes, dataclass field dicts, tuples to lists,
stringified keys, never raises). Pure standard library.

**Derived verdicts.** ``to_jsonable`` walks ``dataclasses.fields``, so a value computed by a
``@property`` never reaches the wire. :class:`~creative_studio.domain.models.VariantReview`
computes its two consequential verdicts that way: ``status`` (worst of the four
deterministic checks) and ``approved`` (nothing failed). Serializing a review with the bare
walker therefore drops exactly the figures the engines decided, and every consumer falls
back to its own default: the console renders "warn" for a variant the engines passed and
counts 0 approved. Use :func:`review_jsonable` / :func:`result_jsonable` on the wire and in
the audit view so the served figures are the engines' verdicts, never a renderer default.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit.serialization import to_jsonable

from .models import CreativeStudioResult, VariantReview

__all__ = ["result_jsonable", "review_jsonable", "to_jsonable"]


def review_jsonable(review: VariantReview) -> dict[str, Any]:
    """One :class:`VariantReview` as JSON, carrying the verdicts the engines computed."""
    data: dict[str, Any] = to_jsonable(review)
    data["status"] = review.status.value
    data["approved"] = review.approved
    return data


def result_jsonable(result: CreativeStudioResult) -> dict[str, Any]:
    """One :class:`CreativeStudioResult` as JSON, with every review's derived verdict."""
    data: dict[str, Any] = to_jsonable(result)
    data["reviews"] = [review_jsonable(review) for review in result.reviews]
    return data

"""A stand-in for ``google.genai`` just deep enough to drive the managed adapters offline.

The gate installs no cloud SDK, so the Gemini and Imagen adapters are exercised here against a
fake ``types`` module and a fake client that record what each call was given. Every recorded
config is the kwargs the adapter passed to ``GenerateContentConfig``, which is where an omitted
``temperature`` has to be observed (a present-but-None key is not an omission).

``install`` puts the fake into ``sys.modules`` through the test's ``monkeypatch``, so it is gone
again before the import-safety tests assert that no adapter loaded ``google`` at import time.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


class _Config(dict[str, Any]):
    """``GenerateContentConfig`` / ``GenerateImagesConfig``: the kwargs, kept as given."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(kwargs)


def _types_module() -> ModuleType:
    types = ModuleType("google.genai.types")
    types.Content = lambda role, parts: SimpleNamespace(role=role, parts=parts)  # type: ignore[attr-defined]
    types.Part = SimpleNamespace(from_text=lambda text: SimpleNamespace(text=text))  # type: ignore[attr-defined]
    types.GenerateContentConfig = _Config  # type: ignore[attr-defined]
    types.GenerateImagesConfig = _Config  # type: ignore[attr-defined]
    types.ThinkingConfig = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    types.ThinkingLevel = SimpleNamespace(LOW="LOW", HIGH="HIGH")  # type: ignore[attr-defined]
    types.Tool = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    types.FileSearch = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    return types


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``from google.genai import types`` resolve to the fake for one test."""
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    types = _types_module()
    genai.types = types  # type: ignore[attr-defined]
    google.genai = genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)


@dataclass
class Call:
    model: str
    config: dict[str, Any]


@dataclass
class FakeModels:
    """``client.models``: answers every call with ``reply`` and records it."""

    reply: str = "{}"
    calls: list[Call] = field(default_factory=list)

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.calls.append(Call(model=model, config=dict(config)))
        return SimpleNamespace(text=self.reply, usage_metadata=None, candidates=[])

    def generate_images(self, *, model: str, prompt: str, config: Any) -> Any:
        self.calls.append(Call(model=model, config=dict(config)))
        image = SimpleNamespace(gcs_uri="gs://fictional-bucket/asset.png")
        return SimpleNamespace(generated_images=[SimpleNamespace(image=image)])


def client(reply: str = "{}") -> SimpleNamespace:
    return SimpleNamespace(models=FakeModels(reply=reply))


#: What a drafting call answers: two brand-safe variants, the shape the adapter asks for.
VARIANTS_REPLY = json.dumps(
    {
        "variants": [
            {"headline": "Save steadily", "body": "Earn 2.10% p.a. T&cs apply.", "cta": "Open"},
            {"headline": "A calm way to save", "body": "2.10% p.a., t&cs apply.", "cta": "See"},
        ]
    }
)

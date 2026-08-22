#!/usr/bin/env python3
"""Headless guard for every presenter-paced creative-studio demo step.

Two layers, because the second catches what the first cannot:

1. **In-process** — walk the session, render every step, assert the page carries the
   maker-checker banner and the step counter.
2. **Served path (F2)** — start the real ``demo_server`` on an ephemeral port, drive it over
   HTTP exactly as the presenter's browser does (``GET /``, ``POST /advance``,
   ``POST /restart``), then read the ``data-*`` evidence hooks back out of the SERVED HTML
   and compare every load-bearing figure with what the deterministic engines actually
   computed for that result.

Layer 2 exists because layer 1 cannot see a disagreement between the page and the engine: a
check that only asserts "this string is present" happily passes while the console reports a
verdict the engines never reached. That is exactly how the derived-verdict serialization
defect (``VariantReview.status`` / ``.approved`` are properties, so the plain dataclass-field
walker dropped them) shipped a demo showing WARN on every variant and "0/3 passed" while the
engines had passed all of them.
"""

from __future__ import annotations

import threading
import urllib.request
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError

from demo_server import DemoSession, Handler


class _HookParser(HTMLParser):
    """Collect every element that carries at least one ``data-*`` evidence hook."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k: (v or "") for k, v in attrs if k.startswith("data-")}
        if data:
            self.elements.append(data)


def _hooks(html: str) -> list[dict[str, str]]:
    parser = _HookParser()
    parser.feed(html)
    return parser.elements


def _one(elements: list[dict[str, str]], key: str) -> dict[str, str]:
    matches = [e for e in elements if key in e]
    assert len(matches) == 1, f"expected exactly one element carrying {key!r}, got {len(matches)}"
    return matches[0]


def _panels(elements: list[dict[str, str]]) -> set[str]:
    return {e["data-panel"] for e in elements if "data-panel" in e}


def _get(base: str, path: str = "/") -> str:
    with urllib.request.urlopen(base + path, timeout=30) as response:  # noqa: S310 (localhost)
        return response.read().decode("utf-8")


def _post(base: str, path: str) -> str:
    request = urllib.request.Request(base + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (localhost)
        return response.read().decode("utf-8")


def _check_in_process(session: DemoSession) -> None:
    """Layer 1: the session walks, and every rendered step carries its banner."""
    assert len(session.results) == 4
    for step, result in enumerate(session.results, 1):
        assert result["requires_human_review"] is True
        assert result["reviews"]
        page = session.render()
        assert f"Step {step}/{len(session.results)}" in page
        assert "HUMAN REVIEW REQUIRED" in page
        if step < len(session.results):
            session.advance()
    assert session.at_end
    session.reset()
    assert session.idx == 0


def _check_served_step(page: str, computed: Any) -> tuple[int, int]:
    """Layer 2: the SERVED page's figures must be the engines' figures.

    ``computed`` is the ``CreativeStudioResult`` the deterministic engines produced for this
    step. Returns ``(approved, variants)`` as read off the page.
    """
    elements = _hooks(page)

    missing = {"summary", "variants", "sources"} - _panels(elements)
    assert not missing, f"served page is missing panel(s): {sorted(missing)}"

    engine_approved = sum(1 for r in computed.reviews if r.approved)

    header = _one(elements, "data-result")
    assert header["data-result"] == computed.id, (
        f"served result id {header['data-result']!r} != engine {computed.id!r}"
    )
    assert int(header["data-result-variants"]) == len(computed.reviews)
    assert int(header["data-result-approved"]) == engine_approved, (
        f"served page claims {header['data-result-approved']} approved variant(s); "
        f"the engines approved {engine_approved}"
    )
    assert int(header["data-result-citations"]) == len(computed.citations)
    assert header["data-result-review"] == str(bool(computed.requires_human_review)).lower()

    summary = _one(elements, "data-approved-count")
    assert int(summary["data-approved-count"]) == engine_approved
    assert int(summary["data-variant-count"]) == len(computed.reviews)
    # The human-readable sentence must say the same thing as the hooks.
    assert f"{engine_approved}/{len(computed.reviews)} variant(s) passed" in page, (
        f"served page does not report '{engine_approved}/{len(computed.reviews)} variant(s) "
        "passed' in its own prose"
    )

    served_variants = [e for e in elements if "data-variant" in e]
    assert len(served_variants) == len(computed.reviews)
    for served, review in zip(served_variants, computed.reviews, strict=True):
        vid = review.variant.id
        assert served["data-variant"] == vid
        assert served["data-variant-status"] == review.status.value, (
            f"variant {vid}: served page shows {served['data-variant-status']!r}, "
            f"the engines computed {review.status.value!r}"
        )
        assert served["data-variant-approved"] == str(review.approved).lower(), (
            f"variant {vid}: served page shows approved="
            f"{served['data-variant-approved']!r}, the engines computed {review.approved!r}"
        )
        assert int(served["data-variant-findings"]) == len(review.findings)
        assert served["data-variant-image"] == str(review.variant.image is not None).lower()

    if computed.requires_human_review:
        assert _one(elements, "data-review-gate")["data-review-gate"] == "required"

    return engine_approved, len(computed.reviews)


def _check_served(session: DemoSession) -> tuple[int, int]:
    """Boot the real server, walk it over HTTP, and audit every served page."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.session = session  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        total_approved = 0
        total_variants = 0
        for step in range(len(session.results)):
            page = _get(base)
            assert f"Step {step + 1}/{len(session.results)}" in page
            approved, variants = _check_served_step(page, session.computed[step])
            total_approved += approved
            total_variants += variants
            if step < len(session.results) - 1:
                page = _post(base, "/advance")

        # The presenter's Restart must return the served page to step 1.
        page = _post(base, "/restart")
        assert "Step 1/" in page
        _check_served_step(page, session.computed[0])

        try:
            _get(base, "/nope")
        except HTTPError as exc:
            assert exc.code == 404
        else:  # pragma: no cover - the server must not serve unknown paths
            raise AssertionError("unknown path did not 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return total_approved, total_variants


def main() -> int:
    session = DemoSession()
    _check_in_process(session)
    approved, variants = _check_served(session)

    # Guard the guard: if the engines passed nothing, a served page that fell back to "warn"
    # for every variant would agree with them by accident and layer 2 would prove nothing.
    assert approved > 0, (
        "no variant was approved by the engines, so the served-figure check cannot "
        "distinguish a real verdict from a renderer fallback"
    )

    print(
        f"PASS demo self-test: 4/4 live creative results rendered, advanced, and reset; "
        f"served pages agree with the engines on {approved}/{variants} approved variant(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Live, presenter-controlled demo server for D3 (stdlib only, fully offline).

Holds a real set of D3 services over the in-memory ``local`` stack and reveals one cited
creative result per click, walking the presenter across both verticals (banking + online
retail), the JP/AU/SG markets and several channels. Each step renders the audit-first
console reused verbatim from ``render_result_ui``. No Google Cloud, no API key, no extra
dependencies.

    MKT_CREATIVE_PROFILE=local PYTHONPATH=src python scripts/demo_server.py [--port 8112]

Then open http://localhost:8112 and click "Next", or drive it with Playwright. The demo
port (8112) is deliberately distinct from the FastAPI API port (8102) and the Next.js
console port (3000) so all three can run side by side.
"""

from __future__ import annotations

import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import demo as scenario  # sibling: the synthetic scenarios + real local run
import render_result_ui as r  # sibling: reuse the exact audit-first rendering

from creative_studio.domain.models import CreativeBrief
from creative_studio.domain.serialization import result_jsonable

_CONTROL_CSS = """
.democtl{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;
  margin:-24px -18px 16px;padding:12px 18px;background:#0b101a;color:#fff}
.democtl .lbl{font-size:13px}.democtl .lbl b{color:#90b2ff}
.democtl .spacer{flex:1}.democtl form{margin:0}
.democtl button{font:inherit;font-size:13px;font-weight:600;border:0;border-radius:7px;padding:7px 14px;cursor:pointer}
.democtl .next{background:#3a60f0;color:#fff}.democtl .next:disabled{opacity:.4;cursor:default}
.democtl .restart{background:transparent;color:#a6b6cc;border:1px solid #33445b}
"""


class DemoSession:
    """Compute the real D3 results once, then reveal one per click."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        service = scenario._service()  # real services over the in-memory local stack
        self.results = []
        self.computed = []  # the engines' own CreativeStudioResult objects, kept for the self-test
        for topic, market, vertical, channel, offer, with_image in scenario._SCENARIOS:
            brief = CreativeBrief(
                topic=topic,
                market=market,
                vertical=vertical,
                channel=channel,
                product=topic,
                offer=offer,
            )
            result = service.generate(brief, actor="demo", with_image=with_image)
            self.computed.append(result)
            self.results.append(result_jsonable(result))
        self.idx = 0

    @property
    def at_end(self) -> bool:
        return self.idx >= len(self.results) - 1

    def advance(self) -> None:
        if not self.at_end:
            self.idx += 1

    def render(self) -> str:
        data = self.results[self.idx]
        page_html = r.render_result(data)
        brief = data.get("brief") or {}
        if not self.at_end:
            nxt = self.results[self.idx + 1].get("brief", {}).get("topic", "")
            next_btn = (
                "<form method='post' action='/advance'><button class='next' type='submit'>"
                f"Next &nbsp;·&nbsp; {r.esc(nxt)}</button></form>"
            )
        else:
            next_btn = "<button class='next' disabled>Demo complete</button>"
        label = f"{brief.get('market')} / {brief.get('vertical')} — {brief.get('topic')}"
        bar = (
            "<div class='democtl'>"
            f"<span class='lbl'>Step {self.idx + 1}/{len(self.results)} — "
            f"<b>{r.esc(label)}</b></span>"
            f"<span class='spacer'></span>{next_btn}"
            "<form method='post' action='/restart'>"
            "<button class='restart' type='submit'>Restart</button></form>"
            "</div>"
        )
        page_html = page_html.replace("</style>", _CONTROL_CSS + "</style>", 1)
        return page_html.replace("<div class='wrap'>", "<div class='wrap'>" + bar, 1)


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, to: str = "/") -> None:
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    @property
    def _sess(self) -> DemoSession:
        return self.server.session  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        with self.server.lock:  # type: ignore[attr-defined]
            if path == "/":
                self._send(self._sess.render())
            elif path == "/restart":
                self._sess.reset()
                self._redirect("/")
            else:
                self._send("<h1>404</h1>", 404)

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        with self.server.lock:  # type: ignore[attr-defined]
            if path == "/advance":
                self._sess.advance()
            elif path == "/restart":
                self._sess.reset()
        self._redirect("/")

    def log_message(self, *args: object) -> None:  # quiet console
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Live D3 creative-studio demo server")
    parser.add_argument("--port", type=int, default=8112)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.session = DemoSession()  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    print(f"D3 demo server on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()

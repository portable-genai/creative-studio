#!/usr/bin/env python3
"""Render the D3 audit-first console from the demo JSON into static HTML pages.

Server-side, dependency-free rendering of a cited :class:`CreativeStudioResult` (each
variant with its deterministic brand / claim / policy / asset findings, the cited rule for
every flag, and the maker-checker "human review required" banner). It reuses the exact
palette of the thin Next.js console so screenshots match the live UI, and runs entirely
offline over the obviously-fictional synthetic results written by ``scripts/demo.py``.

    PYTHONPATH=src python scripts/demo.py
    PYTHONPATH=src python scripts/render_result_ui.py scripts/out

Writes ``index.html`` (a small chooser) plus one ``<result-id>.html`` per result. The
rendering functions are also imported by ``scripts/demo_server.py`` for the presenter demo.

**Evidence hooks (F2).** Every result section carries a stable ``data-panel='<slug>'`` and
every load-bearing figure this product computes (variant count, approved count, per-variant
brand/claim/policy/asset verdict, finding severities, asset ids, citation count, the
maker-checker review flag) is emitted as a ``data-*`` attribute alongside its human-readable
text. The hooks are styling independent on purpose: ``scripts/demo_selftest.py`` drives the
real demo server over HTTP and reads the figures back out of the SERVED page, comparing each
one with what the deterministic engines computed, so a renderer that silently stops emitting
a figure — or a serializer that quietly drops a verdict — fails the gate instead of shipping
a demo that misreports its own results.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

STATUS_COLOR = {
    "pass": ("#d1fae5", "#047857"),
    "warn": ("#fef3c7", "#92400e"),
    "fail": ("#fee2e2", "#b91c1c"),
}
SEV_COLOR = {
    "info": ("#eef2f7", "#546b8b"),
    "low": ("#eef2f7", "#546b8b"),
    "medium": ("#fef3c7", "#92400e"),
    "high": ("#ffedd5", "#c2410c"),
    "critical": ("#fee2e2", "#b91c1c"),
}
SOURCE_LABEL = {
    "brand_guideline": "BRAND",
    "ad_policy": "POLICY",
    "claim_rule": "CLAIM",
    "asset_spec": "ASSET",
    "internal": "INTERNAL",
    "other": "SRC",
}
MARKET_LABEL = {"JP": "Japan", "AU": "Australia", "SG": "Singapore"}
VERTICAL_LABEL = {"banking": "Banking", "online_retail": "Online retail"}

CSS = """
:root{--ink-50:#f5f7fa;--ink-100:#e6ebf2;--ink-200:#cdd7e4;--ink-300:#a6b6cc;
--ink-400:#7790ae;--ink-500:#546b8b;--ink-600:#3f5470;--ink-700:#33445b;--ink-800:#1f2a3a;
--brand-50:#eef4ff;--brand-100:#dbe7ff;--brand-600:#2945d6;--brand-700:#2237ad;
--warn-bg:#fffbeb;--shadow:0 1px 2px rgba(11,16,26,.06),0 8px 24px rgba(11,16,26,.06);}
*{box-sizing:border-box}
body{margin:0;background:var(--ink-50);color:var(--ink-800);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
font-size:14px;line-height:1.5;padding:24px 18px}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:18px;margin:0 0 2px}
.sub{color:var(--ink-500);font-size:13px;margin:0 0 16px}
.sub b{color:var(--ink-800)}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;
border:1px solid var(--brand-100);background:var(--brand-50);color:var(--brand-700);margin-right:6px}
.pill.n{border-color:var(--ink-200);background:var(--ink-50);color:var(--ink-600)}
.panel{border:1px solid var(--ink-200);background:#fff;border-radius:10px;box-shadow:var(--shadow);margin-bottom:16px}
.panel>h2{border-bottom:1px solid var(--ink-100);padding:11px 16px;margin:0;font-size:13px;font-weight:600;color:var(--ink-800)}
.panel>.body{padding:16px}
.review{border:1px solid #fcd34d;background:var(--warn-bg);color:#92400e;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;margin-bottom:14px}
.summary{font-size:14px;line-height:1.6}
.variant{border:1px solid var(--ink-200);border-radius:9px;padding:12px;margin-bottom:12px}
.variant:last-child{margin-bottom:0}
.status{font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px}
.vid{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-400);margin-left:8px}
.headline{font-weight:600;margin-top:6px}
.bodycopy{color:var(--ink-600)}
.cta{margin-top:4px;font-size:12px;font-weight:600;color:var(--brand-700)}
.imgnote{margin-top:4px;font-size:11px;color:var(--ink-400)}
.finding{border-left:2px solid var(--ink-200);padding-left:10px;margin-top:8px}
.sev{font-size:10px;font-weight:700;padding:1px 6px;border-radius:5px;white-space:nowrap}
.fmsg{font-size:12px;color:var(--ink-700);margin-left:6px}
.cites{margin-top:6px;display:flex;flex-direction:column;gap:5px}
.cite{display:flex;gap:8px;align-items:baseline;border:1px solid var(--ink-200);background:var(--ink-50);border-radius:6px;padding:5px 9px}
.cite .src{font-family:ui-monospace,Menlo,monospace;font-size:10px;font-weight:600;color:var(--brand-700);background:var(--brand-50);border:1px solid var(--brand-100);border-radius:5px;padding:1px 6px;white-space:nowrap}
.cite .title{font-size:11px;color:var(--ink-700)}
.cite .id{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:var(--ink-500);margin-left:auto}
.ok{color:#047857;font-size:12px;margin-top:6px}
a.choose{display:block;padding:10px 12px;border:1px solid var(--ink-200);border-radius:8px;background:#fff;margin-bottom:8px;text-decoration:none;color:var(--ink-800)}
.muted{color:var(--ink-400);font-size:12px}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
        f"<div class='wrap'>{body}</div></body></html>"
    )


def _panel(title: str, body: str, slug: str) -> str:
    """One result section, tagged with the stable ``data-panel`` evidence hook."""
    return (
        f"<div class='panel' data-panel='{esc(slug)}'><h2>{esc(title)}</h2>"
        f"<div class='body'>{body}</div></div>"
    )


def _citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return ""
    rows = []
    for c in citations:
        label = SOURCE_LABEL.get(str(c.get("source_type")), "SRC")
        rows.append(
            f"<div class='cite' data-citation='{esc(c.get('source_id'))}' "
            f"data-citation-type='{esc(c.get('source_type'))}'>"
            f"<span class='src'>{esc(label)}</span>"
            f"<span class='title'>{esc(c.get('title'))}</span>"
            f"<span class='id'>{esc(c.get('source_id'))}</span>"
            "</div>"
        )
    return f"<div class='cites' data-citation-count='{len(citations)}'>" + "".join(rows) + "</div>"


def _findings(review: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("brand", "claim", "policy", "asset"):
        out.extend((review.get(key) or {}).get("findings", []))
    return out


def _variant(review: dict[str, Any]) -> str:
    v = review.get("variant") or {}
    status = str(review.get("status", "warn"))
    bg, fg = STATUS_COLOR.get(status, STATUS_COLOR["warn"])
    findings = _findings(review)
    finding_html = []
    for f in findings:
        sbg, sfg = SEV_COLOR.get(str(f.get("severity")), SEV_COLOR["medium"])
        finding_html.append(
            f"<div class='finding' data-finding-severity='{esc(f.get('severity'))}' "
            f"data-finding-rule='{esc(f.get('rule_id'))}'>"
            f"<span class='sev' style='background:{sbg};color:{sfg}'>{esc(f.get('severity'))}</span>"
            f"<span class='fmsg'>{esc(f.get('message'))}</span>"
            f"{_citations(f.get('citations', []))}</div>"
        )
    findings_block = "".join(finding_html) if findings else "<div class='ok'>No issues found.</div>"
    image = v.get("image")
    image_note = (
        f"<div class='imgnote' data-asset='{esc(image.get('uri'))}' data-asset-ratio='{esc(image.get('aspect_ratio'))}'>"
        f"image {esc(image.get('uri'))} ({esc(image.get('aspect_ratio'))})</div>"
        if image
        else ""
    )
    cta = f"<div class='cta'>{esc(v.get('cta'))}</div>" if v.get("cta") else ""
    return (
        f"<div class='variant' data-variant='{esc(v.get('id'))}' "
        f"data-variant-status='{esc(status)}' "
        f"data-variant-approved='{str(bool(review.get('approved'))).lower()}' "
        f"data-variant-findings='{len(findings)}' "
        f"data-variant-image='{str(bool(image)).lower()}'>"
        f"<span class='status' style='background:{bg};color:{fg}'>{esc(status.upper())}</span>"
        f"<span class='vid'>{esc(v.get('id'))}</span>"
        f"<div class='headline'>{esc(v.get('headline'))}</div>"
        f"<div class='bodycopy'>{esc(v.get('body'))}</div>{cta}{image_note}"
        f"{findings_block}</div>"
    )


def render_result(data: dict[str, Any]) -> str:
    """Render one cited CreativeStudioResult dict into a standalone HTML page."""
    brief = data.get("brief") or {}
    market = MARKET_LABEL.get(str(brief.get("market")), str(brief.get("market")))
    vertical = VERTICAL_LABEL.get(str(brief.get("vertical")), str(brief.get("vertical")))
    reviews = data.get("reviews", [])
    approved = sum(1 for r in reviews if r.get("approved"))
    citations = data.get("citations") or []
    head = (
        f"<div class='hdr' data-result='{esc(data.get('id'))}' "
        f"data-result-market='{esc(brief.get('market'))}' "
        f"data-result-vertical='{esc(brief.get('vertical'))}' "
        f"data-result-channel='{esc(brief.get('channel'))}' "
        f"data-result-variants='{len(reviews)}' "
        f"data-result-approved='{approved}' "
        f"data-result-citations='{len(citations)}' "
        f"data-result-review='{str(bool(data.get('requires_human_review'))).lower()}'>"
        f"<h1>Creative — {esc(brief.get('topic'))}</h1>"
        f"<p class='sub'><span class='pill'>{esc(market)}</span>"
        f"<span class='pill'>{esc(vertical)}</span>"
        f"<span class='pill n'>{esc(brief.get('channel'))}</span> id <b>{esc(data.get('id'))}</b></p>"
        "</div>"
    )
    review_banner = ""
    if data.get("requires_human_review"):
        review_banner = (
            "<div class='review' data-review-gate='required'>HUMAN REVIEW REQUIRED — "
            "maker-checker gate. Do not publish this creative until a qualified brand / "
            "compliance reviewer signs off.</div>"
        )
    summary = _panel(
        "Summary",
        f"<div class='summary'>{esc(data.get('summary'))}</div>"
        f"<p class='muted' style='margin-top:8px' data-approved-count='{approved}' "
        f"data-variant-count='{len(reviews)}'>{approved}/{len(reviews)} variant(s) "
        "passed every deterministic check.</p>",
        "summary",
    )
    variants = _panel(
        "Variants and deterministic checks",
        "".join(_variant(r) for r in reviews) or "<div class='muted'>none</div>",
        "variants",
    )
    sources = _panel(
        "Sources and grounding evidence",
        f"<div data-source-count='{len(citations)}'>"
        + (
            _citations(citations)
            or "<div class='muted'>No brand-corpus passage was retrieved for this brief.</div>"
        )
        + "</div>",
        "sources",
    )
    body = head + review_banner + summary + variants + sources
    return _page(f"Creative — {brief.get('topic')}", body)


def render_index(results: list[tuple[str, dict[str, Any]]]) -> str:
    rows = []
    for fname, data in results:
        brief = data.get("brief") or {}
        market = MARKET_LABEL.get(str(brief.get("market")), str(brief.get("market")))
        vertical = VERTICAL_LABEL.get(str(brief.get("vertical")), str(brief.get("vertical")))
        rows.append(
            f"<a class='choose' href='{esc(fname)}'><b>{esc(brief.get('topic'))}</b> "
            f"<span class='muted'>· {esc(market)} · {esc(vertical)} · "
            f"{esc(brief.get('channel'))}</span></a>"
        )
    body = (
        "<h1>D3 Brand-Safe Creative Studio — demo results</h1>"
        "<p class='sub'>Offline, obviously-fictional synthetic data. Local profile, no cloud.</p>"
        + "".join(rows)
    )
    return _page("D3 demo results", body)


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("scripts/out")
    results: list[tuple[str, dict[str, Any]]] = []
    for json_path in sorted(out_dir.glob("creative-*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        html_name = json_path.stem + ".html"
        (out_dir / html_name).write_text(render_result(data), encoding="utf-8")
        results.append((html_name, data))
        print(f"wrote {out_dir / html_name}")
    (out_dir / "index.html").write_text(render_index(results), encoding="utf-8")
    print(f"wrote {out_dir / 'index.html'}  ({len(results)} result(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

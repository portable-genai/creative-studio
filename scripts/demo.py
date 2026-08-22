#!/usr/bin/env python3
"""Offline synthetic-data demo for D3 (audit-first).

Runs the real ``CreativeStudioService`` over the local (offline) adapters for a few
(vertical, market, channel) scenarios, prints a readable, cited trace to stdout, and writes
the creative-result audit views to ``scripts/out/*.json`` for the dependency-free renderer /
screenshots. It is also the end-to-end smoke test for the slice: deterministic, so
screenshots never drift.

Usage::

    MKT_CREATIVE_PROFILE=local python scripts/demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from creative_studio.api.deps import make_studio_service
from creative_studio.config import Container, LocalSettings, Settings
from creative_studio.domain.models import Channel, CreativeBrief, Market, Vertical
from creative_studio.domain.serialization import result_jsonable
from creative_studio.domain.services import CreativeStudioService

_OUT = Path(__file__).resolve().parent / "out"

_SCENARIOS = [
    ("high-yield savings", Market.SG, Vertical.BANKING, Channel.EMAIL, "4.10% p.a.", False),
    ("multi-currency wallet", Market.JP, Vertical.BANKING, Channel.PUSH, "12 currencies", False),
    ("spring apparel sale", Market.AU, Vertical.ONLINE_RETAIL, Channel.SOCIAL, "20% off", True),
    ("loyalty points launch", Market.JP, Vertical.ONLINE_RETAIL, Channel.EMAIL, "5% back", False),
]


def _service() -> CreativeStudioService:
    base = Settings.load("config/settings.yaml")
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        channel=base.channel,
        models=base.models,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    return make_studio_service(Container(settings))


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    service = _service()
    for topic, market, vertical, channel, offer, with_image in _SCENARIOS:
        brief = CreativeBrief(
            topic=topic,
            market=market,
            vertical=vertical,
            channel=channel,
            product=topic,
            offer=offer,
        )
        result = service.generate(brief, actor="demo", with_image=with_image)
        print("=" * 78)
        print(f"CREATIVE: {topic}  [{market.value}/{vertical.value}/{channel.value}]")
        print(f"  review required : {result.requires_human_review}")
        print(
            f"  variants        : {len(result.reviews)} "
            f"({len(result.approved_reviews)} approved, {len(result.failed_reviews)} failed)"
        )
        for review in result.reviews:
            print(f"  [{review.status.value}] {review.variant.headline}")
            for finding in review.findings:
                print(f"      - [{finding.severity.value}] {finding.message}")
        out_path = _OUT / f"{result.id}.json"
        out_path.write_text(json.dumps(result_jsonable(result), indent=2), encoding="utf-8")
        print(f"  wrote           : {out_path}")
    print("=" * 78)
    print("Demo complete. Audit views written to scripts/out/ (obviously-fictional data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

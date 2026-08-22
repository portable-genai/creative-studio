"""Built-in, OBVIOUSLY-FICTIONAL synthetic seed for the ``local`` profile.

This is the offline brand / creative corpus that makes a local run grounded out of the
box: brand-book notes and prior-approved-creative passages, spanning BOTH verticals
(banking AND online retail) across ALL THREE markets (JP, AU, SG). Every brand name is
invented (suffixed FICTIONAL) and every URL points at ``example.test``; nothing here is
real data.

The data is keyed by (market, vertical) so the local KnowledgeBasePort serves vertical-
and market-specific brand guidance, proving D3 is generic and APAC without any hard-coded
branch in the engines.
"""

from __future__ import annotations

from ...domain.models import (
    Citation,
    Market,
    RetrievedPassage,
    SourceType,
    Vertical,
)

_Key = tuple[Market, Vertical]

# Short brand-corpus notes per (market, vertical): the kind of guidance a brand book holds.
_NOTES: dict[_Key, tuple[str, ...]] = {
    (Market.SG, Vertical.BANKING): (
        "Lion City Bank (FICTIONAL) brand voice is calm and transparent; lead with the rate "
        "and always show 't&cs apply' on rate promotions.",
        "Avoid pressure language; never imply a savings return is guaranteed.",
    ),
    (Market.JP, Vertical.BANKING): (
        "Sakura Trust Bank (FICTIONAL) brand voice is courteous and precise; bilingual ja/en "
        "copy must keep the same disclosures in both languages.",
        "Rate claims must carry 'as at' a date and a variable-rate note.",
    ),
    (Market.AU, Vertical.BANKING): (
        "Southern Reef Bank (FICTIONAL) brand voice is friendly and plain; home-loan copy must "
        "state comparison-rate context and 't&cs apply'.",
        "Never use 'risk-free' for any deposit or investment product.",
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): (
        "ShopMerlion (FICTIONAL) brand voice is upbeat but honest; sale copy must show the "
        "real 'was' price and an end date.",
        "Avoid false scarcity such as 'last chance ever'.",
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): (
        "MidoriMart (FICTIONAL) brand voice is cheerful and clear; loyalty-points copy must "
        "state how points are earned and any cap.",
        "Discount claims need the reference price (rrp).",
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): (
        "BoomerangBuy (FICTIONAL) brand voice is casual and direct; BNPL copy must include "
        "'t&cs apply' and never imply zero cost without conditions.",
        "Comparative claims ('cheaper than') need a stated basis.",
    ),
}


def _corpus_passages() -> tuple[RetrievedPassage, ...]:
    passages: list[RetrievedPassage] = []
    for (market, vertical), notes in _NOTES.items():
        tag_m, tag_v = market.value, vertical.value
        for idx, note in enumerate(notes, start=1):
            sid = f"brand-{tag_m.lower()}-{tag_v}-{idx}"
            passages.append(
                RetrievedPassage(
                    text=f"Brand note ({tag_m}/{tag_v}, FICTIONAL): {note}",
                    citation=Citation(
                        source_id=sid,
                        source_type=SourceType.INTERNAL,
                        title=f"Brand guidance {tag_m}/{tag_v} #{idx}",
                        url=f"https://corpus.example.test/{sid}",
                        page=1,
                        snippet=note[:200],
                        score=0.85,
                    ),
                    score=0.85,
                    tags=(f"market:{tag_m}", f"vertical:{tag_v}"),
                )
            )
    return tuple(passages)


CORPUS_PASSAGES: tuple[RetrievedPassage, ...] = _corpus_passages()

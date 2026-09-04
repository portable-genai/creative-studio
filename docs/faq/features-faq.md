# Features FAQ

For product, compliance, and delivery teams: what this studio does, what is deterministic vs
LLM, and, importantly, where its responsibilities **stop** and a sibling catalog system takes
over. Cross-references: [`README.md`](../../README.md), [`SPEC.md`](../../SPEC.md),
[`DEMO.md`](../../DEMO.md).

### What does `creative-studio` actually produce?

A `CreativeStudioResult`: a set of `VariantReview`s. From a `CreativeBrief` (topic, market,
vertical, channel, product, offer, audience, tone, number of variants) it drafts marketing
creative (copy plus an optional image) and, for each variant, runs four deterministic checks
(`BrandCheck`, `ClaimCheck`, `PolicyCheck`, `AssetCheck`), each producing cited `Finding`s,
an LLM summary that only narrates the computed checks, aggregate citations, and
`requires_human_review=True`. The headline output is not the copy; it is the proof that each
variant is on-brand and shippable, with every finding cited to the rule it enforces.

### What is deterministic vs done by the LLM?

The consequential decisions are **deterministic and replayable** (pure stdlib, unit-tested):
`brand_service.py` (forbidden / required terms, tone, reading level), `claim_service.py`
(superlatives, guarantees, comparatives, performance promises and unqualified "free" must each
carry a substantiation token), `policy_service.py` (per-market plus per-vertical advertising /
consumer-protection rules), `asset_service.py` (channel length limits, required headline / CTA
/ image, image dimensions and aspect ratios, mandatory disclaimer tokens), and
`dedup_service.py` (stable variant ids, dedupe near-identical ideas). The LLM only **drafts**
the variants and **narrates** the summary over the already-computed checks. It never decides
whether a variant is brand-safe. An auditor can recompute every verdict without the model.

### Is anything auto-published?

No. Every `CreativeStudioResult` sets `requires_human_review=True` (maker-checker, P-06); the
studio proposes and a qualified human disposes. A variant that fails a check is flagged, not
shipped, and a blocked guardrail verdict never yields creative. Per rule R8 an escalated result
is routed to the sibling `human-review-console` Human-Review console rather than parked in a per-repo boolean.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable GRC systems. It **owns** the creative-generation
plus brand-safety / claim / policy / asset domain logic and its cited outputs. It **integrates**
(via the `platform` profile's HTTP adapters) several cross-cutting concerns owned by sibling
systems; do not rebuild these in a fork:

| Concern | Owned by (catalog id / repo) | `creative-studio`'s role |
|---|---|---|
| Runtime guardrail: unsafe-content / prompt-injection / jailbreak defense | `agent-guardrail-gateway` | screens inbound briefs and outbound summaries on every run |
| Governed knowledge base (the brand book / approved-creative / ad-policy corpus) | `enterprise-knowledge-base` | ingests the brand corpus into it, retrieves grounded passages for provenance |
| Agent registry, versioning, identity, discovery | `agent-registry` | publishes its A2A AgentCard at `/.well-known/agent-card.json` |
| AI-quality / eval / model-risk promotion gate | `model-quality-gate` | its eval metrics gate promotion; the offline gate mirrors it |
| Observability + immutable WORM audit | `agent-observability` | writes audit events to it; traces spans through it |
| Human-Review and Maker-Checker console | `human-review-console` | routes an escalated creative result to it (rule R8) via `review-kit` |
| Marketing-compliance / final-publication gate | `marketing-compliance-gate` | `creative-studio` screens each variant; `marketing-compliance-gate` governs the go / no-go at publication (rule R7) |

So the guardrail, knowledge base, audit sink, eval platform, review console and the
publication gate are *dependencies*, not features of this repo. `creative-studio`'s own brand / claim /
policy / asset engines are the creative-diligence logic, distinct from those platform controls.

### How does `creative-studio` relate to the other marketing systems?

`creative-studio` is the creative-generation and brand-safety studio. Adjacent `mkt` systems handle other
points of the marketing lifecycle and should not be duplicated here: campaign planning
(`campaign-planner`), market intelligence (`market-intelligence`), next-best-action
(`next-best-action`), performance marketing (`performance-marketing-optimisation`), and the
marketing-compliance / governance gate (`marketing-compliance-gate`, `marketing-compliance-gate`). Check
[the organization's repository index](https://github.com/portable-genai) before building a
capability that may already have a home.

### Is it really generic across verticals and markets?

Yes, by construction. Banking and online retail are configurable verticals; Japan, Australia
and Singapore are first-class markets with their own residency regions
(`asia-northeast1` / `australia-southeast1` / `asia-southeast1`) and locales, all in
`config/settings.yaml` and the seed rule sets (`domain/rules.py`, keyed by `(market, vertical)`
/ channel), never a hard-coded branch. Active `vertical`, `market` and `channel` are settings,
overridable via `MKT_VERTICAL` / `MKT_MARKET` / `MKT_CHANNEL`.

### How do I see it working?

`make demo` runs the offline creative flow and renders the static audit-first HTML under the
local profile (real `CreativeStudioService`, no cloud, no API key); `make demo-server` is the
presenter-controlled offline server. `DEMO.md` documents the offline demo and the GCP demo
(region and vertical selectable). Everything in the walkthrough runs on synthetic, fictional
data.

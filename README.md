# Mkt3: Brand-Safe Creative and Content Studio (`creative-studio`)

**Industries:** Retail & e-commerce, Banking, Consumer goods, Media, Travel & hospitality

Generate marketing creative (copy + image) and prove it is brand-safe before it ships. The
LLM drafts the copy and variant ideas; **deterministic engines** decide whether each variant
is on-brand, makes only substantiated advertising claims, meets the per-market and
per-vertical advertising / consumer-protection policy, and fits the channel asset spec. Every
finding is cited back to the rule it enforces, and every result is maker-checker gated
(`requires_human_review=True`).

Part of the marketing catalog (`mkt` group). Mkt3 is **generic, multi-vertical and APAC**:
banking and online retail are configurable verticals, and Japan, Australia and Singapore are
first-class markets (residency regions `asia-northeast1` / `australia-southeast1` /
`asia-southeast1`, locales ja + en), all config + seed, never hard-coded.

## What it does

```
CreativeBrief (topic, market, vertical, channel, product, offer)
   -> Gemini drafts variants (copy + variant ideas)   [LLM: drafts only]
   -> VariantDedupService        (stable ids + dedupe near-identical ideas)
   -> Imagen renders an image    [optional]
   -> for each variant, the deterministic engines run:
        BrandGuidelineService    (forbidden / required terms, tone, reading level)
        ClaimValidationService   (superlatives, guarantees, comparatives, "free")
        PolicyValidationService  (per-market + per-vertical advertising law)
        AssetSpecService         (lengths, image dims, mandatory disclaimers)
   -> CreativeStudioResult (cited findings, requires_human_review=True)
   -> Gemini narrates the summary   [LLM: narration only, over the computed checks]
```

The deterministic engines are the heart of the system. The LLM never decides whether a
variant is brand-safe.

## Architecture (ports and adapters)

Pure domain (`src/creative_studio/domain`) depends on nothing but the standard library.
Every external capability is a `@runtime_checkable` Protocol (`src/creative_studio/ports`)
with three adapter families:

| Port | `gcp` (managed) | `local` (offline default) | `onprem` (fail-fast) |
| --- | --- | --- | --- |
| identity | IAP-verified assertion | seeded dev personas (no IdP) | NotImplementedError |
| copy | Gemini | deterministic templated generator | NotImplementedError |
| image | Imagen | deterministic stub | NotImplementedError |
| knowledge_base | File Search | SQLite FTS5 brand corpus | NotImplementedError |
| guardrail | Model Armor | heuristic | NotImplementedError |
| audit | Cloud Logging (WORM) | append-only SQLite | NotImplementedError |
| tracer | Cloud Trace (OTel) | no-op | NotImplementedError |
| evaluation | Gen AI eval (Hrz4) | offline gate | NotImplementedError |
| agent_registry | A2A registry | in-process | NotImplementedError |
| tool_catalog | MCP catalog | in-process | NotImplementedError |

Switch the whole stack with one setting: `MKT_CREATIVE_PROFILE=gcp|local|onprem`. A
`platform` profile binds thin clients to the shared Hrz1-Hrz5 platform services.

## Quick start (offline, no Google Cloud)

```bash
make install                 # python3.14 venv, [dev] only, NO google-cloud-*
make gate                    # ruff + mypy + pytest + eval, all on the local profile

# A cited, brand-checked artifact offline:
MKT_CREATIVE_PROFILE=local .venv/bin/mkt-creative generate "high-yield savings" \
    -m SG -v banking -C email -o "4.10% p.a."
MKT_CREATIVE_PROFILE=local .venv/bin/mkt-creative generate "spring apparel sale" \
    -m AU -v online_retail -C social -o "20% off"
```

See `DEMO.md` for the offline demo, the presenter server, and the GCP demo (region and
vertical selectable).

## Configuration

`config/settings.yaml` binds every port to an adapter per profile and carries the per-market
residency regions / locales. Active `vertical`, `market` and `channel` are settings
(overridable via `MKT_VERTICAL`, `MKT_MARKET`, `MKT_CHANNEL`). The rule sets (brand
guidelines, claim rules, advertising-policy rules, asset specs) are config + seed in
`src/creative_studio/domain/rules.py`, keyed by `(market, vertical)` / channel.

## Embedding and identity

The UI is a portable micro-frontend that drops into a client's existing web app (same-origin
reverse-proxy iframe) or runs standalone, and identity is verified server-side: every API
route resolves a verified `Principal` (the audit actor plus entitlements) via the
`IdentityPort`, and the request body never carries an `actor`. Local mode runs with no IdP
(seeded dev personas via `X-Dev-Persona`); secure mode verifies the GCP IAP assertion; onprem
is the client-IdP placeholder. Embedding knobs: `MKT_CREATIVE_CORS_ORIGINS` (explicit CORS
allowlist, never `*`), `MKT_CREATIVE_FRAME_ANCESTORS` (CSP `frame-ancestors`),
`MKT_CREATIVE_IAP_AUDIENCE`, and the UI's `NEXT_PUBLIC_BASE_PATH` / `NEXT_PUBLIC_EMBED`. See
[`docs/embedding-and-identity.md`](docs/embedding-and-identity.md).

## The gate

Green before any change lands, in a fresh `[dev]`-only venv (no `google-cloud-*`):

```
ruff check src tests
ruff format --check src tests
mypy src
pytest -m 'not integration' -q
python eval/run_eval.py        # exit 0
```

No git commit is performed by this tooling; the user commits.

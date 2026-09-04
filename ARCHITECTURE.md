# Architecture: `creative-studio` Brand-Safe Creative and Content Studio

`creative-studio` is a **ports-and-adapters (hexagonal)** service. The pure domain is the heart; every
external capability is a Protocol with swappable adapter families. The deterministic engines
own every consequential decision; the LLM only drafts copy and narrates.

## Layers

```
            +---------------------- adapters ----------------------+
 CLI / API  |  gcp (Gemini, Imagen, File Search, Model Armor, ...) |
   |        |  local (templated copy, FTS5 corpus, heuristics)     |
   v        |  onprem (fail-fast placeholders)                     |
 deps  -->  |  platform (thin HTTP clients to `agent-guardrail-gateway`..`agent-observability`)              |
   |        +-----------------------------------------------------+
   v                         ^  (Protocols / ports)
 CreativeStudioService  -----+
   |  (orchestrator, pure domain)
   v
 deterministic engines:  BrandGuidelineService, ClaimValidationService,
                         PolicyValidationService, AssetSpecService, VariantDedupService
   |
   v
 domain models (Citation, Vertical, Market, CreativeBrief, Variant, BrandCheck,
                ClaimCheck, PolicyCheck, AssetCheck, VariantReview, CreativeStudioResult)
```

`src/creative_studio/domain` imports only the standard library. `config.py` reads
`config/settings.yaml`, binds each port to an adapter for the active profile, and exposes a
lazy `Container`. `api/deps.py` wires the container into the orchestrator; the CLI and API
share that wiring.

## The five deterministic engines

| Engine | Decides | Inputs |
| --- | --- | --- |
| `BrandGuidelineService` | on-brand? (forbidden/required terms, tone, reading level) | variant + brand rules |
| `ClaimValidationService` | claims substantiated? (superlative/guarantee/comparative/free) | variant + claim rules |
| `PolicyValidationService` | meets market law? (per-market + per-vertical) | variant + market + vertical + policy rules |
| `AssetSpecService` | fits the channel? (lengths, image dims, disclaimers) | variant + channel asset spec |
| `VariantDedupService` | distinct ideas? + stable content ids | variants |

Each engine is pure, stdlib-only, replayable and unit-tested. Same inputs → same output. No
LLM, clock, network or randomness. Every `Finding` carries the `Citation` of the rule it
enforces. `VariantReview.status` and `CreativeStudioResult.requires_human_review` are derived
deterministically.

## Profiles

`MKT_CREATIVE_PROFILE` selects the adapter family for every port. There is no default:
unset is no choice, so the SDK-free adapters still bind (nothing else is installed) but the
`local` relaxations are refused, meaning no seeded no-auth personas and an empty CORS
allowlist. The value is validated where it is resolved, so an unknown or mis-capitalised
profile raises rather than binding something nobody chose.

- `local`: a working offline stack (what CI and dev run), SDK-free, deterministic, seedable.
- `gcp`: the managed stack (Gemini, Imagen, File Search, Model Armor, Cloud Logging WORM,
  Cloud Trace, Gen AI eval, A2A, MCP). All Google imports are lazy.
- `onprem`: fail-fast `NotImplementedError` placeholders satisfying the same Protocols
  (exit-portability proof).
- `platform`: thin HTTP clients to the shared `agent-guardrail-gateway`-`agent-observability` platform services. The
  `EvaluationGatePort` is a real client to `model-quality-gate` (`POST /v1/evaluations` + `POST /v1/gate`),
  with the metric suite chosen server-side by the registered `mkt3-creative` bundle.

The contract test imports + constructs every `local` and `onprem` adapter with no Google SDK
installed and asserts each satisfies its `@runtime_checkable` Protocol.

## Identity and embedding

Identity is an `IdentityPort` like every other port, resolved server-side from the inbound
request headers. `api/security.py` builds a `RequestContext` and asks the active profile's
adapter for a verified `Principal`; the API passes `principal.actor` (the audit subject) into
the domain services, and the request body carries no `actor`, so a caller cannot assert who
they are. The `local` adapter resolves seeded dev personas (no IdP) selected by
`X-Dev-Persona`; `gcp` / `platform` verify the GCP IAP assertion (`MKT_CREATIVE_IAP_AUDIENCE`);
`onprem` is the client-IdP fail-fast placeholder. The UI embeds same-origin behind a
reverse-proxy (`NEXT_PUBLIC_BASE_PATH` / `NEXT_PUBLIC_EMBED`) or runs standalone; the backend
sets CSP `frame-ancestors` (`MKT_CREATIVE_FRAME_ANCESTORS`) and an explicit CORS allowlist
(`MKT_CREATIVE_CORS_ORIGINS`, never `*`). Full guide: `docs/embedding-and-identity.md`.

## Residency

Markets carry residency regions (JP `asia-northeast1`, AU `australia-southeast1`, SG
`asia-southeast1`), config + seed in `MARKET_PROFILES` / `settings.yaml`. The GCP adapters
resolve and **validate** the region against the per-market allow-list before any network
call, so a managed call can never cross the configured residency boundary.

## Maker-checker

Creative that ships to customers is consequential. The agent (maker) drafts and runs every
deterministic check; a qualified brand / compliance reviewer (checker) disposes.
`CreativeStudioResult.requires_human_review` is always `True`, the CLI / UI surface a banner,
and every run is written to the WORM audit sink.

# SPEC: `creative-studio` Brand-Safe Creative and Content Studio

## Purpose

Generate marketing creative (copy + image) and prove it is brand-safe before it ships. The
LLM drafts; deterministic engines validate. Generic across banking and online retail, and
across the Japan / Australia / Singapore markets.

## Inputs and outputs

- **Input:** a `CreativeBrief` (topic, market, vertical, channel, product, offer, audience,
  tone, n_variants).
- **Output:** a `CreativeStudioResult`: a set of `VariantReview`s, each carrying the variant
  (headline / body / cta / optional image) and four deterministic checks
  (`BrandCheck`, `ClaimCheck`, `PolicyCheck`, `AssetCheck`) with cited `Finding`s, an LLM
  summary (narration only), aggregate citations, and `requires_human_review=True`.

## Functional requirements

1. **Generic, multi-vertical, APAC.** Banking and online retail are configurable verticals;
   JP / AU / SG are first-class markets. Region, locale, vertical, channel and the rule sets
   are config + seed, never hard-coded in a branch.
2. **Deterministic engines own consequential decisions.** Brand-guideline, advertising-claim,
   per-market + per-vertical policy, asset-spec validation and variant dedupe are pure,
   stdlib-only, replayable and unit-tested. The LLM never decides whether a variant is safe.
3. **Provenance.** Every finding cites the rule / policy / spec it enforces (a `Citation`).
4. **Maker-checker.** Every result requires human review; nothing auto-publishes.
5. **Guardrail.** Inbound briefs and outbound summaries are screened; a blocked request never
   yields creative.
6. **Audit.** Every run is written to a WORM-style audit sink.
7. **Portability.** Four profiles (`gcp` / `local` / `platform` / `onprem`) behind identical Protocols.
   The local profile is a working offline stack; onprem fails fast.

## Non-functional requirements

- Python 3.14; `[dev]`-only install requires no `google-cloud-*`.
- The gate (ruff + ruff format + mypy + pytest + eval) is green offline.
- GCP imports are lazy; importing a GCP adapter pulls in no `google` package.
- Markdown is em-dash-free; YAML scalars avoid space-colon-space.

## The deterministic checks

- **Brand:** forbidden terms, required terms, tone (all-caps shouting, excessive
  exclamation), reading level (plain language).
- **Claim:** superlatives, guarantees, comparatives, performance promises and unqualified
  "free" must each carry a substantiation token (e.g. "t&cs apply", "based on", "rrp").
- **Policy:** per-market + per-vertical advertising / consumer-protection rules (illustrative,
  fictional names: JP Act on Specified Commercial Transactions / Premiums & Representations
  Act; AU Australian Consumer Law / ASIC; SG advertising standards / PDPA; banking adds local
  financial-promotion rules as one configured set).
- **Asset:** channel length limits, required headline / CTA / image, image dimensions and
  aspect ratios, mandatory disclaimer tokens.

## Eval (`model-quality-gate`)

`eval/run_eval.py` runs the real `CreativeStudioService` over a golden set (both verticals ×
JP/AU/SG × several channels) and scores: `check_groundedness` (>= 0.80), `citation_accuracy`
(>= 0.90), `brand_safety_detection` (>= 0.80, a deliberately non-compliant probe must FAIL),
`review_safety` (>= 0.99). Exit 0 iff every metric clears its threshold. The GCP gate
(`--use-gcp`) mirrors the metric names and thresholds.

On the `platform` profile the `EvaluationGatePort` is a real HTTP client to the shared
`model-quality-gate` (not a stub): `evaluate` calls
`POST /v1/evaluations` and `gate` calls `POST /v1/gate`, both with a structured `target`
(model, prompt_version, dataset_id, system) plus a top-level `dataset_id`. `model-quality-gate` picks the
metric suite server-side from the registered `mkt3-creative` bundle, so the client never
sends a metric-name list.

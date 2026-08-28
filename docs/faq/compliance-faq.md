# Compliance FAQ

For compliance, marketing-legal, and model-risk teams assessing the repo's regulatory
posture. Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md) (the full principle to
control map and the JP / AU / SG crosswalk appendix), [`SPEC.md`](../../SPEC.md),
[`features-faq.md`](features-faq.md).

### Is this making advertising / publication decisions autonomously?

No. It is a **decision-support** producer (P-05): every consequential output requires human
review (maker-checker, P-06). The deterministic engines produce a documented, replayable
brand-safety assessment of each variant; a qualified brand / compliance reviewer disposes. A
variant that fails a brand, claim, policy or asset check is flagged, not shipped, and a blocked
guardrail verdict never yields creative. Final publication is separately gated by the sibling
**Mkt6** marketing-compliance system (rule R7); the in-repo checks are the first line before
that gate.

### Where does Mkt3 stop and Mkt6 begin?

Mkt3 **screens** each variant with its own deterministic brand-guideline, advertising-claim,
per-market policy and asset-spec engines and cites every finding. **Mkt6**
(`marketing-compliance-gate`) governs the final go / no-go at publication (rule R7). Mkt3 is a
mandatory dependency's *upstream*: it produces cited, review-required creative; Mkt6 owns the
publication gate. Do not rebuild the Mkt6 gate inside a Mkt3 fork.

### How is customer PII handled?

There is none to handle (audit checks C3 / C4 are N-A). Inputs are marketing-brief fields
(topic, product, offer, audience, tone) and the internal brand corpus (brand book, approved
creative, ad-policy notes); the audit stores the brief text and the summary, not customer
records. There is therefore no runtime PII redactor and no `pii_safety` eval metric.
Unsafe-content and prompt-injection screening on every run's input and output is the sibling
**Hrz1** guardrail (Model Armor on `gcp`, a heuristic locally), consumed here, not
re-implemented.

### How is the work auditable / reproducible?

Every run writes an immutable, hash-chained WORM `AuditEvent` with the decision and the
citation set (P-07). Every `Finding` and the aggregate `CreativeStudioResult.citations` carry a
`Citation` back to the rule / policy / spec it enforces (P-10). The consequential checks are
deterministic and stdlib-only, so an auditor can recompute every verdict from the same inputs
without the model, the LLM only drafts variants and narrates the already-computed checks. The
enterprise WORM audit system is **Hrz5**; the in-repo hash-chained store is the offline / local
stand-in (see [security-faq.md](security-faq.md) for its exact tamper-evidence limits).

### What is the model-risk story?

An offline eval gate (`eval/run_eval.py`) scores `check_groundedness`, `citation_accuracy`,
`brand_safety_detection` and `review_safety` against a golden set spanning both verticals,
JP / AU / SG and the channels, failing the build below threshold (P-08). Because the eval
invokes the real deterministic engines, `brand_safety_detection` cannot go falsely green, and
`review_safety` (>= 0.99) is structurally green-proof because `requires_human_review` defaults
True. The enterprise promotion gate and red-team harness are the sibling **Hrz4** system; this
repo's offline gate mirrors its metric names and thresholds so merges are guarded locally. A
fork must rebuild the golden set for its own brand, or the gate measures the wrong thing.

### Which regulators does this map to?

`COMPLIANCE.md` maps the internal P-01..P-13 / R1..R8 controls to concrete code, plus an
**adopter-owned regulator crosswalk appendix** covering the JP / AU / SG reference regimes:
SG ASAS, AU ACCC / ASIC advertising, JP fair-trade / premiums-and-representations, and MAS
FEAT / TRM. To add another supervisor, copy the appendix table, swap the regulator-reference
column, and re-review with local counsel: the Mkt3-control column is stable across regulators.

### Is data residency enforced?

Yes at deploy time, per market, with one stated exception: each of Japan (`asia-northeast1`),
Australia (`australia-southeast1`) and Singapore (`asia-southeast1`) carries its own in-country
region, validated to fail fast, with regional endpoints, a resource-location Org Policy
allowlist, CMEK, and a VPC-SC perimeter (P-03, P-09). **Agent Search follows none of them:** it
serves only `global` / `us` / `eu`, so the retrieval corpus defaults to `global` and is
unlocated. That is recorded in [`COMPLIANCE.md`](../../COMPLIANCE.md) rather than absorbed, and
`us` or `eu` confines it to one jurisdiction where an obligation bites. The residency-violation CI gate is the sibling
**Rsk3** `architecture-validator` (`domain/residency/`); the exit / concentration-risk plan is
**Rgc9** `operational-resilience-mapping` (`domain/concentration_exit/`). This repo enforces
residency in its own infra and is one of the systems those tools reason about.

### Can we run it against real campaigns / customer data today?

Not without your own legal, security, and model-risk sign-off. Every fixture and the seed brand
corpus are obviously fictional, and the docs state throughout that this is a reference build.
The adoption checklist ([`docs/ADOPTING.md`](../ADOPTING.md)) lists the steps, replace the seed
corpus and fixtures, own the brand / claim / policy rules, wire your IdP, rebuild the eval
golden set, that must precede any live use, and Mkt6 still governs publication.

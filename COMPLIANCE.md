# COMPLIANCE: Mkt3 Brand-Safe Creative and Content Studio

This maps every General Principle (P-01..P-13) and dependency rule (R1..R8) to a concrete
control in **this** repo. Where a principle does not apply to Mkt3, it is marked **n/a** with
the reason. Mkt3 generates marketing creative from a brief and a brand corpus and handles no
customer PII, so its load-bearing controls are brand-safety / advertising-claim checks,
provenance, maker-checker and audit.

> The brand, claim and creative data in `tests/`, `eval/` and the local seed is **fictional**.
> This build is a reference piece and is **not** intended for live use without your own legal,
> security and model-risk sign-off.

---

## General Principles

| # | Principle | How Mkt3 implements it | Evidence |
|---|-----------|----------------------|----------|
| **P-01** | Managed-first, minimal surface | Only the managed services the pinned stack uses are enabled; the agent is hosted on Agent Runtime | `infra/terraform/apis.tf`, `agent/root_agent.py` |
| **P-02** | No vendor lock-in (ports and adapters) | Domain depends only on `Protocol` ports; a profile switch rebinds adapters with no domain change. The `local` family proves the same domain runs entirely off-cloud (deterministic copy / image stubs, no Google Cloud SDK) | `ports/`, `config.py`, `adapters/local/*`, `adapters/onprem/*` |
| **P-03** | Data residency (in-country) | Region selected at deploy from a residency allowlist, with per-market overrides (JP / AU / SG), validated to fail fast; regional endpoints; `gcp.resourceLocations` Org Policy; VPC-SC perimeter | `config/settings.yaml` (`markets`), `infra/terraform/variables.tf`, `org_policy.tf`, `vpc_sc.tf` |
| **P-04** | Minimise data to the model | Mkt3 sends a brief and brand context, no customer PII; the model-boundary callback still guardrail-screens every prompt and response, and spans capture no content | `agent/callbacks.py`, `domain/studio_service.py` |
| **P-05** | Grounding over fine-tuning | Brand context is retrieved from the brand-guideline corpus (Hrz2 File Search), not trained into the model. See R3 for the current B2 PARTIAL note | `ports/knowledge_base.py`, `domain/brand_service.py` |
| **P-06** | Human-in-the-loop / maker-checker | Every `CreativeStudioResult` is `requires_human_review=True`; a human signs off before anything ships. Per rule R8 the escalation is routed to the Hrz7 Human-Review console via `review-kit`, not left as a per-repo boolean | `domain/studio_service.py`, `domain/models.py`, `ports/review_router.py` |
| **P-07** | Auditable and explainable by design | Every generation and review writes a WORM `AuditEvent` with the decision and citations; the ADK after-agent callback audits again at the model boundary | `domain/studio_service.py`, `adapters/gcp/cloud_logging_audit.py`, `agent/callbacks.py` |
| **P-08** | Eval-gated promotion | Offline eval gate scores brand-safety / claim-check accuracy and review safety; Hrz4 at promotion | `eval/run_eval.py`, `ports/observability.py` (`EvaluationGatePort.gate`) |
| **P-09** | Defense in depth / zero trust | CMEK, least-privilege IAM, private endpoints, a distinct agent identity; the guardrail screens twice (domain pipeline and model-boundary callback) | `infra/terraform/kms.tf`, `iam.tf`, `agent/callbacks.py` |
| **P-10** | Provenance on every claim | Every check finding carries a source-and-page `Citation` (to the brand rule / claim rule it fired); the model drafts copy but does not assert compliance | `domain/models.py` (`Citation`), `domain/claim_service.py` |
| **P-11** | Cost and latency control | A small triage-tier model handles routing / pre-checks; the reasoning model drafts copy, the deterministic engines check it | `config.py` (`ModelSettings.triage`) |
| **P-12** | Reversibility / documented exit | The `local` adapters run the whole pipeline off-cloud today (the working proof), and the `onprem` placeholders satisfy the same Protocols as the fail-fast sovereign target; the contract test proves parity for both | `adapters/local/*`, `adapters/onprem/*`, `tests/contract/test_port_parity.py`, `docs/onprem-migration.md` |
| **P-13** | Fair, consented marketing (advertising compliance) | Mkt3 **is** a creative producer: every variant is run through the deterministic brand-guideline, advertising-claim and policy checks before it can ship, and final publication is gated by Mkt6 (rule R7). The agent flags any variant that fails a check rather than shipping it | `domain/claim_service.py`, `domain/policy_service.py`, `agent/root_agent.py` instruction |

---

## Dependency rules

Mkt3's mandatory dependencies are **Hrz1, Hrz2, Hrz3, Hrz4 (gate), Hrz5 and Mkt6** (see
`systems/`). Each rule is satisfied by consuming the sibling service through a `platform`
adapter (with an on-prem stub), never by re-implementing the concern.

| Rule | Requirement | How Mkt3 satisfies it | Evidence |
|------|-------------|---------------------|----------|
| **R1** | Customer PII handling: Hrz1 guardrail + DLP redaction | Mkt3 consumes the Hrz1 guardrail for the brand-safety / claim screen and for prompt-injection and unsafe-output screening (INPUT and OUTPUT, pipeline and model boundary). **PII redaction is n/a**: Mkt3 handles a brief and brand context, no customer PII (C2/C3/C4 n/a in the practices audit) | `ports/safety.py`, `domain/studio_service.py`, `agent/callbacks.py` |
| **R2** | Audit to Hrz5 | Every generation / review writes an immutable WORM `AuditEvent`; the `platform` adapter posts to Hrz5 `/v1/audit` | `adapters/gcp/cloud_logging_audit.py`, `adapters/platform/remote_audit.py` |
| **R3** | Governed RAG via Hrz2 | The brand-guideline corpus is retrieved via Hrz2 governed File Search (`KnowledgeBasePort`). **NB (B2 PARTIAL):** the KB port is injected but not yet called in the generate path; brand grounding today comes from the deterministic brand-guideline rules, and wiring the KB into generation is tracked separately | `ports/knowledge_base.py`, `adapters/platform/remote_knowledge_base.py` |
| **R4** | Register in Hrz3 | The A2A AgentCard is published at `/.well-known/agent-card.json` and resolvable via Hrz3; the governed MCP tool catalog scopes access least-privilege | `agent/agent_card.py`, `api/app.py`, `adapters/platform/remote_registry.py`, `adapters/gcp/mcp_tool_catalog.py` |
| **R5** | Hrz4 promotion gate | `EvaluationGatePort.gate` checks the Hrz4 thresholds before promotion; the offline gate guards merges | `ports/observability.py`, `adapters/platform/remote_evaluation.py`, `eval/run_eval.py` |
| **R6** | Validated by Rsk3 at intake | As a new project, Mkt3 is validated by the Rsk3 intake validator externally. n/a in-repo | intake handled by Rsk3 externally |
| **R7** | Marketing compliance via Mkt6 | Mkt3 produces customer-facing creative, so it **must** pass Mkt6 (per-market advertising / consumer-protection claim check, brand guidelines, marketing consent) before publication; Mkt6 is a mandatory dependency and the in-repo checks are the first line before that gate | `domain/claim_service.py`, `agent/root_agent.py` instruction; Mkt6 governance |
| **R8** | Route escalations to Hrz7 (maker-checker console) | An escalated `CreativeStudioResult` (`requires_human_review`) is routed to the Hrz7 Human-Review & Maker-Checker Console through the shared `review-kit` client, not terminated in a per-repo boolean. The `platform`/`gcp` adapter S2S-submits to Hrz7; the `local` adapter enqueues to an in-memory outbox for offline demos/tests; the `onprem` placeholder fails fast. The descriptor, summary and citation snippets are redacted before the wire and the worst finding severity drives dual control | `ports/review_router.py`, `adapters/_review_payload.py`, `adapters/{local,platform,onprem}/review_router.py`, `domain/studio_service.py` |

---

## Why Mkt3 has no customer-PII surface (R1, C2..C4)

- **Brief-and-brand inputs only.** Creative is generated from a campaign brief plus brand
  context; there is no customer record and no tenant-partitioned customer data. The practices
  audit records C2/C3/C4 as **n/a by design**.
- **The guardrail is load-bearing anyway.** Beyond generic safety, the Hrz1 guardrail is the
  brand-safety and claim screen: it runs on INPUT and OUTPUT in the pipeline and again at the
  model boundary.
- **Determinism decides compliance (P-10, P-13).** The model drafts copy, but the
  brand-guideline, advertising-claim and policy engines decide whether a variant is safe to
  ship; each finding is cited and replayable.
- **Maker-checker on a consequential output (P-06).** Creative ships to customers, so it always
  requires human review, and final publication is gated by Mkt6.

---

## Appendix: regulator crosswalk (adopter-owned)

The `P-*` / `R*` catalog above is this build's internal control language; a regulated adopter
maps it onto its own supervisor's requirements. The rows below are a **reference mapping** for
the home markets (JP / AU / SG); a fork adds a column per additional regulator. This appendix
is *adopter-owned*: a template, not legal advice.

| Mkt3 control | Reference regime | What a supervisor looks for |
|---|---|---|
| P-13 / R7 claim + brand checks | SG ASAS; AU ACCC / ASIC advertising; JP fair-trade / premiums-and-representations | Advertising claims are substantiated and consumer-protection-compliant per market before publication |
| P-06 maker-checker | MAS FEAT (Accountability) | A qualified human disposes of every creative before it ships |
| P-07 WORM audit; P-10 provenance | MAS TRM (auditability); record-keeping | Immutable records; every check finding traceable to the rule it fired |
| P-03 residency; P-12 exit | MAS Outsourcing / Cloud guidelines | In-country data residency and a demonstrable exit / portability plan |
| P-08 quality / model-risk gate | MAS FEAT; model-risk expectations | A promotion gate with brand-safety / claim-accuracy / safety metrics |

**To add another regulator**: copy this table, replace the reference column with that
supervisor's instrument and section numbers, and re-review the third column with local
counsel. The Mkt3-control column is stable across regulators; only the mapping changes. The
sibling **Mkt6 Marketing Compliance** system is the shared gate these checks feed.

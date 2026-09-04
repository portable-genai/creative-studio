# On-prem migration (exit / portability): General Principle P-12

The whole point of the ports-and-adapters shape is that `creative-studio`'s exit story is **demonstrable,
not aspirational**. Switching from the managed GCP stack to a sovereign / on-premise stack is a
one-line profile change (`MKT_CREATIVE_PROFILE=onprem`) plus filling in the adapter bodies. The
domain core, the services, the API, the CLI and the agent wiring do not change.

## What "onprem" gives you today

Setting `MKT_CREATIVE_PROFILE=onprem` rebinds every port to a placeholder adapter under
`src/creative_studio/adapters/onprem/`. Those adapters:

- construct cleanly with **no Google Cloud SDK installed** (the contract test proves it),
- structurally satisfy the same `Protocol` as the managed GCP adapter, and
- raise `NotImplementedError` from every method that must not silently no-op (copy generation,
  image generation, knowledge base, guardrail, audit, evaluation, agent registry, tool
  catalog), while non-essential ports return safe defaults (the tracer is a no-op).

This is what makes the contract test `tests/contract/test_port_parity.py` meaningful: it
imports and constructs each on-prem placeholder and asserts interface parity, and separately
proves the `local` family is a WORKING offline stack implementing the same interfaces.

## The migration checklist

To run `creative-studio` on a sovereign / on-premise platform, implement these adapter bodies (the only
files that change):

| Port | On-prem file | What to implement |
|------|--------------|-------------------|
| `CopyGenerationPort` | `onprem/copy.py` | An on-prem model-serving endpoint for ad-copy drafting (e.g. Gemma) |
| `ImageGenerationPort` | `onprem/image.py` | An on-prem image-generation endpoint (or disable image assets) |
| `KnowledgeBasePort` | `onprem/knowledge_base.py` | An on-prem governed RAG store for the brand-guideline corpus (R3) |
| `GuardrailPort` | `onprem/guardrail.py` | An on-prem brand-safety / prompt-response screening backend (R1) |
| `AuditSinkPort` | `onprem/audit.py` | An on-prem immutable (WORM) audit store (R2) |
| `ObservabilityTracerPort` | `onprem/tracer.py` | An on-prem tracing backend (a no-op is acceptable) |
| `EvaluationGatePort` | `onprem/evaluation.py` | An on-prem eval backend and promotion gate (R5) |
| `AgentRegistryPort` | `onprem/registry_agent.py` | An on-prem A2A agent catalog (R4) |
| `ToolCatalogPort` | `onprem/tool_catalog.py` | An on-prem governed MCP tool catalog (R4) |
| `IdentityPort` | `onprem/identity.py` | Your on-prem IdP / SSO assertion verifier |

Nothing under `src/creative_studio/domain/` changes. The generate / review pipeline, the
deterministic brand-guideline, advertising-claim, policy and dedup engines, the maker-checker
policy, the citation mapping, the serialization, and the prompts are all profile-agnostic. The
agent wiring (`src/creative_studio/agent/`) is unchanged too: the FunctionTools call the same
domain services, so they run against whichever adapter family the profile binds.

## Why this matters for a regulated buyer

A bank's or retailer's brand function cannot accept a workload it cannot exit. Because the
domain depends only on Protocols, the buyer-facing properties (brand-safe / claim-checked
creative, cited findings, maker-checker, WORM audit) survive a platform change unchanged, and
the migration is a bounded, testable piece of work rather than a rewrite. The `local` family is
the proof that the off-cloud path already runs end to end today.

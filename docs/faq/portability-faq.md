# Portability FAQ

For architecture, cloud-governance, and exit-planning teams. The claim this repo makes is
"no vendor lock-in, demonstrably" (General Principle P-02 / P-12): it is designed to be
*shown*, not asserted. Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`docs/onprem-migration.md`](../onprem-migration.md),
[`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### What does "portable" actually mean here?

Three axes: **compute** (the whole stack migrates by a one-line profile change, with no
domain edits), **data** (the audit trail exports in an open, documented format and reloads
elsewhere with its integrity re-verified), and **experience / identity** (identity resolves
across hosts by an adapter swap, not a rewrite). Compute portability is proven executably by
the contract suite (`tests/contract/test_port_parity.py`), which constructs every port under
the SDK-free profiles with no Google Cloud installed.

### How does the profile switch work?

The pure-domain core (`domain/`) speaks only to `@runtime_checkable` `Protocol` **ports**;
`config/settings.yaml` binds one adapter per port per profile, and setting
`MKT_CREATIVE_PROFILE` (or `profile:` in the settings) rebinds the entire stack:

- `local`: a WORKING offline stack (deterministic templated copy, a deterministic image
  stub, a SQLite FTS5 brand corpus, a heuristic guardrail, a hash-chained audit). No Google
  Cloud SDK. What dev / test / CI run, but it must be named: unset is no choice, not a
  silent `local`.
- `gcp`: real managed services (Gemini copy, Imagen assets, File Search / Agent Search over
  the brand corpus, Model Armor, Cloud Logging WORM, Cloud Trace, Gen AI Evals).
- `platform`: thin HTTP clients delegating to the sibling horizontal-platform services.
- `onprem`: fail-fast placeholder stubs that still satisfy every Protocol (the sovereign-exit
  target); a primary CLI command exits 2 by design.

No `domain/` code changes across any of these. The contract test proves both `local` and
`onprem` construct with a single `Settings` arg and satisfy every port with no cloud SDK
present, and that deleting a binding fails the build.

### Is there a kernel / vertical split for reuse?

Partly, and honestly. The vertical-neutral types (`Citation`, `AuditEvent`, `EvalReport`,
the LLM envelope, the guardrail verdict) and the creative-specific artifacts currently live
together in `domain/models.py`, with the boundary described in the module header rather than
split into a separate `kernel.py`. A fork for a different creative vertical keeps the port
layer and those neutral types, so the portability guarantees transfer; physically extracting
a `kernel.py` is tracked as a quality-of-adoption refinement, not a portability gap.

### How do we get our data out?

The `local` audit store wraps the shared `hex_service_kit.audit.HashChainedAuditLog`: a
SHA-256 hash chain with SQLite `UPDATE` / `DELETE` triggers enforcing append-only, JSON Lines
export / restore, and `verify_chain()` line-by-line integrity re-verification on reload.
Records rehydrate to first-class `AuditEvent` objects (`domain/serialization.py`). The exit
story for the audit trail is "copy the JSONL file", not "migrate a product". Creative results
and reviews serialize the same way via `to_jsonable`.

### Is on-prem / sovereign deployment real or aspirational?

The `onprem` adapters are deliberate fail-fast placeholders (they raise
`NotImplementedError`) that nonetheless satisfy every Protocol and construct with a single
`Settings` arg, so the *interface contract* for a sovereign migration is proven and enforced
by CI today. The actual on-prem implementations are the migration work, scoped in
[`docs/onprem-migration.md`](../onprem-migration.md). This repo is not the sovereign-exit
*planner* (that is the sibling `operational-resilience-mapping`, module
`domain/concentration_exit/`); this repo is one of the systems whose exit that planner
reasons about.

### Does residency compromise portability?

No: residency is a deploy-time pin (the region, an Org Policy resource-location allowlist,
CMEK, a VPC-SC perimeter) and portability is the ability to change *where* the stack runs by
configuration. They are orthogonal. Each market carries its own in-country residency region,
`config/settings.yaml` and the per-market profiles: Japan `asia-northeast1`, Australia
`australia-southeast1`, Singapore `asia-southeast1`, never a hard-coded branch. A second
market or region is a settings / tfvars change, not a fork. The residency-violation CI gate
is the sibling `architecture-validator` (`domain/residency/`), which a fork should
run rather than re-implement.

### How does identity stay portable across hosts?

Identity resolves server-side through the `IdentityPort` on every route, so moving hosts is an
adapter swap, not a rewrite: `local` uses seeded dev personas with no IdP, `gcp` / `platform`
verify the IAP-injected assertion, and `onprem` is the client-IdP placeholder. The request
body never carries an actor. See [`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### What is NOT yet a single executable portability tour?

The profile swap, port parity and the `onprem` fail-fast family are proven offline by
`tests/contract/test_port_parity.py`, but there is not yet one `portability_demo` script that
also exercises tamper-evident audit export / reload and the identity swap end-to-end behind a
single exit code. That consolidation is tracked as quality-of-adoption; the underlying
guarantees are already tested.

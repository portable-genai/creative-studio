# Security FAQ

For an application-security team reviewing this repo before adopting it as a base. Answers
reflect the current code. Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`COMPLIANCE.md`](../../COMPLIANCE.md),
[`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### How is a request authenticated? Can a client spoof its identity?

No. Identity is resolved **server-side** from the transport context by an `IdentityPort`
adapter (`api/security.py`), never from the request body. The request schemas carry no `actor`
field (`api/schemas.py`), and any client-asserted actor or ACL is discarded. The audit actor
and the entitlement principals both come from the verified `Principal`. Per profile: `local` =
seeded dev personas (no IdP, offline only, selected by the `X-Dev-Persona` header which is
local-profile-only), `gcp` / `platform` = the IAP-injected signed assertion. There is no
OIDC / login flow in this repo (C8 is N-A): identity is IAP-injected, seeded, or the onprem
client-IdP placeholder.

### How is multi-tenant isolation handled? Is there object-level authz?

Mkt3 stores **no tenant-partitioned customer data** (C2 is N-A). The only data store is the
shared internal brand corpus (brand book, approved creative, ad-policy notes), scoped, not
secured, by `market:` / `vertical:` tags in `adapters/local/knowledge_base.py`. Identity still
resolves `tenant` plus entitlement principals server-side, but there is no per-tenant resource
that requires an object-level ACL. If a fork later adds tenant-owned assets to the corpus, the
KB matcher needs a real fail-closed ACL first; that latent note is called out in the practices
audit (C2).

### Is there any customer PII to protect?

No (C3 / C4 are N-A). Inputs are marketing-brief fields (topic, product, offer, audience,
tone) and the internal brand corpus; audit stores the brief text and the summary, not customer
records. There is no runtime PII redactor and no `pii_safety` eval metric because no customer
PII is processed. Unsafe-content screening (Model Armor on `gcp`, a heuristic locally) is the
Hrz1 guardrail concern, consumed on every run's input and output, not re-implemented here.

### What about the service-to-service calls in the `platform` profile?

The one real outbound call (the Hrz4 eval client) is re-based on the shared
`PromotionGateClient`: it attaches an S2S bearer credential and enforces an https-only
base-URL guard (plaintext non-loopback URLs are rejected at construction, which is why the
respx contract tests use an https fixture URL). The Hrz7 review router (`review-kit`) does
its S2S submission the same way. The remaining platform delegates are phase stubs.

### Is the demo / dev server safe? Does anything bind 0.0.0.0 by default?

Under the `local` profile the API and `make run-api` bind **loopback (127.0.0.1)** by default
(`API_HOST ?= 127.0.0.1` in the Makefile); serving the no-auth persona adapter on a
non-loopback interface must be deliberately overridden. Secure profiles keep the
container-friendly `0.0.0.0` (ingress is fronted by the platform / IAP). The offline demo
server is clearly dev-only.

### What HTTP security headers are set?

`api/app.py` middleware sets CSP `frame-ancestors` (plus `X-Frame-Options` in the self case),
and `ui/next.config.mjs` sets the same for the UI. This is a known **partial** (C6 in the
practices audit): `X-Content-Type-Options: nosniff`, `Referrer-Policy`, HSTS on secure
profiles, and a full UI CSP (`default-src 'self'`, scoped `connect-src`) are not yet set on
both surfaces. It is tracked as quality-of-adoption, not a load-bearing gap.

### How tamper-evident is the audit trail? What are its limits?

The `local` audit store wraps the shared `hex_service_kit.audit.HashChainedAuditLog`: a SHA-256
hash chain with SQLite `UPDATE` / `DELETE` triggers enforcing append-only, JSONL export /
restore, `verify_chain()`, and an honest-limits docstring. Proven by
`tests/unit/test_audit_chain.py`. In production the `gcp` profile uses a locked WORM bucket
(`retention_days: 2557`, ~7 years). This repo does not *replace* the platform audit system
(Hrz5); see [features-faq.md](features-faq.md).

### Supply chain: are dependencies pinned and scanned?

Yes. Committed lockfiles (`requirements-dev.lock`, `requirements-gcp.lock`, py3.12 uv pip
compile) are installed in CI and the Docker build; the base image is digest-pinned; GitHub
Actions are SHA-pinned; `dependabot.yml` proposes bumps; and CI runs `pip-audit` (on the
lockfiles) plus `npm audit` (on the UI) as hard gates. `ruff` is pinned exactly. The shared
commons are pinned by git tag with the exact SHA captured in the locks.

### Where are secrets? Are any committed?

No secret values are in the repo. `config/settings.yaml` stores only the **names** of env vars
holding secrets (`*_env`, `S2S_TOKEN`, ...); values are read at construction time and never
logged. `grep -riE "secret|token|key" config/` matches only `*_env` names. The brand corpus
seed and every fixture are obviously fictional.

### What is explicitly out of scope / a residual risk?

- Security-header baseline is partial on both surfaces (C6, above).
- The in-repo hash chain resists targeted edits but relies on the WORM bucket (or an external
  anchor) to resist full truncation / rewrite; the docstring states which classes are caught.
- This is a reference build: run your own pen-test, threat model and model-risk review before
  any live-data deployment (stated throughout the docs).

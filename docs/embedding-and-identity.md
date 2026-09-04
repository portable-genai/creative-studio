# Embedding and identity: client integration guide (`creative-studio` creative-studio)

This guide shows how an enterprise client runs the D3 Brand-Safe Creative and Content Studio
and, when desired, embeds its UI inside an existing web application with secure single sign-on
(SSO) so users never see a second login. It is grounded in what the codebase implements today.

The studio ships as two cooperating pieces:

- **Backend**: a FastAPI service (default port 8102) exposing the creative endpoints
  (`POST /v1/creative`, `POST /v1/review`), health (`GET /healthz`), and the seeded-persona
  list (`GET /v1/personas`).
- **UI**: a Next.js console (default port 3000) that calls the backend and renders the cited,
  brand-checked result. `NEXT_PUBLIC_EMBED=1` drops the UI's own chrome (`ui/app/layout.tsx`);
  the UI base path and API base are build-time env vars (`ui/next.config.mjs`, `ui/lib/api.ts`).

## 1. Three deployment shapes

Pick the cheapest shape the host can actually satisfy.

| Shape | Use when the host | Host work | Isolation | Identity |
| --- | --- | --- | --- | --- |
| **Embedded, same-origin reverse-proxy** | controls its own edge (nginx / Next.js rewrites) and can federate its IdP into Cloud IAP. | Two proxy routes (`/studio/*`, `/studio/api/*`) plus one `<iframe src="/studio/">`. | iframe = hard CSS/JS isolation; same-origin (first-party, no CORS, no third-party cookies). | IAP-verified `x-goog-iap-jwt-assertion` (`adapters/gcp/iap_identity.py`); the proxy forwards the header. |
| **Standalone behind Cloud IAP** | has no host app, or wants a separate console at its own URL. | DNS plus HTTPS load balancer plus IAP. | Top-level app (not framed); `frame-ancestors 'self'`. | IAP-verified assertion; IAP plus Workforce Identity Federation gives SSO from the client IdP. |
| **Local dev, no auth** | is evaluating offline, no IdP. | None. | N/A (offline). | Seeded personas via `X-Dev-Persona` (`adapters/local/identity.py`). |

Controls-edge and GCP-aligned goes to the embedded shape. No host app goes to standalone.
Offline evaluation goes to local dev.

## 2. Run locally, no auth

Local mode (`MKT_CREATIVE_PROFILE=local`) runs the entire pipeline offline: deterministic
templated copy, an SQLite FTS5 brand corpus, deterministic validators, and **no IdP, AD, or
LDAP**. Identity is resolved from a small set of seeded dev personas
(`adapters/local/identity.py`) selected by an `X-Dev-Persona` request header, with the first
persona as the default.

```bash
# Backend (repo root)
export MKT_CREATIVE_PROFILE=local
make run-api                      # uvicorn on http://localhost:8102

# UI (in ./ui)
# no .env.local needed: NEXT_PUBLIC_API_BASE already defaults to http://localhost:8102
npm install && npm run dev        # http://localhost:3000
```

The UI fetches `GET /v1/personas` and sends the chosen id as `X-Dev-Persona`. The seeded
personas deliberately span different entitlements and tenants (including a cross-tenant one):

| Persona id | Subject | Tenant | Entitlement principals |
| --- | --- | --- | --- |
| `analyst` | `demo.analyst@bank.example` | `demo-bank` | `group:creative-analyst`, `group:brand` |
| `approver` | `demo.approver@bank.example` | `demo-bank` | `group:creative-analyst`, `group:brand`, `group:creative-approver` |
| `auditor` | `demo.auditor@bank.example` | `demo-bank` | `group:audit` |
| `other-tenant` | `user@other-tenant.example` | `other-bank` | `group:creative-analyst` |

```bash
curl -s http://localhost:8102/v1/personas | jq .
curl -s -X POST http://localhost:8102/v1/creative \
  -H 'Content-Type: application/json' -H 'X-Dev-Persona: auditor' \
  -d '{"topic":"high-yield savings","market":"SG","vertical":"banking","channel":"email","offer":"4.10% p.a."}' | jq '.summary'
```

An unknown persona is a hard 401. In secure profiles `X-Dev-Persona` is ignored entirely
(Section 4), so leaving persona-selection code in the UI is harmless in production, and
`/v1/personas` returns an empty list outside `local`.

## 3. Standalone behind Cloud IAP (secure GCP)

When there is no host application, deploy the studio on its own URL:

1. Deploy the backend and UI behind the same HTTPS load balancer and Cloud IAP.
2. Set `MKT_CREATIVE_PROFILE=gcp` and `MKT_CREATIVE_IAP_AUDIENCE` so the backend verifies the
   IAP assertion (the adapter refuses to verify without the audience).
3. Point the UI at the backend with `NEXT_PUBLIC_API_BASE`. If the UI and backend are on
   **different** origins, also set `MKT_CREATIVE_CORS_ORIGINS` to the UI origin (an explicit
   allowlist, never `"*"`):

   ```bash
   export MKT_CREATIVE_CORS_ORIGINS="https://studio.client.com"
   export NEXT_PUBLIC_API_BASE="https://api.studio.client.com"
   ```

4. Share the URL with authorized users. IAP plus Workforce Identity Federation gives silent
   SSO from the corporate IdP while the corporate session is live.

Cloud IAP authenticates on the load balancer (not hand-rolled), composes with Cloud Armor and
Context-Aware Access, and injects the signed `x-goog-iap-jwt-assertion`. The backend still
independently re-verifies that assertion (signature, audience, issuer, expiry) and derives the
`Principal` itself, so the network gate and the app-level check are defense in depth. Leave
`MKT_CREATIVE_FRAME_ANCESTORS` at its `'self'` default: nothing should iframe a standalone
deployment.

## 4. Embed via same-origin reverse proxy

This is the smallest change for a host that controls its edge: serve the studio **under your
own origin** at a sub-path (for example `/studio/`) via a reverse proxy, then drop an iframe
pointing at that same-origin path. Because the iframe is first-party there are no
third-party-cookie issues and no CORS to configure. The client owns exactly two things: a proxy
route and an iframe tag.

**nginx:**

```nginx
# On https://portal.client.com
location /studio/ {
    proxy_pass         http://studio-ui.internal:3000/;      # the Next.js UI
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
# The UI's API calls (NEXT_PUBLIC_API_BASE=/studio/api) resolve same-origin:
location /studio/api/ {
    proxy_pass         http://studio-backend.internal:8102/;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
    # IAP runs in front of this origin, so x-goog-iap-jwt-assertion is present on the
    # inbound request and forwarded through to the backend.
}
```

**Next.js host app** (if the parent is itself Next.js, use `rewrites()` in its config):

```js
// next.config.mjs of the PARENT app
const nextConfig = {
  async rewrites() {
    return [
      { source: "/studio/api/:path*", destination: "http://studio-backend.internal:8102/:path*" },
      { source: "/studio/:path*",     destination: "http://studio-ui.internal:3000/:path*" },
    ];
  },
};
export default nextConfig;
```

**Mount the studio UI under the sub-path and hide its chrome** (build-time env for the UI):

```bash
NEXT_PUBLIC_BASE_PATH=/studio      # mount the UI (and assets) under the sub-path
NEXT_PUBLIC_API_BASE=/studio/api   # same-origin API calls (no CORS needed)
NEXT_PUBLIC_EMBED=1                # hide the UI's own header/nav chrome when embedded
```

**The iframe tag** (host page), inside a sized container so the frame does not collapse:

```html
<iframe
  src="/studio/"
  title="Brand-Safe Creative Studio"
  style="width:100%; height:800px; border:0;"
  loading="lazy">
</iframe>
```

**Allow the parent origin to frame the UI.** The backend emits
`Content-Security-Policy: frame-ancestors <MKT_CREATIVE_FRAME_ANCESTORS>` via middleware
(`api/app.py`), and adds `X-Frame-Options: SAMEORIGIN` **only** when the value is `'self'` (the
legacy header cannot express a multi-origin allowlist, so the multi-origin case is left to CSP):

```bash
export MKT_CREATIVE_FRAME_ANCESTORS="https://portal.client.example"
# multiple parents are space-separated, per the CSP grammar:
# export MKT_CREATIVE_FRAME_ANCESTORS="https://portal.client.example https://admin.client.example"
```

`MKT_CREATIVE_FRAME_ANCESTORS` is read in three states, not two. Leaving it **unset** keeps the
restrictive `'self'` default. Setting it to a **blank** value is refused at boot: the service
will not start. That is deliberate, because a blank value used to render
`Content-Security-Policy: frame-ancestors ` with an empty directive, which browsers discard as
a parse error, and the `X-Frame-Options` fallback was skipped at the same time, so the
clickjacking control disappeared with no signal. If you meant "no parent may frame this", that
is the `'self'` default, so unset the variable. The same rule applies to the UI's
`NEXT_PUBLIC_FRAME_ANCESTORS`, which is refused at build time when set and blank.

Scope limit: `frame-ancestors` is only honored on the HTTP response of the document the browser
actually frames. In the same-origin proxy shape the framed document is served through the proxy,
so the backend header reaches it. In a cross-origin shape the framed document is the Next.js UI
on a different origin, so that document carries its own full policy, described next.

### 4a. The console's own Content-Security-Policy

The console serves a complete default-deny policy, not just a framing directive. It is built in
exactly one module, `ui/lib/csp.mjs`, and set in exactly one place, `ui/proxy.ts`, on every
request. `ui/next.config.mjs` emits no `Content-Security-Policy` at all: two layers both setting
one leaves the browser intersecting them, the stricter wins per directive, and a per-request
nonce set by one layer would be silently overridden by the static copy of the other.

The policy carries `default-src 'self'`, `base-uri 'self'`, `form-action 'self'`,
`object-src 'none'`, `style-src 'self' 'unsafe-inline'` (the Next runtime injects critical CSS
and there is no nonce path for it), `img-src`/`font-src` with `data:`, a `connect-src` widened
only to the ORIGIN of `NEXT_PUBLIC_API_BASE`, and `frame-ancestors` resolved exactly as the
backend resolves its own. `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`
are genuinely static, so they stay in the `next.config.mjs` header table.

`script-src` is the load-bearing part, and it is `'self'` plus a PER-REQUEST nonce plus
`'strict-dynamic'`. Next serves its hydration bootstrap as an inline script carrying the Flight
payload, so a bare `script-src 'self'` blocks it: `__next_f` never fills, React never attaches,
and the console renders every control as dead markup while the headers, the type-check, the build
and every string-level test stay green.

Two things must BOTH hold or the nonce makes matters worse rather than better:

1. `proxy.ts` sets the policy on the REQUEST headers as well as the response. The request copy is
   where Next reads the nonce it stamps onto each script tag; the response copy is what the
   browser enforces. Either alone fails, in opposite directions.
2. The route must be DYNAMICALLY rendered, which is why `app/layout.tsx` sets
   `export const dynamic = "force-dynamic"`. A statically prerendered page was built before the
   nonce existed, so nothing in its HTML carries the nonce, and `'strict-dynamic'` switches off
   the `'self'` fallback that had at least been loading the chunk scripts. That half-configured
   state blocks strictly MORE than having no `script-src` at all did.

Because the response header is byte-identical in the working case and in the dead-markup case,
no header assertion can tell them apart. `ui/scripts/assert-hydratable.mjs` starts the BUILT
server, fetches the served document, and asserts that the policy is complete, that it carries a
nonce, and that every script tag carries that same nonce. It runs last in `make ui-check` and in
CI. `next.config.mjs` additionally refuses at build and boot if the layout is missing
`force-dynamic`.

## 5. The identity contract

The single invariant, preserved across every shape: **the server never trusts a client-asserted
actor or ACL.** `get_principal` (`api/security.py`) builds a `RequestContext` from inbound
headers only, asks the active `IdentityPort` adapter to resolve a verified `Principal`, and a
failure is a hard 401. Each route receives `actor=principal.actor` from that verified
`Principal`; the request schemas carry **no** `actor` field, so any client-supplied identity is
discarded. There is no path by which a caller can assert who they are.

The `Principal` (`domain/identity.py`) models what enforcement needs: `subject` (the audit
actor), `principals` (entitlement groups/ACL), `tenant` (multi-tenant partition), `assurance`
(auth-strength hint), and `source` (which adapter resolved it).

| Adapter | Profile | What it does | Where it lives |
| --- | --- | --- | --- |
| IAP-verified assertion | `gcp`, `platform` | Verifies the signed `x-goog-iap-jwt-assertion` against Google's IAP public keys; `subject` from `email`/`sub`, `tenant` from `hd`. | `adapters/gcp/iap_identity.py` |
| Local seeded personas | `local` | Offline dev/test identity via `X-Dev-Persona`, no IdP. | `adapters/local/identity.py` |
| On-prem enterprise IdP | `onprem` | Fail-fast `NotImplementedError` placeholder (never returns `ANONYMOUS`); the natural home for a JWKS/OIDC/SAML verifier. | `adapters/onprem/identity.py` |

Where authZ is enforced (defense-in-depth policy enforcement point): the edge (Cloud IAP)
authenticates at ingress, the `agent-guardrail-gateway` applies central policy, and this backend
re-validates and derives identity itself. Each layer assumes the others may be bypassed.

## 6. Config knobs

| Variable | Side | Purpose |
| --- | --- | --- |
| `MKT_CREATIVE_PROFILE` | backend | `local` \| `gcp` \| `platform` \| `onprem`. Selects the identity adapter (and the whole adapter set). No default: unset refuses the `local` relaxations rather than assuming them. |
| `MKT_CREATIVE_IAP_AUDIENCE` | backend | The IAP audience string (the exact structured resource path) the backend verifies against. Required in `gcp`/`platform`. |
| `MKT_CREATIVE_CORS_ORIGINS` | backend | Explicit origin allowlist for the cross-origin / standalone case. Never `"*"`; when unset the dev origins apply only under a deliberate `local` profile, otherwise the allowlist is empty. |
| `MKT_CREATIVE_FRAME_ANCESTORS` | backend | CSP `frame-ancestors` allowlist: parent origins permitted to iframe the UI. Defaults to `'self'` when unset; set and blank is refused at boot, never read as the default. |
| `MKT_CREATIVE_ALLOW_INSECURE_DEMO` | backend | The ONE opt-out from the loopback exposure bound. When the bound identity adapter does not verify the end user, a non-loopback peer gets 503; set this to exactly `1` to accept that exposure deliberately. `0`, `true`, blank and ` 1 ` all leave the guard on. |
| `NEXT_PUBLIC_API_BASE` | UI | Backend base URL the UI calls. Build-time. |
| `NEXT_PUBLIC_BASE_PATH` | UI | Sub-path the UI is mounted under (blank keeps standalone). Build-time. |
| `NEXT_PUBLIC_EMBED` | UI | Set to `1` to hide the UI's own chrome. Build-time. |
| `NEXT_PUBLIC_FRAME_ANCESTORS` | UI | CSP `frame-ancestors` for the console document itself, resolved in the same three states as the backend variable: unset keeps `'self'`, set and blank is refused at build/boot, a value is used as given. `X-Frame-Options` is added only for `'self'` and `'none'`. |
| `X-Dev-Persona` | request header | **Local profile only.** Selects a seeded dev persona; ignored in secure profiles. |

## 7. Checklists

**Client-side integration (same-origin embed):**

- [ ] Reverse-proxy route mapping `/studio/*` to the UI service and `/studio/api/*` to the backend.
- [ ] `<iframe src="/studio/">` on the host page in a sized container.
- [ ] IdP federated into IAP (Workforce Identity Federation) so users carry one session through.
- [ ] UI built with `NEXT_PUBLIC_BASE_PATH`, `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_EMBED=1`.

**Security:**

- [ ] **HTTPS everywhere** (the load balancer terminates TLS; IAP requires it).
- [ ] **IAP audience configured**: `MKT_CREATIVE_IAP_AUDIENCE` set in any IAP profile (the
      backend refuses to verify without it).
- [ ] **Framing locked down**: `MKT_CREATIVE_FRAME_ANCESTORS` set to the exact parent origin(s);
      `'self'` for standalone; never a wildcard. Never set it to a blank value to mean
      "default": the service refuses to boot on it.
- [ ] **Origins locked down**: same-origin proxy (no CORS) for the embedded shape; otherwise
      `MKT_CREATIVE_CORS_ORIGINS` is an explicit allowlist, never `"*"`.
- [ ] **No client-asserted identity trusted**: production uses `gcp`/`platform` (or an
      implemented `onprem`), never `local`.

## 8. Further layers (not in this slice)

The following harden the design further and are documented, not built here. They are
reference-implemented in the sibling repo `cdd-sow-research`, which is the pattern source:

- **Cross-origin embedding for hosts that cannot run a proxy or federate into IAP**: a versioned,
  SRI-pinned loader plus a web component, a versioned host-to-iframe `postMessage` contract, and
  a host-minted bearer token (RFC 8693 audience-scoped, in memory only) verified against the
  client IdP's JWKS by a new adapter on the same `IdentityPort` seam.
- **Launch-in-new-tab OIDC redirect login** (self-issued session cookie) for the simplest,
  most portable integration when top-level navigation is acceptable.
- **Per-hop OAuth2 token exchange (OBO) plus Workload Identity and mTLS** to the Hrz platform
  services, and step-up (acr/amr) for high-value actions.
- **Per-tenant framing/CORS/issuer policy resolved at request time**, a UI-side CSP on the
  framed document, and fail-closed tenant-partitioned retrieval.

See `cdd-sow-research/docs/embedding-and-identity.md` for the full treatment of these layers.

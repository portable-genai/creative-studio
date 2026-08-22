# Mkt3 Creative Studio: thin demo console

A minimal Next.js (App Router) console over the Mkt3 FastAPI backend. It posts a creative
brief and renders the cited `CreativeStudioResult`: each variant with its deterministic
brand / claim / policy / asset findings and the maker-checker "human review required" banner.

```bash
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8102 npm run dev   # then open http://localhost:3000
npm run build                                            # production build (CI builds this)
```

Set `NEXT_PUBLIC_API_BASE` to the Mkt3 API (default `http://localhost:8102`). The console owns
no business logic; the backend owns the engines and the citations.

## Source map

| Path | What it owns |
| --- | --- |
| `lib/csp.mjs` | THE Content-Security-Policy, built once. Also the three-state `frame-ancestors` resolution (mirroring `api/app.py`), the per-request nonce, and the build-time refusal of an un-hydratable configuration. |
| `proxy.ts` | The only place the policy is emitted, per request, on BOTH the request headers (where Next reads the nonce it stamps onto script tags) and the response headers (what the browser enforces). |
| `next.config.mjs` | Base path, and the two genuinely static headers (`nosniff`, `Referrer-Policy`). Deliberately emits NO CSP: a second policy would be intersected with the first and the stricter would win per directive. |
| `app/layout.tsx` | `export const dynamic = "force-dynamic"`, required by the nonce CSP rather than chosen for performance. |
| `scripts/assert-hydratable.mjs` | Starts the BUILT server and asserts the served document actually hydrates. |
| `tests/csp.test.mjs` | What a policy STRING can decide. Explicitly not sufficient on its own. |

## Gate

```bash
make ui-check     # from the repo root: lint, unit tests, build, then assert-hydratable
make ui-install   # npm ci, proving package-lock.json still resolves
```

`assert-hydratable` runs last and against the artefact the build just produced. It is the only
check that can see one failure mode that every other check misses: `script-src` without a nonce
blocks Next's inline hydration bootstrap, so React never attaches and every control becomes dead
markup, while the headers, the type-check, the build and every string assertion stay green. The
response header is byte-identical in the working and the broken case, so the check reads the
markup instead: every `<script>` tag must carry the nonce the response advertised.

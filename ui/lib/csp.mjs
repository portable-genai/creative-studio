// The console's Content-Security-Policy, in ONE module so it is built once and read everywhere.
//
// Living inline in `next.config.mjs`, emitted through the static `headers()` table, would carry
// a single directive: `frame-ancestors`. That is a clickjacking control and nothing
// else. There was no `default-src`, no `script-src`, no `object-src`, no `base-uri`, so the
// console shipped with no script, object or base-tag restriction at all.
//
// Adding `script-src 'self'` alone would NOT have fixed it, and this is the part that keeps
// catching people out: Next serves its hydration bootstrap as an INLINE `<script>` carrying the
// Flight payload, so a bare `'self'` blocks it, `__next_f` never fills, React never attaches and
// every control on the page becomes dead markup while the headers, the type-check, the build and
// every string test stay green. So `script-src` takes a PER-REQUEST nonce plus `'strict-dynamic'`,
// the nonce is minted in `proxy.ts`, and `next.config.mjs` no longer emits a
// `Content-Security-Policy` at all. Two layers both setting one would give the browser two
// policies to intersect, and the stricter wins per directive, which quietly reinstates the defect.
//
// The nonce path has a trap of its own: a STATICALLY prerendered route was built before the nonce
// existed, so nothing in its HTML carries the nonce, and `'strict-dynamic'` switches off the
// `'self'` fallback that had at least been loading the chunk scripts. That combination blocks
// strictly MORE than the unfixed policy did. `assertHydratableCsp` refuses that build, and
// `scripts/assert-hydratable.mjs` proves the served bytes by execution.

/**
 * Origin of the API base, when the console is deployed cross-origin from its service.
 *
 * A rooted path is the SAME-ORIGIN deployment, which is what a host portal mounting this console
 * under its own route sets. There is no second origin to name there, and `'self'` already permits
 * it, so "" is the correct answer rather than an error: refusing it made the console answer 500
 * behind the portal, which is a working configuration reported as a broken one.
 *
 * A protocol-relative value is still refused. It names a DIFFERENT host while looking rooted, so
 * treating it as same-origin would drop a genuinely cross-origin API out of `connect-src`, which
 * is the silent-drop this function exists to prevent.
 *
 * @param {Record<string, string | undefined>} env
 * @returns {string} an origin to add to `connect-src`, or "" when same-origin
 */
function apiOrigin(env) {
  const raw = (env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!raw) return "";
  if (raw.startsWith("//")) {
    throw new Error(`NEXT_PUBLIC_API_BASE must name its scheme, got: ${raw}`);
  }
  if (raw.startsWith("/")) return "";
  try {
    return new URL(raw).origin;
  } catch {
    throw new Error(
      `NEXT_PUBLIC_API_BASE must be an absolute URL or a rooted same-origin path, got: ${raw}`,
    );
  }
}

/** Raised when an embedding variable is set but names nothing. Mirrors the API's own refusal. */
export class ConfiguredEmptyError extends Error {}

/** Raised when an embedding variable names a wildcard instead of the origins it should allow. */
export class WildcardOriginError extends Error {}

/**
 * Exact tokens that must never be accepted as a framing ancestor.
 *
 * `'*'` is what a quoted Terraform variable or a YAML string renders. `*.*` is a host pattern
 * matching every name with a dot in it. `null` is the one that reads as harmless and is not: it
 * is not a wildcard by spelling and behaves as one, because a SANDBOXED iframe presents the
 * origin `null`, so a policy naming it hands framing rights to any page that can open one.
 */
const WILDCARD_TOKENS = new Set(["*", "'*'", "null", "*.*"]);

/**
 * True when an entry may not be a framing ancestor.
 *
 * Exact matching alone is not enough. `https://*.client.example` is in no token set, and CSP
 * honours a host-source wildcard: every subdomain may frame the console, including one an
 * attacker obtains by takeover or on a user-content subdomain. So ANY entry containing an
 * asterisk is refused, which turns away nothing a deployment could correctly hold, since a real
 * origin never contains the character.
 *
 * @param {string} entry
 * @returns {boolean}
 */
function isWildcard(entry) {
  return WILDCARD_TOKENS.has(entry) || entry.includes("*");
}

/**
 * Refuse an allowlist that names a wildcard, before the value can reach a response header.
 *
 * `src/creative_studio/api/app.py::_refuse_wildcard` does this for the API surface, and it was the only half that
 * did. There are two `frame-ancestors` emitters, and the one a browser consults before framing
 * this console is the header on the DOCUMENT, which Next serves under the policy this module
 * builds. This resolver passed its configured value straight through, so a deployment whose
 * variable rendered a wildcard refused to start the API and still served a document any origin
 * could frame. The half that was closed is not the half that governs.
 *
 * Tokens are split on commas as well as whitespace. CSP source lists are space separated, so a
 * comma form never names a valid origin anyway; splitting on it here means
 * `*,https://portal.example` is seen as the wildcard it contains rather than as one opaque token
 * that merely fails to equal `*`.
 *
 * @param {string} raw the configured value, before it is normalised
 * @param {string} envName the variable it came from, for the message
 * @throws {WildcardOriginError}
 */
function refuseWildcards(raw, envName) {
  for (const piece of String(raw).split(/[\s,]+/)) {
    const entry = piece.trim();
    if (entry && isWildcard(entry)) {
      throw new WildcardOriginError(
        `${envName} contains ${JSON.stringify(entry)}, which lets ANY origin frame this ` +
          "console: a wildcard frame-ancestors is the clickjacking control switched off, not " +
          `configured. Name the exact parent origins that may frame it, or unset ${envName} to ` +
          "keep the restrictive default.",
      );
    }
  }
}

/**
 * Who may frame this console, resolved in THREE states, matching the API resolver in
 * `src/creative_studio/api/app.py::_frame_ancestors` exactly.
 *
 * * unset: no intent was expressed, so the restrictive `'self'` default stands.
 * * set and blank (or whitespace only): an intent WAS expressed and it names nothing. REFUSED.
 *   A `||` fallback alone lets a whitespace-only value through as truthy and renders an empty
 *   `frame-ancestors` directive, which browsers discard as a parse error; the legacy
 *   `X-Frame-Options` branch below is skipped too, so the clickjacking control vanishes without
 *   a trace in the one deployment shape that looks configured.
 * * set with a value: used as given.
 *
 * The two halves of the embedding posture have to agree, so this deliberately does NOT use the
 * hrz reference's two-state `env.X || "'self'"`, and does not import the hex-service-template's
 * `embed-policy.mjs` (that module reads `UI_FRAME_ANCESTORS` / `UI_TENANT_ORIGINS`, names this
 * repo does not use, and resolves a naming-nothing value to `'none'` where this API refuses).
 *
 * @param {Record<string, string | undefined>} env
 * @returns {string}
 */
export function frameAncestors(env) {
  const raw = env.NEXT_PUBLIC_FRAME_ANCESTORS;
  if (raw === undefined || raw === null) return "'self'";
  const value = String(raw).trim();
  if (value === "") {
    throw new ConfiguredEmptyError(
      "NEXT_PUBLIC_FRAME_ANCESTORS is set but empty. An empty CSP frame-ancestors directive is " +
        "discarded by browsers, leaving the console with no clickjacking protection. Unset it to " +
        "keep the 'self' default, or name the parent origins that may frame it.",
    );
  }
  refuseWildcards(value, "NEXT_PUBLIC_FRAME_ANCESTORS");
  return value;
}

/**
 * The pre-CSP `X-Frame-Options` spelling of a framing policy, or "" when it has none.
 *
 * A NAMED allowlist has no `X-Frame-Options` equivalent, so nothing is sent there rather than a
 * `SAMEORIGIN` that would contradict the CSP in an older agent.
 *
 * @param {string} ancestors the resolved `frame-ancestors` value
 * @returns {string}
 */
export function frameOptions(ancestors) {
  if (ancestors === "'self'") return "SAMEORIGIN";
  if (ancestors === "'none'") return "DENY";
  return "";
}

/**
 * The full default-deny policy.
 *
 * `style-src` carries `'unsafe-inline'` because the Next runtime injects critical CSS and there
 * is no nonce path for it. `script-src` does NOT: it takes the per-request nonce plus
 * `'strict-dynamic'`, so the nonced bootstrap may load its own chunks and nothing else may run.
 * Passing no nonce yields the strict `'self'` form, which is correct for any response that is not
 * a Next-rendered document and wrong for one that is.
 *
 * @param {Record<string, string | undefined>} env
 * @param {string} [nonce]
 * @returns {string}
 */
export function contentSecurityPolicy(env, nonce) {
  const connectSrc = ["'self'", apiOrigin(env)].filter(Boolean).join(" ");
  const scriptSrc = nonce
    ? `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`
    : "script-src 'self'";
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    `frame-ancestors ${frameAncestors(env)}`,
  ].join("; ");
}

/** A fresh per-request nonce. Base64 of 16 random bytes from the Web Crypto global. */
export function generateNonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/** Raised when the nonce policy and the rendering mode disagree, which serves un-hydratable HTML. */
export class UnhydratableCspError extends Error {}

/**
 * Refuse a build whose CSP mints a nonce the rendered HTML can never carry.
 *
 * Next can only stamp a per-request nonce onto the scripts of a DYNAMICALLY rendered route. A
 * statically prerendered page was built before the nonce existed, so it emits bare script tags
 * while the header advertises a nonce, and because `'strict-dynamic'` switches off the `'self'`
 * fallback, that combination blocks strictly MORE than the unfixed policy did. The failure is
 * invisible to every check that does not execute the page, so it is refused at build time.
 *
 * No I/O happens here: the caller passes the source as a string, which keeps this module
 * importable from the edge-runtime proxy.
 *
 * @param {string} layoutSource contents of `app/layout.tsx`
 * @throws {UnhydratableCspError}
 */
export function assertHydratableCsp(layoutSource) {
  if (!/export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/.test(layoutSource)) {
    throw new UnhydratableCspError(
      'app/layout.tsx must set `export const dynamic = "force-dynamic"`. The CSP mints a ' +
        "per-request nonce, and Next can only stamp it onto script tags for a dynamically " +
        "rendered route. Statically prerendered HTML was built before the nonce existed, so " +
        "every script is blocked and the page never hydrates.",
    );
  }
}

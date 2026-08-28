// What a STRING can decide about the console's CSP, and nothing more.
//
// These tests are NOT sufficient, and saying so is the point. Before the nonce fix the policy
// string was exactly what its author intended and every string-level assertion about it passed;
// what shipped was still dead markup, because `script-src` blocked Next's inline hydration
// bootstrap and no test executed the page. The header is byte-identical in the working case and
// in the statically-prerendered broken case, so a header assertion cannot tell them apart.
//
// `scripts/assert-hydratable.mjs` is the check that can: it starts the BUILT server, fetches the
// served document, and asserts every script tag carries the served nonce. These tests cover the
// decisions the string makes on its own (directive completeness, the three-state frame-ancestors,
// the connect-src widening), so that a mistake there is caught in milliseconds rather than after
// a production build.

import assert from "node:assert/strict";
import test from "node:test";

import {
  ConfiguredEmptyError,
  UnhydratableCspError,
  WildcardOriginError,
  assertHydratableCsp,
  contentSecurityPolicy,
  frameAncestors,
  frameOptions,
  generateNonce,
} from "../lib/csp.mjs";

/** Parse a policy string into directive name -> value. */
function directives(csp) {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...value] = part.split(/\s+/);
        return [name.toLowerCase(), value.join(" ")];
      }),
  );
}

test("the policy carries every directive the console depends on", () => {
  const parsed = directives(contentSecurityPolicy({}, "n0nce"));
  for (const name of [
    "default-src",
    "base-uri",
    "form-action",
    "object-src",
    "script-src",
    "style-src",
    "img-src",
    "font-src",
    "connect-src",
    "frame-ancestors",
  ]) {
    assert.ok(parsed.has(name), `missing ${name}`);
  }
  assert.equal(parsed.get("object-src"), "'none'");
  assert.equal(parsed.get("base-uri"), "'self'");
});

test("no directive is ever emitted empty, in any reachable env shape", () => {
  for (const env of [{}, { NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.example" }]) {
    for (const nonce of [undefined, "n0nce"]) {
      for (const [name, value] of directives(contentSecurityPolicy(env, nonce))) {
        assert.notEqual(value, "", `${name} is empty, which browsers discard as a parse error`);
      }
    }
  }
});

test("script-src gets the nonce and strict-dynamic only when a nonce is passed", () => {
  assert.equal(
    directives(contentSecurityPolicy({}, "abc123")).get("script-src"),
    "'self' 'nonce-abc123' 'strict-dynamic'",
  );
  assert.equal(directives(contentSecurityPolicy({})).get("script-src"), "'self'");
});

test("frame-ancestors resolves in three states, matching the API resolver", () => {
  assert.equal(frameAncestors({}), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.example" }), "https://portal.example");
  for (const raw of ["", "   "]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: raw }),
      ConfiguredEmptyError,
      `NEXT_PUBLIC_FRAME_ANCESTORS=${JSON.stringify(raw)} must refuse, not fall back`,
    );
  }
});

test("X-Frame-Options is sent only for the two policies it can express", () => {
  assert.equal(frameOptions("'self'"), "SAMEORIGIN");
  assert.equal(frameOptions("'none'"), "DENY");
  assert.equal(frameOptions("https://portal.example"), "");
});

test("connect-src widens to the API ORIGIN, not the full URL", () => {
  const parsed = directives(
    contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "https://api.example:8443/v1/creative" }),
  );
  assert.equal(parsed.get("connect-src"), "'self' https://api.example:8443");
});

test("a rooted API base stays same-origin rather than being refused", () => {
  // A host portal mounting this console under its own route sets exactly this. Same-origin is
  // already covered by 'self', so it widens nothing, and refusing it answered 500 on a working
  // deployment. What must never happen is the value being dropped while it names a real origin,
  // which is the case below.
  assert.doesNotThrow(() => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "/apps/x/api" }));
});

test("a protocol-relative API base is refused rather than read as same-origin", () => {
  assert.throws(
    () => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "//api.example/v1" }),
    /must name its scheme/,
  );
});

test("an API base that is neither absolute nor rooted is refused", () => {
  assert.throws(
    () => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "api.example/v1" }),
    /NEXT_PUBLIC_API_BASE/,
  );
});

test("nonces are unique and base64", () => {
  const seen = new Set();
  for (let i = 0; i < 50; i += 1) {
    const nonce = generateNonce();
    assert.match(nonce, /^[A-Za-z0-9+/]+={0,2}$/);
    seen.add(nonce);
  }
  assert.equal(seen.size, 50);
});

test("a layout without force-dynamic is refused, because its HTML cannot carry the nonce", () => {
  assert.throws(() => assertHydratableCsp("export default function L() {}"), UnhydratableCspError);
  assert.doesNotThrow(() =>
    assertHydratableCsp('export const dynamic = "force-dynamic";\nexport default function L() {}'),
  );
});

test("a wildcard frame-ancestors is refused in every spelling a config can render", () => {
  // The FastAPI half already refuses these. This is the OTHER emitter, and it is the one a
  // browser honours for the document, so closing only the service side left the console
  // framable by any origin while every check stayed green.
  for (const wildcard of ["*", "'*'", "null", "*.*"]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }),
      WildcardOriginError,
      `${JSON.stringify(wildcard)} must be refused, not passed through to the header`,
    );
  }
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example *" }),
    WildcardOriginError,
    "a wildcard standing beside named origins is still a wildcard",
  );
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "*,https://portal.client.example" }),
    WildcardOriginError,
    "a comma is not CSP list syntax, so a comma-joined wildcard must still be seen",
  );
  // A HOST-SOURCE wildcard is the spelling an exact-token set misses, and CSP honours it: every
  // subdomain may frame the console, including one an attacker takes over or registers on a
  // user-content domain. A real origin never contains an asterisk, so refusing the character
  // outright turns away nothing a deployment could correctly hold.
  for (const hostSource of [
    "https://*.client.example",
    "*.client.example",
    "https://*",
    "https://portal.client.example https://*.evil.example",
  ]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: hostSource }),
      WildcardOriginError,
      `${JSON.stringify(hostSource)} is a host-source wildcard and must be refused`,
    );
  }
});

test("the policy the proxy actually serves refuses a wildcard too", () => {
  // `contentSecurityPolicy` is what `proxy.ts` puts on the document response. Refusing inside
  // the resolver alone would be theatre if this path could still build a policy around it.
  for (const wildcard of ["*", "'*'", "null", "*.*", "https://*.client.example"]) {
    assert.throws(
      () => contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }, "n0nce"),
      WildcardOriginError,
      `the served document policy must not carry frame-ancestors ${wildcard}`,
    );
  }
});

test("a legitimate named allowlist is unaffected by the wildcard refusal", () => {
  // A refusal that also refuses valid input is an outage, not a control.
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }),
    "https://portal.client.example",
  );
  assert.equal(
    frameAncestors({
      NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example https://intranet.client.example",
    }),
    "https://portal.client.example https://intranet.client.example",
  );
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'self'" }), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'none'" }), "'none'");
  assert.match(
    contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }, "n"),
    /frame-ancestors https:\/\/portal\.client\.example/,
  );
});

test("the unset and emptied states are exactly what they were before wildcards were refused", () => {
  // Pinned so a later edit cannot drift them. THIS repo REFUSES an emptied value rather than
  // mapping it to 'none', mirroring its own FastAPI half; the wildcard case is an addition to
  // that behaviour, never a replacement for it.
  assert.equal(frameAncestors({}), "'self'");
  for (const blank of ["", "   ", "\t", "\n", " \t\n "]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: blank }),
      ConfiguredEmptyError,
      `blank value ${JSON.stringify(blank)} must still be refused as configured-empty`,
    );
  }
});

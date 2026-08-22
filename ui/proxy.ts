// The one place the console's security headers are emitted, per request.
//
// `proxy.ts` is the Next 16 name for what was `middleware.ts`. It runs on every document and
// asset request, which is the only layer that can mint a PER-REQUEST value, and a script nonce is
// exactly that. `next.config.mjs` deliberately emits no `Content-Security-Policy` at all: two
// layers both setting one leaves the browser intersecting them, the stricter wins per directive,
// and the nonce would be silently overridden by the static copy.
//
// Both header sets below are required, and they do different jobs:
//
//   * The REQUEST header is where Next reads the nonce it stamps onto every `<script>` tag it
//     emits. Setting it alone proves nothing to a browser.
//   * The RESPONSE header is what the browser actually enforces. Setting it alone blocks the very
//     scripts the nonce was added to allow.
//
// The request header name must be exactly `Content-Security-Policy`; Next looks for that name.

import { type NextRequest, NextResponse } from "next/server";

import { contentSecurityPolicy, frameAncestors, frameOptions, generateNonce } from "./lib/csp.mjs";

export function proxy(request: NextRequest) {
  const nonce = generateNonce();
  const csp = contentSecurityPolicy(process.env, nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  // Only for the two framing policies X-Frame-Options can express. A named allowlist has no
  // spelling there, so nothing is sent rather than a SAMEORIGIN that contradicts the CSP.
  const legacy = frameOptions(frameAncestors(process.env));
  if (legacy) response.headers.set("X-Frame-Options", legacy);

  return response;
}

export const config = { matcher: "/:path*" };

/** @type {import('next').NextConfig} */
// NEXT_PUBLIC_BASE_PATH mounts the UI (and its assets) under a reverse-proxy sub-path
// (for example /agent) for same-origin embedding; blank keeps the standalone deployment
// unchanged.
//
// The Content-Security-Policy is NOT emitted here. It lives in `lib/csp.mjs` and is set once, per
// request, by `proxy.ts`, because a script nonce is a per-request value and this static table
// cannot express one. Emitting a policy here as well would give the browser two policies to
// intersect, and the stricter wins per directive, which is exactly how the nonce would be
// silently dropped. Only headers that are genuinely static belong in this table.
//
// The module-scope refusal below runs on `next build` AND `next start`, so a console whose CSP
// mints a nonce its statically prerendered HTML could never carry does not come up at all.
import { readFileSync } from "node:fs";

import { assertHydratableCsp, frameAncestors } from "./lib/csp.mjs";

assertHydratableCsp(readFileSync(new URL("./app/layout.tsx", import.meta.url), "utf8"));
// Resolved for the side effect of refusing a NEXT_PUBLIC_FRAME_ANCESTORS that is set but names
// nothing, at build/boot rather than on some later request.
frameAncestors(process.env);

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;

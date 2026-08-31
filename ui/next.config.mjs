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
  // `next dev` writes AGENTS.md and CLAUDE.md into this directory unless this is false; the
  // writer is node_modules/next/dist/server/lib/generate-agent-files.js. This repo's working
  // agreement is the AGENTS.md at its root and there is no tool-specific alias of it, so a
  // second one here is a second agreement to keep in step and CLAUDE.md is precisely the alias
  // the convention forbids. The generated prose also carries an em-dash, which the catalog's
  // house style forbids in shipped markdown. tests/unit/test_ui_agent_documents.py fails the
  // gate if this line goes away or if either file turns up on disk anyway.
  agentRules: false,
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

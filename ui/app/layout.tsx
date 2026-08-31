import type { Metadata } from "next";
import { ProvenanceBanner } from "./ProvenanceBanner";
import "./globals.css";

// Required by the nonce CSP, not a performance preference. `proxy.ts` mints a per-request script
// nonce, and Next can only stamp it onto the script tags of a DYNAMICALLY rendered route. A
// statically prerendered page was built before the nonce existed, so nothing carries it, and
// `'strict-dynamic'` switches off the `'self'` fallback that had at least been loading the chunks:
// the half-configured state blocks strictly more than no policy at all. `next.config.mjs` refuses
// to build without this line; `ui/scripts/assert-hydratable.mjs` proves the served bytes.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Brand-Safe Creative Studio",
  description:
    "Gemini copy + Imagen image with deterministic brand, advertising-claim, per-market policy and asset-spec validation, generic across banking and online retail and the JP/AU/SG markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // EMBED mode: the host page owns the chrome, so drop our own page background/framing
  // and let the embedded surface fill the host container.
  const embed = process.env.NEXT_PUBLIC_EMBED === "1";
  return (
    <html lang="en">
      <body className={embed ? "" : "min-h-screen"}>
        <ProvenanceBanner />
        {children}
      </body>
    </html>
  );
}

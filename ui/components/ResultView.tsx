import type { CreativeStudioResult, VariantReview } from "@/lib/types";
import { CitationList } from "./CitationList";

const MARKET_LABEL: Record<string, string> = {
  JP: "Japan",
  AU: "Australia",
  SG: "Singapore",
};
const VERTICAL_LABEL: Record<string, string> = {
  banking: "Banking",
  online_retail: "Online retail",
};
const STATUS_COLOR: Record<string, string> = {
  pass: "bg-emerald-100 text-emerald-700",
  warn: "bg-amber-100 text-amber-800",
  fail: "bg-red-100 text-red-700",
};
const SEV_COLOR: Record<string, string> = {
  info: "bg-ink-100 text-ink-600",
  low: "bg-ink-100 text-ink-600",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4 rounded-xl border border-ink-200 bg-white shadow-panel">
      <h2 className="border-b border-ink-100 px-4 py-2.5 text-[13px] font-semibold text-ink-800">
        {title}
      </h2>
      <div className="p-4">{children}</div>
    </section>
  );
}

function VariantCard({ review }: { review: VariantReview }) {
  const v = review.variant;
  return (
    <div className="mb-3 rounded-lg border border-ink-200 p-3 last:mb-0">
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-bold ${
            STATUS_COLOR[review.status] ?? STATUS_COLOR.warn
          }`}
        >
          {review.status.toUpperCase()}
        </span>
        <span className="font-mono text-[11px] text-ink-400">{v.id}</span>
      </div>
      <div className="text-sm font-semibold">{v.headline}</div>
      <div className="text-sm text-ink-600">{v.body}</div>
      {v.cta ? <div className="mt-1 text-xs font-semibold text-brand-700">{v.cta}</div> : null}
      {v.image ? (
        <div className="mt-1 text-[11px] text-ink-400">
          image {v.image.uri} ({v.image.aspect_ratio})
        </div>
      ) : null}
      {review.brand.findings
        .concat(review.claim.findings, review.policy.findings, review.asset.findings)
        .length === 0 ? (
        <div className="mt-2 text-xs text-emerald-700">No issues found.</div>
      ) : (
        <div className="mt-2 flex flex-col gap-1.5">
          {review.brand.findings
            .concat(review.claim.findings, review.policy.findings, review.asset.findings)
            .map((f, i) => (
              <div key={i} className="border-l-2 border-ink-200 pl-2.5">
                <div className="flex items-baseline gap-2">
                  <span
                    className={`rounded px-1.5 text-[10px] font-bold ${
                      SEV_COLOR[f.severity] ?? SEV_COLOR.medium
                    }`}
                  >
                    {f.severity}
                  </span>
                  <span className="text-xs text-ink-700">{f.message}</span>
                </div>
                <CitationList citations={f.citations} />
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

export function ResultView({ result }: { result: CreativeStudioResult }) {
  const b = result.brief;
  const approved = result.reviews.filter((r) => r.approved).length;
  return (
    <div>
      <h1 className="text-lg font-semibold">Creative — {b.topic}</h1>
      <p className="mb-4 text-[13px] text-ink-500">
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {MARKET_LABEL[b.market] ?? b.market}
        </span>
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {VERTICAL_LABEL[b.vertical] ?? b.vertical}
        </span>
        <span className="mr-1.5 inline-block rounded-full border border-ink-200 bg-ink-50 px-2.5 py-0.5 text-[11px] font-semibold text-ink-600">
          {b.channel}
        </span>
        id <b className="text-ink-800">{result.id}</b>
      </p>

      {result.requires_human_review ? (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          HUMAN REVIEW REQUIRED — maker-checker gate. Do not publish this creative until a
          qualified brand / compliance reviewer signs off.
        </div>
      ) : null}

      <Panel title="Summary">
        <p className="leading-relaxed">{result.summary}</p>
        <p className="mt-2 text-xs text-ink-500">
          {approved}/{result.reviews.length} variant(s) passed every deterministic check.
        </p>
      </Panel>

      <Panel title="Variants and deterministic checks">
        {result.reviews.map((review, i) => (
          <VariantCard key={i} review={review} />
        ))}
      </Panel>
    </div>
  );
}

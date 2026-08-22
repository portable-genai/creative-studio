import type { Citation } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  brand_guideline: "BRAND",
  ad_policy: "POLICY",
  claim_rule: "CLAIM",
  asset_spec: "ASSET",
  internal: "INTERNAL",
  other: "SRC",
};

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations || citations.length === 0) {
    return null;
  }
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {citations.map((c, i) => (
        <div
          key={`${c.source_id}-${i}`}
          className="flex items-baseline gap-2 rounded-md border border-ink-200 bg-ink-50 px-2.5 py-1"
        >
          <span className="rounded border border-brand-100 bg-brand-50 px-1.5 font-mono text-[10px] font-semibold text-brand-700">
            {SOURCE_LABEL[c.source_type] ?? "SRC"}
          </span>
          <span className="text-xs text-ink-700">{c.title}</span>
          <span className="ml-auto font-mono text-[10px] text-ink-500">{c.source_id}</span>
        </div>
      ))}
    </div>
  );
}

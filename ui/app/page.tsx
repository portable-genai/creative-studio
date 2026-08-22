"use client";

import { useEffect, useState } from "react";
import { ResultView } from "@/components/ResultView";
import { api, API_BASE, ApiError, setDevPersona } from "@/lib/api";
import type {
  Channel,
  CreativeStudioResult,
  Health,
  Market,
  Persona,
  Vertical,
} from "@/lib/types";

const MARKETS: { value: Market; label: string }[] = [
  { value: "JP", label: "Japan (asia-northeast1)" },
  { value: "AU", label: "Australia (australia-southeast1)" },
  { value: "SG", label: "Singapore (asia-southeast1)" },
];
const VERTICALS: { value: Vertical; label: string }[] = [
  { value: "banking", label: "Banking" },
  { value: "online_retail", label: "Online retail" },
];
const CHANNELS: { value: Channel; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "sms", label: "SMS" },
  { value: "push", label: "Push" },
  { value: "display", label: "Display banner" },
  { value: "search", label: "Search ad" },
  { value: "social", label: "Social" },
  { value: "web", label: "Web" },
];

export default function Page() {
  const [topic, setTopic] = useState("high-yield savings push");
  const [market, setMarket] = useState<Market>("SG");
  const [vertical, setVertical] = useState<Vertical>("banking");
  const [channel, setChannel] = useState<Channel>("email");
  const [offer, setOffer] = useState("4.10% p.a.");
  const [withImage, setWithImage] = useState(false);
  const [result, setResult] = useState<CreativeStudioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await api.healthz();
      if (cancelled) return;
      setHealth(status);
      // The persona picker is dev-only: it only appears under the local profile, where
      // the backend has no IdP and resolves identity from the X-Dev-Persona header.
      if (!status || status.profile !== "local") return;
      try {
        const list = await api.listPersonas();
        if (cancelled || list.length === 0) return;
        setPersonas(list);
        setSelectedPersona(list[0].id);
        setDevPersona(list[0].id);
      } catch {
        // Persona picker is a convenience; ignore lookup failures.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onPersonaChange(id: string) {
    setSelectedPersona(id);
    setDevPersona(id);
  }

  async function onGenerate() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.generateCreative({
        topic,
        market,
        vertical,
        channel,
        product: topic,
        offer,
        with_image: withImage,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-6xl gap-6 p-6">
      <aside className="w-80 shrink-0">
        <h1 className="text-base font-semibold">D3 Brand-Safe Creative Studio</h1>
        <p className="mb-4 text-xs text-ink-500">
          Generate creative and prove it is brand-safe, generic across banking and online
          retail and the JP/AU/SG markets.
        </p>

        <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
          <label className="mb-1 block text-xs font-semibold text-ink-600">Campaign theme</label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />

          <label className="mb-1 block text-xs font-semibold text-ink-600">Offer</label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={offer}
            onChange={(e) => setOffer(e.target.value)}
            placeholder="e.g. 4.10% p.a. / 20% off"
          />

          <label className="mb-1 block text-xs font-semibold text-ink-600">Market</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
          >
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">Vertical</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={vertical}
            onChange={(e) => setVertical(e.target.value as Vertical)}
          >
            {VERTICALS.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">Channel</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={channel}
            onChange={(e) => setChannel(e.target.value as Channel)}
          >
            {CHANNELS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>

          <label className="mb-3 flex items-center gap-2 text-xs font-semibold text-ink-600">
            <input
              type="checkbox"
              checked={withImage}
              onChange={(e) => setWithImage(e.target.checked)}
            />
            Generate an image asset (Imagen)
          </label>

          <button
            onClick={onGenerate}
            disabled={loading || !topic.trim()}
            className="w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {loading ? "Generating…" : "Generate brand-safe creative"}
          </button>
        </div>

        <div className="mt-3 rounded-xl border border-ink-200 bg-white p-3 text-xs text-ink-500 shadow-panel">
          <div>
            API <span className="font-mono">{API_BASE}</span>
          </div>
          {health ? (
            <div className="mt-1">
              profile <b className="text-ink-700">{health.profile}</b> · status{" "}
              <b className="text-ink-700">{health.status}</b>
            </div>
          ) : (
            <div className="mt-1 text-amber-700">backend not reachable (start the API)</div>
          )}
        </div>

        {personas.length > 0 ? (
          <div className="mt-3 rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
            <label className="mb-1 block text-xs font-semibold text-ink-600">
              Demo identity
            </label>
            <select
              className="w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
              value={selectedPersona}
              onChange={(e) => onPersonaChange(e.target.value)}
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.subject} · {p.tenant}
                </option>
              ))}
            </select>
            <p className="mt-2 text-[11px] text-ink-400">
              Local profile only: the backend has no IdP, so it resolves this persona from
              the X-Dev-Persona header. Ignored in secure profiles.
            </p>
          </div>
        ) : null}
      </aside>

      <section className="min-w-0 flex-1">
        {error ? (
          <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        {!result && !error ? (
          <div className="rounded-xl border border-dashed border-ink-200 bg-white p-10 text-center text-sm text-ink-400">
            Configure a theme, market, vertical and channel, then generate brand-safe
            creative.
          </div>
        ) : null}
        {result ? <ResultView result={result} /> : null}
      </section>
    </main>
  );
}

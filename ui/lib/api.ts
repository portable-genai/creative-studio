/**
 * Typed fetch client for the D3 Brand-Safe Creative Studio FastAPI backend.
 *
 * Routes:
 *   POST /v1/creative  -> CreativeStudioResult
 *   POST /v1/review    -> VariantReview
 *   GET  /healthz      -> Health
 *   GET  /v1/personas  -> seeded dev personas (local profile only)
 *
 * The API base is read from NEXT_PUBLIC_API_BASE (default http://localhost:8102, the D3
 * API port). All calls are thin: the backend owns the business logic and the citations.
 *
 * Identity is resolved server-side. In LOCAL mode the backend picks a seeded persona from
 * the X-Dev-Persona header (attached only when a persona is selected). In secure profiles
 * that header is ignored: identity comes from an IAP assertion the platform injects, so the
 * request body never carries an actor.
 */

import type {
  Channel,
  CreativeStudioResult,
  Health,
  Market,
  Persona,
  Vertical,
} from "./types";
import { ConfiguredEmptyError, readEnvValue } from "./env-setting.mjs";

// The API base is resolved in THREE states, not two.
//
// Reading `process.env.NEXT_PUBLIC_API_BASE || "<loopback default>"` hands a
// variable an operator DELIBERATELY EMPTIED the loopback default. That is a widening: the
// console then talks to a local API instead of the configured one, and `connect-src` is built
// from the same value, so the emptied deployment is byte-identical to one that never configured
// the variable at all. Next inlines NEXT_PUBLIC_* AT BUILD TIME, so the wrong value is frozen
// into the bundle and cannot be corrected by fixing the environment at start-up.
//
// Unset keeps the documented loopback default, which is what a laptop wants. Set-and-empty
// refuses, because an emptied value names nothing and the default is the more permissive branch.
const DEFAULT_API_BASE = "http://localhost:8102";
// The literal member expression is required: a bundler substitutes the public value
// only where it sees exactly this, and handing it `process.env` leaves the browser
// reading {} and silently taking the hard-coded loopback default.
const API_BASE_SETTING = readEnvValue(
  "NEXT_PUBLIC_API_BASE",
  process.env.NEXT_PUBLIC_API_BASE,
);
if (API_BASE_SETTING.isConfiguredEmpty) {
  throw new ConfiguredEmptyError(
    "NEXT_PUBLIC_API_BASE is set to an empty value. An emptied variable names nothing, " +
      "so it cannot inherit the unset default (" + DEFAULT_API_BASE + "), which points this " +
      "console at a loopback API and widens connect-src to match. Unset it to take that " +
      "default deliberately, or give it the API origin this deployment should call.",
  );
}
export const API_BASE = (API_BASE_SETTING.hasValue ? API_BASE_SETTING.value : DEFAULT_API_BASE).replace(
  /\/+$/,
  "",
);

// Dev-only identity selection. In LOCAL mode the backend resolves identity from the
// X-Dev-Persona header; in secure profiles this is ignored (identity comes from the
// IAP assertion the platform injects). Module-level so every call sees the same choice.
let devPersona = "";

export function setDevPersona(id: string): void {
  devPersona = id;
}

export function getDevPersona(): string {
  return devPersona;
}

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface CreativeBody {
  topic: string;
  market: Market;
  vertical: Vertical;
  channel: Channel;
  product?: string;
  offer?: string;
  n_variants?: number;
  with_image?: boolean;
}

function requestHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (devPersona) headers["X-Dev-Persona"] = devPersona;
  return headers;
}

async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = (parsed && (parsed.detail || parsed.message)) || text;
    } catch {
      /* keep raw text */
    }
    throw new ApiError(
      `${res.status} ${res.statusText}: ${detail || "request failed"}`,
      res.status,
      text,
    );
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("Malformed JSON in response", res.status, text);
  }
}

export async function generateCreative(
  body: CreativeBody,
  signal?: AbortSignal,
): Promise<CreativeStudioResult> {
  const res = await fetch(`${API_BASE}/v1/creative`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(body),
    signal,
  });
  return (await parseJsonOrThrow(res)) as CreativeStudioResult;
}

export async function healthz(signal?: AbortSignal): Promise<Health | null> {
  try {
    const res = await fetch(`${API_BASE}/healthz`, {
      method: "GET",
      headers: requestHeaders(),
      signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export async function listPersonas(signal?: AbortSignal): Promise<Persona[]> {
  const res = await fetch(`${API_BASE}/v1/personas`, {
    method: "GET",
    headers: requestHeaders(),
    signal,
  });
  return (await parseJsonOrThrow(res)) as Persona[];
}

export const api = { generateCreative, healthz, listPersonas };

/**
 * Domain shapes mirrored from the D3 FastAPI backend (the JSON shape of a cited
 * CreativeStudioResult / VariantReview produced by `to_jsonable`).
 */

export type Market = "JP" | "AU" | "SG";
export type Vertical = "banking" | "online_retail";
export type Channel =
  | "email"
  | "sms"
  | "push"
  | "display"
  | "search"
  | "social"
  | "web";
export type CheckStatus = "pass" | "warn" | "fail";

export interface Citation {
  source_id: string;
  source_type: string;
  title: string;
  url?: string;
  page?: number | null;
  snippet?: string;
}

export interface Finding {
  rule_id: string;
  severity: string;
  message: string;
  span?: string;
  suggestion?: string;
  citations: Citation[];
}

export interface GeneratedImage {
  prompt: string;
  width: number;
  height: number;
  aspect_ratio: string;
  uri: string;
  alt_text: string;
}

export interface Variant {
  id: string;
  headline: string;
  body: string;
  cta?: string;
  channel: Channel;
  image?: GeneratedImage | null;
  rationale?: string;
}

export interface Check {
  status: CheckStatus;
  failed: boolean;
  findings: Finding[];
}

export interface VariantReview {
  variant: Variant;
  brand: Check;
  claim: Check;
  policy: Check;
  asset: Check;
  status: CheckStatus;
  approved: boolean;
}

export interface CreativeBrief {
  topic: string;
  market: Market;
  vertical: Vertical;
  channel: Channel;
  product?: string;
  offer?: string;
}

export interface CreativeStudioResult {
  id: string;
  brief: CreativeBrief;
  reviews: VariantReview[];
  summary: string;
  citations: Citation[];
  requires_human_review: boolean;
}

export interface Health {
  status: string;
  profile: string;
  market: string;
  vertical: string;
}

// A seeded dev persona (local profile only). Used by the "Demo identity" picker to
// exercise per-user authorization offline; the chosen id is sent as X-Dev-Persona.
export interface Persona {
  id: string;
  subject: string;
  tenant: string;
  principals: string;
}

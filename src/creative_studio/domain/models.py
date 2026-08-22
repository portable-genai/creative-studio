"""Domain models for the Brand-Safe Creative and Content Studio (D3).

This module is the heart of the hexagon. It has **no dependency on Google Cloud,
ADK, FastAPI, or any framework** (only the Python standard library). Every adapter
(GCP, remote-platform, or on-prem placeholder) speaks in terms of these types, which
is what lets the managed-service stack (Gemini for copy, Imagen for image) be swapped
for an on-premise one without touching domain logic (no vendor lock-in, ports and
adapters).

D3 is deliberately **generic marketing creative**, not a bank-specific tool:

* ``Vertical`` is a configurable enum (banking, online retail), so the same engines
  validate a savings-account ad and an e-commerce sale ad.
* ``Market`` is a configurable enum (JP, AU, SG) carrying its residency region and
  locales, so JP, AU and SG are first-class config and seed, never hard-coded.

The deterministic engines are the heart of the system: brand-guideline validation,
advertising-claim validation, per-market and per-vertical policy validation, variant
dedupe, and asset-spec checks. The LLM only generates copy and variant ideas; every
claim that leaves the system carries a :class:`Citation` (to the brand rule or policy
clause it was checked against) and every consequential aggregate sets
``requires_human_review``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agent_eval_kit.report import EvalMetricResult as EvalMetricResult
from agent_eval_kit.report import EvalReport as EvalReport
from hex_service_kit import StrEnum
from hex_service_kit.observability import TokenUsage

from .kernel import ThinkingLevel

# Three value types this module used to DECLARE now come from the commons and are re-exported
# here, so every existing `from ...domain.models import TokenUsage` keeps working while there is
# exactly one definition in the fleet to change. Sixteen repositories had hand-copied them and
# drifted; a dataclass copied into N repos is N dataclasses, and only one of them gets fixed when
# a defect is found. See the comment blocks below, where each one lives.
#
# `agent_eval_kit.report` is imported as the SUBMODULE rather than the package root on purpose:
# the root pulls in `gate_client`, and with it httpx, which this stdlib-only domain module has no
# business requiring.


def utcnow() -> datetime:
    """Timezone-aware UTC now (the single clock the domain uses)."""
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Vertical and Market — the two configurable axes (generic, multi-vertical, APAC)
# --------------------------------------------------------------------------- #
class Vertical(StrEnum):
    """The business vertical the creative is scoped to.

    D3 is generic: banking is ONE vertical and online retail is another. The
    deterministic engines and the LLM prompts switch tone/taxonomy/rules by vertical;
    no bank-only logic is baked into the domain.
    """

    BANKING = "banking"
    ONLINE_RETAIL = "online_retail"


class Market(StrEnum):
    """A supported market (Japan, Australia, Singapore).

    The residency region, locales and per-market rule sets are config + seed (see
    :data:`MARKET_PROFILES` and ``config/settings.yaml``), never hard-coded into a
    branch. Adding a market is a config + seed change, not a code change.
    """

    JP = "JP"
    AU = "AU"
    SG = "SG"


@dataclass(frozen=True, slots=True)
class MarketProfile:
    """Static, fictional-data-friendly metadata for a market.

    The residency ``region`` is a GCP regional id selectable at deploy and validated;
    ``locales`` drives bilingual (ja + en) output. These defaults can be overridden in
    ``config/settings.yaml`` so the catalog stays config-driven.
    """

    market: Market
    region: str  # GCP residency region, e.g. "asia-northeast1" (Tokyo)
    display_name: str
    locales: tuple[str, ...]  # e.g. ("ja", "en") or ("en",)
    currency: str = ""


# Built-in defaults. Region/locale are config + seed: settings.yaml may override these.
MARKET_PROFILES: dict[Market, MarketProfile] = {
    Market.JP: MarketProfile(
        market=Market.JP,
        region="asia-northeast1",
        display_name="Japan",
        locales=("ja", "en"),
        currency="JPY",
    ),
    Market.AU: MarketProfile(
        market=Market.AU,
        region="australia-southeast1",
        display_name="Australia",
        locales=("en",),
        currency="AUD",
    ),
    Market.SG: MarketProfile(
        market=Market.SG,
        region="asia-southeast1",
        display_name="Singapore",
        locales=("en",),
        currency="SGD",
    ),
}


# --------------------------------------------------------------------------- #
# Provenance / citation
# --------------------------------------------------------------------------- #
class SourceType(StrEnum):
    """Every citation names which kind of evidence / rule it points to."""

    BRAND_GUIDELINE = "brand_guideline"  # an internal brand-book rule
    AD_POLICY = "ad_policy"  # an advertising / consumer-protection policy clause
    CLAIM_RULE = "claim_rule"  # an advertising-claim substantiation rule
    ASSET_SPEC = "asset_spec"  # a channel asset-spec requirement
    INTERNAL = "internal"  # the internal brand / creative corpus (File Search)
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Citation:
    """Provenance attached to every finding and check in a creative review.

    A reviewer must be able to trace every flag back to its exact source: the brand-book
    rule, the advertising-policy clause or the asset-spec requirement it was checked
    against. An auditable creative review is the whole point of D3.
    """

    source_id: str
    source_type: SourceType
    title: str
    url: str = ""
    page: int | None = None
    published_date: str | None = None  # ISO date as published, if known
    snippet: str = ""
    score: float | None = None


# --------------------------------------------------------------------------- #
# Retrieval from the internal brand / creative corpus (KnowledgeBasePort)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """A passage retrieved from the internal brand / creative corpus."""

    text: str
    citation: Citation
    score: float = 0.0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    top_k: int = 10
    market: Market | None = None
    vertical: Vertical | None = None
    filters: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Channels and asset specifications
# --------------------------------------------------------------------------- #
class Channel(StrEnum):
    """The marketing channel a creative is produced for.

    Channels are generic across verticals; per-channel asset specs live in the seed
    (:data:`ASSET_SPECS`-style config), not in the enum, so the engine stays generic.
    """

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    DISPLAY = "display"  # display banner / image ad
    SEARCH = "search"  # search ad
    SOCIAL = "social"
    WEB = "web"


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """The hard channel constraints a variant's copy / image must satisfy.

    Asset specs are config + seed (per channel, per market where it matters); the
    deterministic asset-spec engine checks a variant against the spec for its channel.
    A spec field left at its sentinel (``0`` / ``()``) is "not constrained".
    """

    channel: Channel
    max_headline_chars: int = 0  # 0 => unconstrained
    max_body_chars: int = 0
    max_cta_chars: int = 0
    requires_headline: bool = True
    requires_cta: bool = False
    requires_image: bool = False
    image_width: int = 0  # 0 => unconstrained
    image_height: int = 0
    allowed_aspect_ratios: tuple[str, ...] = ()  # e.g. ("1:1", "16:9")
    mandatory_disclaimer_tokens: tuple[str, ...] = ()  # tokens that must appear somewhere


# --------------------------------------------------------------------------- #
# Brand guidelines, advertising policies and claim rules (config + seed)
# --------------------------------------------------------------------------- #
class RuleSeverity(StrEnum):
    """How serious a violated rule is (drives review escalation)."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BrandRuleKind(StrEnum):
    """A category of brand-guideline rule (generic across verticals)."""

    FORBIDDEN_TERM = "forbidden_term"  # word/phrase that must not appear
    REQUIRED_TERM = "required_term"  # word/phrase that must appear
    TONE = "tone"  # tone-of-voice signal (e.g. no all-caps shouting)
    READING_LEVEL = "reading_level"  # plain-language requirement


@dataclass(frozen=True, slots=True)
class BrandRule:
    """One brand-book rule. Config + seed; the engine never hard-codes a brand.

    ``pattern`` is matched case-insensitively as a whole word/phrase against the copy.
    For TONE rules the engine applies its own heuristic (see the brand engine).
    """

    id: str
    kind: BrandRuleKind
    pattern: str  # the term / phrase the rule concerns (empty for TONE/READING_LEVEL)
    message: str
    severity: RuleSeverity = RuleSeverity.MEDIUM
    vertical: Vertical | None = None  # None => applies to all verticals
    market: Market | None = None  # None => applies to all markets
    suggestion: str = ""  # a compliant alternative, if any


class ClaimRuleKind(StrEnum):
    """A category of advertising-claim rule."""

    SUPERLATIVE = "superlative"  # "best", "cheapest" need substantiation
    GUARANTEE = "guarantee"  # "guaranteed", "risk-free" need qualification
    COMPARATIVE = "comparative"  # "better than X" needs a basis
    PERFORMANCE = "performance"  # "save 50%", "earn 5%" needs a basis/disclaimer
    UNQUALIFIED_FREE = "unqualified_free"  # "free" without conditions


@dataclass(frozen=True, slots=True)
class ClaimRule:
    """One advertising-claim rule. Config + seed (per market + vertical).

    ``triggers`` are the phrases that fire the rule; ``requires_tokens`` are tokens
    (e.g. "T&Cs apply", "*", a disclaimer) at least one of which must also appear for the
    claim to be considered substantiated.
    """

    id: str
    kind: ClaimRuleKind
    triggers: tuple[str, ...]
    message: str
    requires_tokens: tuple[str, ...] = ()
    severity: RuleSeverity = RuleSeverity.HIGH
    vertical: Vertical | None = None
    market: Market | None = None
    citation: Citation | None = None  # the policy clause this rule enforces


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One per-market / per-vertical advertising or consumer-protection policy rule.

    Generic advertising / consumer-protection, NOT bank-only: banking financial-promotion
    rules are simply one configured set among others. ``forbidden_patterns`` are phrases
    that must not appear; ``required_patterns`` must appear (e.g. a mandated disclosure).
    """

    id: str
    name: str  # human name, e.g. "JP Premiums and Representations Act"
    market: Market
    vertical: Vertical | None  # None => applies to every vertical in the market
    forbidden_patterns: tuple[str, ...] = ()
    required_patterns: tuple[str, ...] = ()
    message: str = ""
    severity: RuleSeverity = RuleSeverity.HIGH
    citation: Citation | None = None


# --------------------------------------------------------------------------- #
# Creative brief, variants and generated images
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CreativeBrief:
    """The inbound creative brief: what to produce, for whom, where.

    Generic across verticals: ``product`` and ``offer`` are free text seeded per
    vertical; ``market``/``vertical``/``channel`` are the configurable axes.
    """

    topic: str  # the campaign theme, e.g. "spring savings push"
    market: Market
    vertical: Vertical
    channel: Channel
    product: str = ""  # e.g. "high-yield savings account" / "spring apparel sale"
    offer: str = ""  # e.g. "4.10% p.a." / "20% off"
    audience: str = ""  # target audience description
    tone: str = "clear and trustworthy"
    n_variants: int = 3
    keywords: tuple[str, ...] = ()
    locale: str = ""  # "" => the market's first locale


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    """An image produced for a variant (Imagen on GCP; a deterministic stub locally)."""

    prompt: str
    width: int = 0
    height: int = 0
    aspect_ratio: str = ""
    uri: str = ""  # where the image was stored (or a data placeholder offline)
    alt_text: str = ""
    citation: Citation | None = None  # provenance of the generating model / prompt


@dataclass(frozen=True, slots=True)
class Variant:
    """One creative variant: the copy fields plus an optional image.

    The LLM drafts these; the deterministic engines then check each one. ``id`` is a
    stable, content-derived slug so dedupe and audit are reproducible.
    """

    id: str
    headline: str
    body: str
    cta: str = ""
    channel: Channel = Channel.EMAIL
    image: GeneratedImage | None = None
    rationale: str = ""  # the model's note on why this angle (narration only)
    citations: tuple[Citation, ...] = ()


# --------------------------------------------------------------------------- #
# Check results — the deterministic engine outputs
# --------------------------------------------------------------------------- #
class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Finding:
    """One issue raised by a deterministic engine against a variant.

    Carries the citation of the rule / policy / spec it was checked against, so every
    flag is auditable back to its source.
    """

    rule_id: str
    severity: RuleSeverity
    message: str
    span: str = ""  # the offending substring, if any
    suggestion: str = ""
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class BrandCheck:
    """The deterministic brand-guideline check result for one variant."""

    variant_id: str
    status: CheckStatus
    findings: tuple[Finding, ...] = ()

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    """The deterministic advertising-claim check result for one variant."""

    variant_id: str
    status: CheckStatus
    findings: tuple[Finding, ...] = ()

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


@dataclass(frozen=True, slots=True)
class PolicyCheck:
    """The deterministic per-market / per-vertical policy check for one variant."""

    variant_id: str
    market: Market
    vertical: Vertical
    status: CheckStatus
    findings: tuple[Finding, ...] = ()

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


@dataclass(frozen=True, slots=True)
class AssetCheck:
    """The deterministic asset-spec check (lengths, image dims, disclaimers)."""

    variant_id: str
    channel: Channel
    status: CheckStatus
    findings: tuple[Finding, ...] = ()

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


@dataclass(frozen=True, slots=True)
class VariantReview:
    """All deterministic checks for one variant, plus a derived verdict.

    The verdict is computed deterministically from the four checks; the LLM never
    decides whether a variant is brand-safe.
    """

    variant: Variant
    brand: BrandCheck
    claim: ClaimCheck
    policy: PolicyCheck
    asset: AssetCheck

    @property
    def checks(self) -> tuple[BrandCheck | ClaimCheck | PolicyCheck | AssetCheck, ...]:
        return (self.brand, self.claim, self.policy, self.asset)

    @property
    def status(self) -> CheckStatus:
        """Worst status across the four checks (FAIL > WARN > PASS)."""
        statuses = {c.status for c in self.checks}
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.PASS

    @property
    def approved(self) -> bool:
        """A variant is provisionally approved only when nothing failed."""
        return self.status is not CheckStatus.FAIL

    @property
    def findings(self) -> tuple[Finding, ...]:
        out: list[Finding] = []
        for check in self.checks:
            out.extend(check.findings)
        return tuple(out)

    @property
    def citations(self) -> tuple[Citation, ...]:
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for finding in self.findings:
            for c in finding.citations:
                key = (c.source_id, c.page)
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return tuple(out)


# --------------------------------------------------------------------------- #
# Generation (LLM) — the LLM only drafts copy / variant ideas
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str  # "user" | "model" | "system"
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    messages: tuple[LlmMessage, ...]
    system_instruction: str | None = None
    model: str | None = None  # None => adapter default from config
    thinking: ThinkingLevel = ThinkingLevel.MEDIUM
    temperature: float = 0.4
    max_output_tokens: int = 4096
    response_schema: dict | None = None  # JSON schema for structured output


# ``TokenUsage`` was declared here: three int fields defaulting to zero, frozen and slotted. It
# now comes from ``hex_service_kit.observability`` (imported at the top of this module and
# re-exported), byte-identical to what stood here, because a shared value type that every repo
# copies is a shared value type that had never actually been shared.


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    raw: dict | None = None


@dataclass(frozen=True, slots=True)
class ImageRequest:
    """A request to the image-generation port (Imagen on GCP)."""

    prompt: str
    aspect_ratio: str = "1:1"
    width: int = 0
    height: int = 0
    market: Market | None = None
    vertical: Vertical | None = None
    n: int = 1


# --------------------------------------------------------------------------- #
# Safety (guardrail) — A1 Guardrail Gateway concern
# --------------------------------------------------------------------------- #
class GuardrailCategory(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    SENSITIVE_DATA = "sensitive_data"
    MALICIOUS_URL = "malicious_url"
    OTHER = "other"


class Direction(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class GuardrailFinding:
    category: GuardrailCategory
    confidence: str  # "low" | "medium" | "high"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    direction: Direction
    findings: tuple[GuardrailFinding, ...] = ()
    sanitized_text: str | None = None
    reason: str = ""


# --------------------------------------------------------------------------- #
# Audit and observability — A5 Observability, Audit and FinOps concern
# --------------------------------------------------------------------------- #
class Decision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"  # routed to a human (maker-checker)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable, WORM-stored record of one creative-studio interaction."""

    action: str  # "generate_creative" | "review_variant"
    actor: str  # authenticated marketer / service identity
    decision: Decision
    prompt: str = ""
    response: str = ""
    citations: tuple[Citation, ...] = ()
    resource: str = "creative-studio"
    trace_id: str | None = None
    timestamp: datetime = field(default_factory=utcnow)
    metadata: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Evaluation gate — A4 AI Quality and Model-Risk concern
# --------------------------------------------------------------------------- #
# ``EvalMetricResult`` and ``EvalReport`` were declared here. They now come from
# ``agent_eval_kit.report`` (imported at the top of this module and re-exported).
#
# The fail-closed rule this repo added to ``EvalReport.passed`` is NOT lost in the move: the
# commons property is the same expression, ``n_examples > 0 and bool(results) and all(...)``.
# That mattered enough to check character by character before re-exporting, because the naive
# ``all(())`` is vacuously True, ``eval/run_eval.py`` exits 0 on this property, and re-exporting
# a laxer copy would have turned "an evaluation that scored nothing" back into a certified
# promotion.
#
# The commons type is otherwise strictly ADDITIVE: it carries ``run_id``, ``dataset_version``,
# ``dataset_digest``, ``evaluator``, ``schema_version``, ``trace_id``, ``correlation_id``,
# ``artifact_refs`` and ``attested``, all defaulted, so every constructor call in this repo still
# compiles unchanged. Those fields are the durable evidence the platform adapter used to throw
# away on the way in, which is what made the re-export worth doing rather than merely tidy.


# --------------------------------------------------------------------------- #
# Governance — A3 Agent Registry and the MCP tool catalog
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AgentSkill:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Minimal A2A-style agent card published at /.well-known/agent-card.json."""

    name: str
    description: str
    url: str
    version: str
    skills: tuple[AgentSkill, ...] = ()
    provider: str = "creative-studio"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A governed, least-privilege tool exposed to the agent (typically via MCP)."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# The top-level aggregate — always requires human review
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CreativeStudioResult:
    """A cited, brand-checked set of creative variants for a brief.

    The top-level consequential output of D3. Creative that ships to customers is
    consequential, so it **always** requires human review (maker-checker): a maker (the
    agent) proposes variants and runs every deterministic check, and a checker (a
    qualified brand / compliance reviewer) disposes before anything is published.
    """

    id: str
    brief: CreativeBrief
    reviews: tuple[VariantReview, ...] = ()
    summary: str = ""  # LLM narration over the already-computed checks
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True
    generated_at: datetime = field(default_factory=utcnow)

    @property
    def approved_reviews(self) -> tuple[VariantReview, ...]:
        return tuple(r for r in self.reviews if r.approved)

    @property
    def failed_reviews(self) -> tuple[VariantReview, ...]:
        return tuple(r for r in self.reviews if not r.approved)

    @property
    def all_findings(self) -> tuple[Finding, ...]:
        out: list[Finding] = []
        for review in self.reviews:
            out.extend(review.findings)
        return tuple(out)

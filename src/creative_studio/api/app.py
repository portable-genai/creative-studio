"""FastAPI app — thin HTTP boundary over the domain services.

Owns no business logic: it translates a request into a domain call and serialises the cited
result with ``result_jsonable`` / ``review_jsonable`` (the bare ``to_jsonable`` walker skips
the engines' derived verdicts, which are properties). Heavy / cloud imports stay lazy so
importing this module under the local profile needs no Google Cloud SDK.

Identity is server-verified, never client-asserted: every route takes a ``CurrentPrincipal``
resolved by the active :class:`IdentityPort` adapter, and the verified ``principal.actor``
becomes the audit actor. The request body carries no ``actor`` field, so a caller cannot
assert who they are.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from hex_service_kit import cors_allowlist
from hex_service_kit.netdefaults import ConfiguredEmptyError, read_env_setting
from hex_service_kit.web import add_loopback_exposure_guard

from ..config import Settings, end_user_auth_kind
from ..domain.errors import GuardrailBlockedError, NoVariantsError
from ..domain.identity import IdentityError
from ..domain.models import Channel, CreativeBrief, Market, Variant, Vertical
from ..domain.serialization import result_jsonable, review_jsonable
from ..ports.identity import VERIFIED
from . import deps
from .deps import make_studio_service
from .schemas import (
    AgentCardModel,
    CreativeRequestModel,
    HealthModel,
    VariantReviewRequestModel,
)
from .security import CurrentPrincipal

_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Embedding-surface controls. In secure/embedded mode the studio is served same-origin via
# the parent app's reverse-proxy (no CORS needed); for the cross-origin / standalone dev
# case, MKT_CREATIVE_CORS_ORIGINS is an explicit per-tenant allowlist (never "*").
# MKT_CREATIVE_FRAME_ANCESTORS is the CSP frame-ancestors allowlist of parent origins
# permitted to iframe the studio UI.
_FRAME_ANCESTORS_ENV = "MKT_CREATIVE_FRAME_ANCESTORS"
_CORS_ORIGINS_ENV = "MKT_CREATIVE_CORS_ORIGINS"
_DEFAULT_FRAME_ANCESTORS = "'self'"

# The ONE deliberate opt-out from the loopback exposure bound below. It is a RELAXATION, so the
# commons compares the raw value against exactly "1": unset, set-and-empty, "0", "true" and
# " 1 " all leave the guard ON, and no other variable can switch it off.
_INSECURE_DEMO_ENV = "MKT_CREATIVE_ALLOW_INSECURE_DEMO"


#: Entries that are a wildcard by BEHAVIOUR rather than by spelling, so the asterisk test below
#: cannot see them. ``null`` is the one that matters: a SANDBOXED iframe presents the origin
#: ``null``, so allowing it hands framing and credentialed cross-origin rights to any page able
#: to open one. ``'*'`` is what a quoted Terraform variable or a YAML string renders, and ``*.*``
#: is a host pattern matching every name with a dot in it. The same set is refused on the
#: document half, in ``ui/lib/csp.mjs``.
_WILDCARD_TOKENS = frozenset({"*", "'*'", "null", "*.*"})


def _refuse_wildcard(values: Sequence[str], env_name: str) -> None:
    """Refuse a resolved origin policy that names a wildcard, at boot rather than per request.

    Both allowlists were resolved carefully in three states and then handed on verbatim, with
    the "never ``*``" rule living only in the comment above and in the runbook. A comment does
    not fail a build: ``frame-ancestors *`` lets ANY page frame the console, and ``*`` in the
    CORS allowlist grants every origin on the internet the trust the allowlist exists to
    restrict, on responses that carry credentials.

    Any token CONTAINING ``*`` is refused, not only a bare one. ``https://*.client.example``
    is a real CSP host-source wildcard covering every subdomain, including whichever one an
    attacker manages to register, and an allowlist is only worth having when each entry names
    an origin somebody decided to trust.

    The character test is necessary and not sufficient, so :data:`_WILDCARD_TOKENS` covers the
    spellings that carry no asterisk and behave as one anyway. A real origin never contains the
    character and is never one of those tokens, so this refuses nothing a deployment could
    correctly hold.
    """
    offending = [value for value in values if "*" in value or value in _WILDCARD_TOKENS]
    if offending:
        raise ValueError(
            f"{env_name} resolved to {offending}: the origin policy must never contain a "
            "wildcard. Name the exact parent origins that may frame or call this service, or "
            f"unset {env_name} to keep the restrictive default."
        )


def _frame_ancestors() -> str:
    """Resolve the CSP ``frame-ancestors`` allowlist in THREE states, never two.

    ``os.environ.get(name, "'self'")`` only distinguishes absent from present, so a variable
    an operator set to empty (a Terraform variable that renders to nothing, a Cloud Run env
    var declared with no value) reached the middleware verbatim and produced
    ``Content-Security-Policy: frame-ancestors `` with an EMPTY directive. Browsers discard a
    valueless directive as a parse error, and the ``== "'self'"`` branch below was skipped too,
    so ``X-Frame-Options`` was not emitted as the legacy fallback either: the clickjacking
    control vanished without a trace in the one deployment shape that looks configured.

    * unset: no intent was expressed, so the documented restrictive default stands.
    * set and empty: an intent WAS expressed and it names nothing. Refused, not silently
      widened. This resolver runs at import, so the refusal is a BOOT refusal: the process
      never comes up serving responses that carry no framing policy at all.
    * set with a value: used as given, once :func:`_refuse_wildcard` has established that it
      names origins rather than everybody.
    """
    setting = read_env_setting(_FRAME_ANCESTORS_ENV)
    if setting.is_configured_empty:
        raise ConfiguredEmptyError(
            f"{_FRAME_ANCESTORS_ENV} is set but empty. An empty CSP frame-ancestors directive "
            "is discarded by browsers, which would leave the studio with no clickjacking "
            f"protection at all. Unset {_FRAME_ANCESTORS_ENV} to keep the "
            f"{_DEFAULT_FRAME_ANCESTORS} default, or name the parent origins that may frame it."
        )
    resolved = setting.value or _DEFAULT_FRAME_ANCESTORS
    _refuse_wildcard(resolved.split(), _FRAME_ANCESTORS_ENV)
    return resolved


_FRAME_ANCESTORS = _frame_ancestors()


def _cors_origins() -> list[str]:
    """Explicit allowlist, never "*"; the localhost dev fallback applies ONLY under a
    DELIBERATE local profile (shared hex-service-kit rule).

    The argument is the exposure profile, not the raw one: a run that never chose a profile
    presents ``unconfigured``, which is no origin's allowlist, so an unset variable cannot
    hand cross-origin trust to arbitrary local processes on a user's machine.

    The commons resolver documents that it never returns ``*``, and it never invents one, but
    it does return what the variable says: a tenant that sets the allowlist to ``*`` gets
    ``["*"]`` back. :func:`_refuse_wildcard` is what turns that documented rule into a refusal.

    It runs on the CONFIGURED value first, and that ordering is the point rather than an
    accident. The commons resolver now refuses a wildcard itself, raising
    ``InsecureCorsError``, so whichever of the two runs first is the one that decides which
    message an operator reads. This repo owns the rule: it names the variable, it says how to
    get back to the restrictive default, and its union covers the behavioural tokens as well
    as the asterisk. Running it first keeps it the single authority and leaves the commons an
    unreachable backstop on the configured path. The trailing call still guards the RESOLVED
    list, which under the unset default is a value the operator never wrote.
    """
    setting = read_env_setting(_CORS_ORIGINS_ENV)
    if setting.has_value:
        _refuse_wildcard(
            [origin.strip() for origin in setting.value.split(",") if origin.strip()],
            _CORS_ORIGINS_ENV,
        )
    origins = cors_allowlist(
        deps.get_container().settings.exposure_profile,
        origins_env=_CORS_ORIGINS_ENV,
        dev_origins=tuple(_DEV_ORIGINS),
    )
    _refuse_wildcard(origins, _CORS_ORIGINS_ENV)
    return origins


app = FastAPI(
    title="D3 Brand-Safe Creative and Content Studio",
    version="0.1.0",
    description=(
        "Gemini copy + Imagen image with deterministic brand, advertising-claim, per-market "
        "policy and asset-spec validation, generic across banking and online retail and the "
        "JP/AU/SG markets."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Dev-Persona"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Any:
    """Emit embedding-surface headers: CSP frame-ancestors (who may iframe the studio).

    ``_FRAME_ANCESTORS`` is guaranteed non-empty by :func:`_frame_ancestors`, so the directive
    emitted here always carries a value a browser will honour.
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {_FRAME_ANCESTORS}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if deps.get_container().settings.exposure_profile in {"gcp", "platform", "onprem"}:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if _FRAME_ANCESTORS == _DEFAULT_FRAME_ANCESTORS:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


# A request arrives with nothing authenticating the END USER unless BOTH of these hold, and the
# guard below bounds every case where either fails:
#
#   1. a profile was chosen. Absent that, nobody selected an identity scheme: the seeded-persona
#      adapter refuses to construct and every artifact route answers 401, but /healthz, the
#      agent card and /v1/personas would still answer a stranger, and a deployment in that state
#      has no business being reachable at all. It is also the one case where a settings file
#      that bound a verifying adapter must NOT buy the relaxation: unset is not consent,
#      whatever the binding says;
#   2. the identity adapter the active binding names DECLARES that it verifies the end user
#      (``ports/identity.py``). Seeded personas arrive on the ``X-Dev-Persona`` header the
#      caller wrote and the on-premises placeholder resolves nobody at all; neither
#      authenticates anyone, so neither may switch this off. Reading the BINDING rather than
#      the profile string also answers correctly for a deployment that rebound identity in
#      ``config/settings.yaml`` to its own IdP adapter.
#
# Resolved from ONE settings object, so the two halves of the question cannot answer about
# different resolutions of the profile.
_POSTURE_SETTINGS = deps.get_container().settings
_END_USER_AUTHENTICATED = (
    _POSTURE_SETTINGS.profile_explicit and end_user_auth_kind(_POSTURE_SETTINGS) == VERIFIED
)

# Registered LAST, so it is the OUTERMOST middleware: an off-loopback caller is refused before
# CORS, before the security-header middleware above and before any route or dependency runs.
#
# DO NOT DELETE THIS AND RELY ON A BIND-HOST CHECK IN AN ENTRY POINT. A start-up bound is a
# property of the ONE entry point that calls it, and the shipped entry points do not: this
# repo's Dockerfile ends with
#
#     CMD exec uvicorn creative_studio.api.app:app --host 0.0.0.0 --port ${PORT}
#
# and ``make run-api`` hands the same ``creative_studio.api.app:app`` object to uvicorn. Both
# reach this module and neither reaches any ``main()``, so the bound has to live on the APP
# OBJECT to hold in a shipped process. Without it, a LAN peer got 200 on /v1/personas with the
# full seeded-persona list and could then act as any of them, including the approver, by
# echoing the id back in ``X-Dev-Persona``.
add_loopback_exposure_guard(
    app,
    unauthenticated=not _END_USER_AUTHENTICATED,
    insecure_demo_env=_INSECURE_DEMO_ENV,
    # The EXPOSURE profile, so a run nobody configured names itself 'unconfigured' in the
    # refusal rather than borrowing the name of a profile an operator never chose.
    posture=_POSTURE_SETTINGS.exposure_profile,
)


@app.get("/healthz", response_model=HealthModel)
def healthz() -> HealthModel:
    settings = Settings.load()
    return HealthModel(
        status="ok",
        profile=settings.profile,
        market=settings.market,
        vertical=settings.vertical,
        runtime=settings.runtime,
        generator_model=settings.generator_model,
    )


@app.get(
    "/.well-known/agent-card.json",
    response_model=AgentCardModel,
    tags=["governance"],
)
def agent_card() -> AgentCardModel:
    """Serve the A2A AgentCard for this agent (Hrz3 discovery, rule R4).

    Pure and identity-agnostic: the card advertises the agent's governed skills so a peer
    agent or the registry sees one capability surface. Built from ``agent.agent_card`` with no
    ADK import.
    """
    from ..agent.agent_card import build_agent_card

    return AgentCardModel.from_domain(build_agent_card(deps.get_container().settings))


@app.get("/v1/personas")
def personas() -> list[dict[str, str]]:
    """List seeded dev personas for the local persona picker (empty outside local profile).

    Local mode runs with no IdP; the UI uses this to let a demo/test pick an identity
    (and thus exercise per-user authorization) via the ``X-Dev-Persona`` header. Secure
    profiles resolve identity from the IAP assertion, so this returns an empty list, and so
    does a run that never chose a profile: the persona adapter refuses to construct there,
    which is an empty picker rather than a 500.
    """
    try:
        identity = deps.get_container().identity
    except IdentityError:
        return []
    lister = getattr(identity, "personas", None)
    if lister is None:
        return []
    return [dict(p) for p in lister()]


def _brief(body: CreativeRequestModel) -> CreativeBrief:
    return CreativeBrief(
        topic=body.topic,
        market=Market(body.market),
        vertical=Vertical(body.vertical),
        channel=Channel(body.channel),
        product=body.product,
        offer=body.offer,
        audience=body.audience,
        tone=body.tone,
        n_variants=body.n_variants,
    )


@app.post("/v1/creative")
def generate_creative(body: CreativeRequestModel, principal: CurrentPrincipal) -> dict:
    try:
        brief = _brief(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = make_studio_service().generate(
            brief,
            actor=principal.actor,
            with_image=body.with_image,
            tenant=principal.tenant,
        )
    except GuardrailBlockedError as exc:
        raise HTTPException(status_code=400, detail=f"guardrail blocked: {exc}") from exc
    except NoVariantsError as exc:
        raise HTTPException(status_code=404, detail=f"no variants generated: {exc}") from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return result_jsonable(result)


@app.post("/v1/review")
def review_variant(body: VariantReviewRequestModel, principal: CurrentPrincipal) -> dict:
    try:
        brief = CreativeBrief(
            topic="ad-hoc review",
            market=Market(body.market),
            vertical=Vertical(body.vertical),
            channel=Channel(body.channel),
        )
        variant = Variant(
            id="",
            headline=body.headline,
            body=body.body,
            cta=body.cta,
            channel=Channel(body.channel),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        review = make_studio_service().review(brief, variant, actor=principal.actor)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return review_jsonable(review)

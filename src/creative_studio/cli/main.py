"""``mkt-creative`` — the Typer CLI for the D3 Brand-Safe Creative and Content Studio.

A thin presentation layer over the domain services. It owns no business logic: every
command builds the wiring from :func:`creative_studio.api.deps.make_studio_service`,
invokes one domain service, and pretty-prints the cited result.

Design constraints honoured here:

* **Import-safe.** Importing this module (the ``[project.scripts]`` entry point, or
  ``--help``) must never pull in FastAPI, uvicorn or the Google Cloud SDKs. They are
  imported lazily inside command bodies, so the on-prem / local / test profile (which
  installs no Google Cloud SDK) can still load the CLI.
* **Profile-aware.** ``MKT_CREATIVE_PROFILE`` selects the adapter stack. The ``onprem``
  profile binds placeholder adapters that raise ``NotImplementedError``; the CLI then fails
  clearly (exit code 2) naming the migration target.
* **Citations are first-class.** Every finding prints with the rule / policy it cites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import Citation, CreativeStudioResult, VariantReview

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "D3 Brand-Safe Creative and Content Studio — Gemini copy + Imagen image with "
        "deterministic brand, advertising-claim, per-market policy and asset-spec checks, "
        "generic across banking and online retail and the JP/AU/SG markets."
    ),
)

_PROFILE_EXIT = 2
_RUNTIME_EXIT = 1
_CLI_ACTOR = "cli:operator"

_STATUS_COLOR = {
    "pass": typer.colors.GREEN,
    "warn": typer.colors.YELLOW,
    "fail": typer.colors.RED,
}


def _fail(message: str, *, code: int = _RUNTIME_EXIT) -> Any:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _run(action: str, fn: Any) -> Any:
    """Execute ``fn`` and translate adapter failures into clean CLI errors."""
    from ..config import Settings

    profile = Settings.load().profile
    try:
        return fn()
    except NotImplementedError as exc:
        detail = str(exc) or "method not implemented"
        _fail(
            f"'{action}' is not available under profile '{profile}'. "
            f"This profile uses placeholder adapters (migration target): {detail}",
            code=_PROFILE_EXIT,
        )
    except KeyError as exc:
        _fail(f"'{action}' has no adapter wired for profile '{profile}': {exc}", code=_PROFILE_EXIT)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks to operators
        _fail(f"'{action}' failed: {type(exc).__name__}: {exc}", code=_RUNTIME_EXIT)


# --------------------------------------------------------------------------- #
# Pretty-printing
# --------------------------------------------------------------------------- #
def _fmt_citation(c: Citation) -> str:
    st = c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type)
    return f"[{c.source_id}, {st}] {c.title}"


def _echo_review_banner(requires_review: bool) -> None:
    if requires_review:
        typer.secho(
            "  [HUMAN REVIEW REQUIRED] maker-checker gate — do not publish this creative "
            "until a qualified brand / compliance reviewer signs off.",
            fg=typer.colors.YELLOW,
            bold=True,
        )


def _echo_review(review: VariantReview) -> None:
    v = review.variant
    color = _STATUS_COLOR.get(review.status.value, typer.colors.WHITE)
    typer.secho(f"\n  Variant {v.id} — {review.status.value.upper()}", fg=color, bold=True)
    typer.echo(f"    headline: {v.headline}")
    typer.echo(f"    body    : {v.body}")
    if v.cta:
        typer.echo(f"    cta     : {v.cta}")
    if v.image is not None:
        typer.echo(f"    image   : {v.image.uri} ({v.image.aspect_ratio})")
    if review.findings:
        typer.secho("    Findings:", bold=True)
        for f in review.findings:
            typer.echo(f"      - [{f.severity.value}] {f.message}")
            for c in f.citations:
                typer.echo(f"          cite: {_fmt_citation(c)}")
    else:
        typer.secho("    No issues found.", fg=typer.colors.GREEN)


def _echo_result(result: CreativeStudioResult) -> None:
    b = result.brief
    typer.secho(f"\nCREATIVE: {b.topic}", bold=True)
    typer.echo(f"  id       : {result.id}")
    typer.echo(f"  market   : {b.market.value}")
    typer.echo(f"  vertical : {b.vertical.value}")
    typer.echo(f"  channel  : {b.channel.value}")
    typer.echo(
        f"  variants : {len(result.reviews)} "
        f"({len(result.approved_reviews)} approved, {len(result.failed_reviews)} failed)"
    )
    _echo_review_banner(result.requires_human_review)
    typer.secho("\n  Summary:", bold=True)
    typer.echo(f"    {result.summary}")
    for review in result.reviews:
        _echo_review(review)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def generate(
    topic: str = typer.Argument(..., help="The campaign theme, e.g. 'spring savings push'."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
    channel: str = typer.Option("email", "--channel", "-C", help="Channel: email | display | ..."),
    product: str = typer.Option("", "--product", "-p", help="Product / offer subject."),
    offer: str = typer.Option("", "--offer", "-o", help="The headline offer."),
    n_variants: int = typer.Option(3, "--variants", "-n", help="Number of variants."),
    with_image: bool = typer.Option(False, "--image", help="Also generate an image asset."),
) -> None:
    """Generate and brand-check creative variants for a campaign theme."""
    from ..api.deps import make_studio_service
    from ..domain.models import Channel, CreativeBrief, Market, Vertical

    def go() -> CreativeStudioResult:
        brief = CreativeBrief(
            topic=topic,
            market=Market(market),
            vertical=Vertical(vertical),
            channel=Channel(channel),
            product=product,
            offer=offer,
            n_variants=n_variants,
        )
        return make_studio_service().generate(brief, actor=_CLI_ACTOR, with_image=with_image)

    result = _run("generate", go)
    _echo_result(result)


@app.command()
def review(
    headline: str = typer.Argument(..., help="The variant headline to review."),
    body: str = typer.Option("", "--body", "-b", help="The variant body copy."),
    cta: str = typer.Option("", "--cta", help="The variant call to action."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
    channel: str = typer.Option("email", "--channel", "-C", help="Channel: email | display | ..."),
) -> None:
    """Run the deterministic brand / claim / policy / asset checks on one variant."""
    from ..api.deps import make_studio_service
    from ..domain.models import Channel, CreativeBrief, Market, Variant, Vertical

    def go() -> VariantReview:
        brief = CreativeBrief(
            topic="ad-hoc review",
            market=Market(market),
            vertical=Vertical(vertical),
            channel=Channel(channel),
        )
        variant = Variant(id="", headline=headline, body=body, cta=cta, channel=Channel(channel))
        return make_studio_service().review(brief, variant, actor=_CLI_ACTOR)

    result = _run("review", go)
    typer.secho(f"\nVARIANT REVIEW: {market}/{vertical}/{channel}", bold=True)
    _echo_review_banner(not result.approved)
    _echo_review(result)


if __name__ == "__main__":  # pragma: no cover
    app()

#!/usr/bin/env python3
"""Offline evaluation gate for the D3 Brand-Safe Creative Studio (A4).

This is the **promotion gate**: CI runs it on every change and the build fails if the
studio's creative review falls below the model-risk thresholds agreed for a brand-safe
creative agent (see ``eval/rubrics/*.yaml``)::

    check_groundedness     >= 0.80   (every finding carries a citation to its rule/policy)
    citation_accuracy      >= 0.90   (cites only the rules / policies actually applied)
    brand_safety_detection >= 0.80   (a deliberately non-compliant variant is caught)
    review_safety          >= 0.99   (every result requires human review; maker-checker)

Two evaluators, one gate
------------------------
* **Production evaluator** — the **Gen AI evaluation service** on the Gemini Enterprise
  Agent Platform, wired in as ``EvaluationGatePort`` ->
  ``creative_studio.adapters.gcp.genai_eval:GenAiEvalAdapter``. It needs GCP credentials.
  Select it with ``--use-gcp``.

* **Offline evaluator (default)** — a deterministic gate in this file. It needs **no GCP
  credentials and no Google Cloud SDK**, runs the real ``CreativeStudioService`` against the
  local (offline) adapters over the golden set, and computes the four metrics. This is what
  guards the merge in CI.

Usage::

    python eval/run_eval.py                      # offline gate (CI)
    python eval/run_eval.py --dataset path.jsonl # custom golden set
    python eval/run_eval.py --use-gcp            # route through GenAiEvalAdapter

Exit code is ``0`` iff ``EvalReport.passed`` (every metric meets its threshold).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Domain models / config are pure-stdlib + the local adapters are SDK-free, so this script
# runs in the local / on-prem / test profile with no Google Cloud SDK installed.
# The --mode smoke|gate scaffold + aligned report rendering come from the shared
# agent-eval-kit commons; this script keeps only its own offline
# evaluator and gate runner.
from agent_eval_kit import (
    assert_can_go_red,
    eval_main,
    load_rubrics,
    prove_before_scoring,
)

from creative_studio.domain.models import (
    Channel,
    Citation,
    CreativeBrief,
    CreativeStudioResult,
    EvalMetricResult,
    EvalReport,
    ImageRequest,
    Market,
    SourceType,
    Variant,
    VariantReview,
    Vertical,
)

#: Where every bar lives. Not a dict here: a threshold written as a Python literal carries no
#: argument. The rubric files carry the reasoning beside the number, and
#: `agent_eval_kit.load_rubrics` reads them. What was here before was BOTH a dict and a loader
#: that overlaid two rubric files on top of it, falling back to the dict when PyYAML was missing.

_REPO_ROOT = Path(__file__).resolve().parent.parent
RUBRICS = _REPO_ROOT / "eval" / "rubrics"
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_creative.jsonl"

# A deliberately non-compliant variant the studio MUST catch (unqualified guarantee,
# misleading absolute claim, no t&cs): the brand_safety_detection probe.
_BAD_VARIANT = Variant(
    id="",
    headline="The BEST risk-free way to get rich!",
    body="100% guaranteed returns, amazing free money — act now!",
    cta="ACT NOW",
)


@dataclass(frozen=True, slots=True)
class GoldenExample:
    id: str
    topic: str
    market: str
    vertical: str
    channel: str
    expect_all_pass: bool


def load_golden(path: Path) -> list[GoldenExample]:
    examples: list[GoldenExample] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        examples.append(
            GoldenExample(
                id=str(obj.get("id", f"example-{lineno}")),
                topic=str(obj["topic"]),
                market=str(obj["market"]),
                vertical=str(obj["vertical"]),
                channel=str(obj.get("channel", "email")),
                expect_all_pass=bool(obj.get("expect_all_pass", True)),
            )
        )
    if not examples:
        raise SystemExit(f"{path}: golden dataset is empty")
    return examples


def load_thresholds_from_rubrics() -> dict[str, float]:
    """Read every metric's reviewed bar out of ``eval/rubrics/*.yaml``. No fallback, by design."""
    return load_rubrics(RUBRICS).thresholds()


#: The metrics this runner scores, in report order. Named so `assert_covers` can compare them
#: with the rubric set in BOTH directions.
SCORED: tuple[str, ...] = (
    "check_groundedness",
    "citation_accuracy",
    "brand_safety_detection",
    "review_safety",
    "image_spec_compliance",
)


def score_image_spec_compliance(image: object, request: object) -> float:
    """Does the generated image asset actually satisfy the request it was made for?

    The `ImageGenerationPort` is the only image port in the fleet and had ZERO eval coverage:
    nothing checked that the asset came back with the dimensions asked for, an aspect ratio that
    matches them, alt text, or provenance. Every one of those is consequential for a marketing
    asset, and the last two are the ones that reach a person: an image with no alt text fails
    accessibility outright, and one with no citation is an asset nobody can say who made.

    Four checks, equally weighted, so a partial failure reads as a partial score rather than as
    a collapse. Scored through whatever adapter the profile binds, so the managed Imagen path
    would be measured by the same rule.
    """
    checks = (
        getattr(image, "width", 0) == getattr(request, "width", -1),
        getattr(image, "height", 0) == getattr(request, "height", -1),
        bool(str(getattr(image, "alt_text", "")).strip()),
        getattr(image, "citation", None) is not None,
    )
    return round(sum(1 for ok in checks if ok) / len(checks), 4)


def prove_image_spec_compliance_can_go_red(threshold: float) -> None:
    """An adapter that ignores the request, or drops alt text, must score below the bar."""
    from creative_studio.domain.models import GeneratedImage, ImageRequest

    request = ImageRequest(prompt="a brand-safe illustration", width=1024, height=1024)
    good = GeneratedImage(
        prompt=request.prompt,
        width=1024,
        height=1024,
        aspect_ratio="1:1",
        uri="https://images.example.test/good.png",
        alt_text="Brand-safe illustration",
        citation=Citation(
            source_id="image:good", source_type=SourceType.OTHER, title="Generated asset"
        ),
    )
    assert_can_go_red(
        lambda image: score_image_spec_compliance(image, request),
        green=good,
        # The three ways this actually goes wrong, in one asset: the wrong size, no alt text,
        # and no provenance. Any one alone would still clear a 0.75 bar, which is why the bar
        # is 1.0 and why the red case is not a single-field mutation.
        red=GeneratedImage(
            prompt=request.prompt, width=512, height=512, aspect_ratio="1:1", uri="", alt_text=""
        ),
        threshold=threshold,
        metric="image_spec_compliance",
    )


# --------------------------------------------------------------------------- #
# Service wiring (the real CreativeStudioService over the local offline adapters)
# --------------------------------------------------------------------------- #
def _make_service():  # type: ignore[no-untyped-def]
    from creative_studio.api.deps import make_studio_service
    from creative_studio.config import Container, LocalSettings, Settings

    base = Settings.load(str(_REPO_ROOT / "config" / "settings.yaml"))
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        channel=base.channel,
        models=base.models,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    container = Container(settings)
    return make_studio_service(container)


def _image_adapter():  # type: ignore[no-untyped-def]
    """The image adapter the CONTAINER binds for this profile, not a stub written here.

    Scoring a stub the eval constructed would measure the eval. Reaching through the container
    means the same rule scores whatever a profile binds, including the managed Imagen adapter,
    which is the only way `image_spec_compliance` says anything about the product.
    """
    from creative_studio.config import Container, LocalSettings, Settings

    base = Settings.load(str(_REPO_ROOT / "config" / "settings.yaml"))
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        channel=base.channel,
        models=base.models,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    return Container(settings).image


# --------------------------------------------------------------------------- #
# Heuristic scorers
# --------------------------------------------------------------------------- #
def score_groundedness(result: CreativeStudioResult) -> float:
    """Every finding raised must carry at least one citation to the rule/policy it cites."""
    findings = result.all_findings
    if not findings:
        return 1.0
    cited = sum(1 for f in findings if f.citations)
    return round(cited / len(findings), 4)


def score_citation_accuracy(result: CreativeStudioResult) -> float:
    """No finding cites a source outside the brand/claim/policy/asset rule namespaces."""
    allowed_types = {"brand_guideline", "ad_policy", "claim_rule", "asset_spec"}
    cites = [c for f in result.all_findings for c in f.citations]
    if not cites:
        return 1.0
    ok = sum(1 for c in cites if c.source_type.value in allowed_types)
    return round(ok / len(cites), 4)


def score_brand_safety_detection(review: VariantReview) -> float:
    """1.0 only when the studio REFUSED to approve the reviewed variant.

    Named rather than inlined so the not-falsely-green proof can drive the real metric: a
    detector that approved everything, or flagged everything, is caught by feeding it a clean
    variant and requiring this to fall to 0.0.
    """
    return 0.0 if review.approved else 1.0


def score_review_safety(result: CreativeStudioResult) -> float:
    return 1.0 if result.requires_human_review else 0.0


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass
class _PerMetric:
    scores: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0


def run_offline(dataset: Path, thresholds: dict[str, float]) -> EvalReport:
    # The rubrics and the scored set must agree in BOTH directions before anything is scored.
    load_rubrics(RUBRICS).assert_covers(SCORED)
    prove_before_scoring(
        lambda: prove_image_spec_compliance_can_go_red(thresholds["image_spec_compliance"])
    )
    examples = load_golden(dataset)
    service = _make_service()
    agg: dict[str, _PerMetric] = {metric: _PerMetric() for metric in SCORED}
    print(
        f"Running offline eval gate over {len(examples)} golden briefs (CreativeStudioService).\n"
    )
    for ex in examples:
        brief = CreativeBrief(
            topic=ex.topic,
            market=Market(ex.market),
            vertical=Vertical(ex.vertical),
            channel=Channel(ex.channel),
            product=ex.topic,
            offer="a clear offer",
        )
        result = service.generate(brief, actor="eval-bot")
        agg["check_groundedness"].scores.append(score_groundedness(result))
        agg["citation_accuracy"].scores.append(score_citation_accuracy(result))
        agg["review_safety"].scores.append(score_review_safety(result))
        # brand_safety_detection: the studio MUST flag (FAIL) the deliberately bad variant.
        bad_review = service.review(brief, _BAD_VARIANT, actor="eval-bot")
        agg["brand_safety_detection"].scores.append(score_brand_safety_detection(bad_review))
        # The image path, which had no eval coverage at all. Scored through whatever adapter the
        # profile binds, so the managed Imagen path is measured by the same rule as the stub.
        request = ImageRequest(
            prompt=f"A brand-safe illustration for {ex.topic}",
            aspect_ratio="1:1",
            width=1024,
            height=1024,
            market=Market(ex.market),
            vertical=Vertical(ex.vertical),
        )
        agg["image_spec_compliance"].scores.append(
            score_image_spec_compliance(_image_adapter().generate(request), request)
        )

    results = tuple(
        EvalMetricResult(
            metric=metric,
            score=round(agg[metric].mean, 4),
            threshold=thresholds[metric],
            passed=round(agg[metric].mean, 4) >= thresholds[metric],
        )
        for metric in SCORED
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(examples))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    """Promotion verdict via EvaluationGatePort (platform = model-quality-gate, gcp = Gen AI evals).

    Fails closed on the reconciled evaluate + gate result. Refuses to run outside the
    platform/gcp profiles so the offline smoke result is never relabelled a promotion pass.
    """
    from creative_studio.config import Settings, build_container

    settings = Settings.load()
    if settings.profile not in ("platform", "gcp"):
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            "MKT_CREATIVE_PROFILE=platform or gcp "
            f"(got {settings.profile!r}); run --mode smoke for the offline pre-merge check."
        )
    container = build_container(settings)
    gate = container.evaluation
    report = gate.evaluate(str(dataset))
    if not isinstance(report, EvalReport):  # pragma: no cover - defensive
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    gate_passed = bool(gate.gate(str(dataset)))
    return report, gate_passed


def main(argv: list[str] | None = None) -> int:
    """Dispatch --mode via the shared eval_main scaffold (fail-closed exit codes).

    ``--use-gcp`` (the pre-split flag for the production evaluator) is kept as an alias
    for ``--mode gate``.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if "--use-gcp" in args:
        args = [a for a in args if a != "--use-gcp"] + ["--mode", "gate"]
    return eval_main(
        smoke=lambda dataset: run_offline(dataset, load_thresholds_from_rubrics()),
        gate=run_gate,
        default_dataset=DEFAULT_DATASET,
        description="Offline / platform evaluation gate for D3 (A4 / P-08).",
        smoke_label="offline heuristic (no GCP creds)",
        gate_label="promotion gate (EvaluationGatePort: model-quality-gate / Gen AI evals)",
        argv=args,
    )


if __name__ == "__main__":
    raise SystemExit(main())

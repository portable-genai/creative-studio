"""Contract test: the platform evaluation adapter speaks Hrz4's hardened HTTP contract.

Pins the wire shape that the shared **Hrz4 AI Quality / Model-Risk** service expects, so a
drift in the client body (e.g. reverting to a metric-name list, or a GET gate) fails here
rather than on the live service:

* ``POST /v1/evaluations`` with a structured ``target``, a top-level ``dataset_id`` equal to
  ``target.dataset_id``, and ``bundle`` = ``"mkt3-creative"`` (NO metric-name list);
* ``results[]`` from the response parsed into the domain :class:`EvalReport`, but only when
  the response also carries the evidence that makes those numbers mean something later;
* ``gate`` POSTs the same body to ``POST /v1/gate`` and returns a verdict RE-DERIVED from a
  complete promotion decision, never the server's own aggregate boolean.

The response fixtures are large on purpose. The hardened ``agent-eval-kit`` client recomputes
every verdict from the evidence and raises on any contradiction, so a body cannot simply
assert that a promotion passed: each metric row's ``passed`` has to equal
``score >= threshold``, the red-team aggregate has to equal the AND of its rows, and the
top-level verdict has to equal (quality AND attested AND red team). The refusal tests at the
bottom are as much the contract as the happy path, because the shape they reject,
``{"passed": true}`` with nothing behind it, is a promotion certified by nothing.

Uses ``respx`` (a dev dependency) to intercept httpx without any network.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from creative_studio.adapters.platform.remote_evaluation import (
    RemoteEvaluationAdapter,
    RemoteEvaluationError,
)
from creative_studio.config import Settings
from creative_studio.domain.models import EvalReport

_BASE = "https://quality.test"
_DATASET = "eval/data/golden.jsonl"

#: Obviously fictional durable identifiers. Every one is REQUIRED by the hardened parse: scores
#: that name no run, no dataset state and no evaluator cannot be re-derived by anyone reading
#: the promotion record months later, so they are not promotion evidence.
_DIGEST = "sha256:feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface"
_EVALUATOR = "hrz4-ai-quality (FICTIONAL)"
_DATASET_VERSION = "golden@2026-08-01"
_MODEL_CARD_REF = "gs://fictional-hrz4-evidence/model-cards/mkt3-creative.md"
_MRM_REF = "gs://fictional-hrz4-evidence/mrm/mkt3-creative-2026-08.json"

#: Rows are internally CONSISTENT: ``passed`` equals ``score >= threshold`` in every one.
_MIXED_ROWS = [
    {"metric": "brand_safety_detection", "score": 0.95, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.85, "threshold": 0.90, "passed": False},
]

_PASSING_ROWS = [
    {"metric": "brand_safety_detection", "score": 0.95, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.93, "threshold": 0.90, "passed": True},
    {"metric": "claim_substantiation", "score": 0.88, "threshold": 0.85, "passed": True},
]

#: Red-team rows: ``passed`` and ``blocked`` must AGREE (an attack that was not blocked did
#: not pass), and the aggregate must equal the AND of the rows.
_REDTEAM_PASSING = {
    "passed": True,
    "results": [
        {"case": "prompt-injection-01", "passed": True, "blocked": True},
        {"case": "unsubstantiated-claim-01", "passed": True, "blocked": True},
    ],
}


def _eval_body(*, run_id: str, results: list[dict], attested: bool = True) -> dict:
    """A complete evaluation response in the hardened shape.

    ``passed`` is deliberately absent: the client derives it from the rows, and a value that
    disagrees with them is a hard error rather than an override.
    """
    return {
        "results": results,
        "n_examples": 24,
        "run_id": run_id,
        "dataset_version": _DATASET_VERSION,
        "dataset_digest": _DIGEST,
        "evaluator": _EVALUATOR,
        "schema_version": "v1",
        "artifact_refs": [f"gs://fictional-hrz4-evidence/{run_id}/report.json"],
        "attested": attested,
    }


def _gate_body(*, passed: bool, rows: list[dict], attested: bool = True) -> dict:
    """The full promotion decision, at every layer the client checks."""
    return {
        "passed": passed,
        "eval_report": _eval_body(run_id="run-fictional-0001", results=rows, attested=attested),
        "redteam_report": _REDTEAM_PASSING,
        "model_card_ref": _MODEL_CARD_REF,
        "mrm_evidence_ref": _MRM_REF,
    }


def _adapter(monkeypatch: pytest.MonkeyPatch) -> RemoteEvaluationAdapter:
    monkeypatch.setenv("HRZ_QUALITY_URL", _BASE)
    # Default Settings pins reasoning = gemini-3.5-flash, which the target.model must carry.
    return RemoteEvaluationAdapter(Settings())


@respx.mock
def test_evaluate_posts_structured_target_bundle_and_parses_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(
            200, json=_eval_body(run_id="run-fictional-0002", results=_MIXED_ROWS)
        )
    )

    report = _adapter(monkeypatch).evaluate(_DATASET)

    assert route.called
    body = json.loads(route.calls.last.request.content)

    # Structured target with the pinned reasoning model + prompt_version + dataset_id.
    assert body["target"] == {
        "model": "gemini-3.5-flash",
        "prompt_version": "v1",
        "dataset_id": "golden",
        "system": "",
    }
    # Top-level dataset_id MUST equal target.dataset_id.
    assert body["dataset_id"] == body["target"]["dataset_id"] == "golden"
    # Metrics are chosen by bundle ONLY : never a metric-name list.
    assert body["bundle"] == "mkt3-creative"
    assert "metrics" not in body

    # results[] parsed into the domain EvalReport, thresholds passed through unchanged.
    assert isinstance(report, EvalReport)
    assert report.dataset == _DATASET
    assert [(r.metric, r.score, r.threshold, r.passed) for r in report.results] == [
        ("brand_safety_detection", 0.95, 0.80, True),
        ("citation_accuracy", 0.85, 0.90, False),
    ]
    assert report.n_examples == 24
    assert report.passed is False  # one metric failed

    # The durable evidence SURVIVES the adapter. A `_to_domain` mapper rebuilding a
    # locally-declared EvalReport from three fields drops everything below, which is
    # precisely the evidence the client had just validated. Scores that name no run,
    # no dataset state, no evaluator and no artifact cannot be reproduced or attributed by
    # anyone reading the promotion record later, so their loss is the defect, not a detail.
    assert report.run_id == "run-fictional-0002"
    assert report.dataset_version == _DATASET_VERSION
    assert report.dataset_digest == _DIGEST
    assert report.evaluator == _EVALUATOR
    assert report.schema_version == "v1"
    assert report.artifact_refs == ("gs://fictional-hrz4-evidence/run-fictional-0002/report.json",)
    assert report.attested is True


@respx.mock
def test_evaluate_REFUSES_scores_with_no_durable_run_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metric rows alone are a number, not evidence.

    The client enforces the durable identifiers on the plain evaluations path too, not
    only inside ``gate()``. Without a run id, a dataset digest, an evaluator and an artifact
    ref, nobody can later reproduce the score or say which corpus produced it.
    """
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json={"results": _PASSING_ROWS, "n_examples": 24})
    )
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).evaluate(_DATASET)


@respx.mock
def test_evaluate_REFUSES_a_row_whose_verdict_contradicts_its_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row claiming PASS below its own bar is the failure a trusted flag always hides."""
    rows = [{"metric": "brand_safety_detection", "score": 0.41, "threshold": 0.80, "passed": True}]
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_eval_body(run_id="run-fictional-0003", results=rows))
    )
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).evaluate(_DATASET)


@respx.mock
def test_gate_posts_to_v1_gate_and_returns_true_on_a_full_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(passed=True, rows=_PASSING_ROWS))
    )

    assert _adapter(monkeypatch).gate(_DATASET) is True

    assert route.called
    request = route.calls.last.request
    assert request.method == "POST"  # POST, not GET

    body = json.loads(request.content)
    assert body["bundle"] == "mkt3-creative"
    assert body["dataset_id"] == body["target"]["dataset_id"] == "golden"
    assert "metrics" not in body


@respx.mock
def test_gate_returns_false_through_evidence_that_actually_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A FAIL has to be reachable the honest way: a metric that genuinely missed its bar.

    A body claiming ``passed: false`` over evidence that all passed is a contradiction and
    raises, so this fixture fails the citation-accuracy row rather than asserting a verdict.
    """
    respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(passed=False, rows=_MIXED_ROWS))
    )
    assert _adapter(monkeypatch).gate(_DATASET) is False


@respx.mock
def test_gate_REFUSES_a_naked_boolean_with_no_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shape this file used to accept: a verdict with nothing behind it.

    An upstream returning ``{"passed": true}`` for every target is indistinguishable from one
    that evaluated nothing at all, so the refusal is the contract rather than a nuisance.
    """
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json={"passed": True}))
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).gate(_DATASET)


@respx.mock
def test_gate_REFUSES_an_unattested_report_even_when_every_metric_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unattested scores are a draft run, not sign-off, however good the numbers look."""
    respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(
            200, json=_gate_body(passed=True, rows=_PASSING_ROWS, attested=False)
        )
    )
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).gate(_DATASET)


@respx.mock
def test_gate_REFUSES_a_redteam_aggregate_that_contradicts_its_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A red-team summary reporting PASS over a case that was not blocked is a rubber stamp."""
    body = _gate_body(passed=True, rows=_PASSING_ROWS)
    body["redteam_report"] = {
        "passed": True,
        "results": [
            {"case": "prompt-injection-01", "passed": True, "blocked": True},
            {"case": "unsubstantiated-claim-01", "passed": False, "blocked": False},
        ],
    }
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).gate(_DATASET)


@respx.mock
def test_gate_REFUSES_a_decision_with_no_model_card_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model-risk sign-off has to point at something durable, or it points at nothing."""
    body = _gate_body(passed=True, rows=_PASSING_ROWS)
    body["model_card_ref"] = ""
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).gate(_DATASET)


@respx.mock
def test_non_2xx_raises_remote_evaluation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(503, text="unavailable"))

    with pytest.raises(RemoteEvaluationError):
        _adapter(monkeypatch).evaluate(_DATASET)

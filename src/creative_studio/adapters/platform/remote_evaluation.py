"""Remote-platform evaluation adapter : thin HTTP client to model-quality-gate.

At promotion this vertical's quality is checked against the shared **model-quality-gate AI Quality /
model-risk** service (``model-quality-gate``). This adapter implements
:class:`EvaluationGatePort` against model-quality-gate's hardened contract:

* ``evaluate`` -> ``POST /v1/evaluations {target, dataset_id, bundle}`` -> EvalReport.
* ``gate``     -> ``POST /v1/gate {target, dataset_id, bundle}`` -> ``{passed}``.

**Sourced from the shared ``agent-eval-kit`` commons.** The HTTP contract
is ``agent_eval_kit.gate_client.PromotionGateClient``; this adapter configures it (the
registered ``mkt3-creative`` bundle, the reasoning model, and this repo's S2S auth
headers), returns its report UNCHANGED, and re-raises its errors as
:class:`RemoteEvaluationError`.

There is deliberately no ``_to_domain`` mapper here rebuilding a locally-declared ``EvalReport``
from the client's by copying across three fields. Because the domain re-exports the commons type,
such a mapper is a lossy identity function: it drops ``run_id``, ``dataset_version``,
``dataset_digest``, ``evaluator``, ``schema_version``, ``trace_id``, ``correlation_id``,
``artifact_refs`` and ``attested`` -- exactly the durable, attested evidence the client had just
validated, and exactly what anyone reading the promotion record months later needs in order
to say which corpus produced the score and who signed it off.
"""

from __future__ import annotations

from agent_eval_kit.gate_client import GateClientError, PromotionGateClient

from ...config import Settings
from ...domain.errors import CreativeStudioError
from ...domain.models import EvalReport
from ...envread import setting_or_default
from . import _s2s

_DEFAULT_URL = "http://localhost:8084"

#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + bars).
_BUNDLE = "mkt3-creative"
#: Prompt/agent version tag; bump when the prompt corpus changes, or source it from a registry.
_PROMPT_VERSION = "v1"


class RemoteEvaluationError(CreativeStudioError):
    """Raised when the model-quality-gate quality service returns a non-2xx response."""


class RemoteEvaluationAdapter:
    """HTTP client for the model-quality-gate ``model-quality-gate`` service (via
    PromotionGateClient).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = PromotionGateClient(
            setting_or_default("QUALITY_GATE_URL", _DEFAULT_URL),
            bundle=_BUNDLE,
            model=settings.models.reasoning,
            prompt_version=_PROMPT_VERSION,
            auth_headers=lambda: _s2s.headers(),
        )

    def evaluate(self, dataset_path: str) -> EvalReport:
        """Score ``dataset_path`` via model-quality-gate and return the client's report, evidence
        intact.
        """
        try:
            return self._client.evaluate(dataset_path)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc

    def gate(self, target: str) -> bool:
        """Promotion gate: True iff model-quality-gate reports ``target`` passes."""
        try:
            return self._client.gate(target)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc

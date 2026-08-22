"""Observability ports — the A5 (audit/trace) and A4 (eval gate) concerns.

Primary GCP adapters: a **Cloud Logging locked WORM bucket** for immutable audit, **Cloud
Trace via OpenTelemetry** for the reasoning-loop traces, and the **Gen AI evaluation
service** plus the A4 promotion gate for model risk.

Two of the three ports here are RE-EXPORTED from the commons rather than declared. Hand-copied
Protocol bodies drift. Across sixteen repositories that each copy one, the copies disagree by the
time anyone compares them: one drops ``EvaluationGatePort`` entirely, two drop its ``gate`` method
(the half that can refuse a promotion), one returns ``str`` from an audit ``record`` that returns
``None`` everywhere else. A Protocol copied into N repos is N Protocols, and only one of them gets
fixed when a defect is found. So:

* :class:`~hex_service_kit.observability.ObservabilityTracerPort` and its
  :class:`~hex_service_kit.observability.TokenUsage` come from ``hex-service-kit``;
* :class:`~agent_eval_kit.EvaluationGatePort` comes from ``agent-eval-kit``, which is where
  :class:`~agent_eval_kit.report.EvalReport` already lives.

``AuditSinkPort`` stays declared here, deliberately: it is typed in this repo's own vocabulary
(``AuditEvent``), so it is not a member of the shared drift class.
``tests/contract/test_port_parity.py`` asserts object IDENTITY (``is``) against the commons, not
merely ``isinstance``, because a hand-copied look-alike satisfies a runtime_checkable Protocol
and would slip straight back in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_eval_kit import EvaluationGatePort
from hex_service_kit.observability import ObservabilityTracerPort, TokenUsage

from ..domain.models import AuditEvent


@runtime_checkable
class AuditSinkPort(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Write an immutable audit record (WORM)."""
        ...


__all__ = [
    "AuditSinkPort",
    "EvaluationGatePort",
    "ObservabilityTracerPort",
    "TokenUsage",
]

"""Contract tests: the ``onprem`` and ``local`` adapters are structural parity of the ports.

For every port the catalog declares, this iterates the adapter map and, for both the
``onprem`` and ``local`` profiles, imports + constructs the bound class (which must build
cleanly with **no Google Cloud SDK** installed), then asserts:

  1. the constructed instance satisfies its runtime_checkable Protocol (isinstance), and
  2. every method/property the Protocol declares actually exists on the instance.

It additionally proves the two profiles' distinct contracts:

* ``onprem`` is the fail-fast migration target: every method raises ``NotImplementedError``
  (proven on a representative port), and
* ``local`` is a WORKING offline stack: the same ports construct and answer in-process.

This is the proof of the ports-and-adapters / no-lock-in promise: the on-prem migration
target and the offline local stack implement the exact same interface as the managed GCP
stack.
"""

from __future__ import annotations

import importlib
from typing import Protocol, get_type_hints

import pytest

from creative_studio import config, ports
from creative_studio.config import LocalSettings, Settings, instantiate

CONFIG_PATH = "config/settings.yaml"

PORT_PROTOCOLS: dict[str, type] = {
    "copy": ports.CopyGenerationPort,
    "image": ports.ImageGenerationPort,
    "knowledge_base": ports.KnowledgeBasePort,
    "guardrail": ports.GuardrailPort,
    "audit": ports.AuditSinkPort,
    "tracer": ports.ObservabilityTracerPort,
    "evaluation": ports.EvaluationGatePort,
    "agent_registry": ports.AgentRegistryPort,
    "tool_catalog": ports.ToolCatalogPort,
    "identity": ports.IdentityPort,
    "review_router": ports.ReviewRouterPort,
}

# Profiles whose adapters must construct + satisfy the Protocols with no GCP SDK.
SDK_FREE_PROFILES = ("onprem", "local")


def _settings(profile: str) -> Settings:
    base = Settings.load(CONFIG_PATH)
    return Settings(
        project_id=base.project_id,
        region=base.region,
        profile=profile,
        vertical=base.vertical,
        market=base.market,
        channel=base.channel,
        models=base.models,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        markets=base.markets,
        adapters=base.adapters,
    )


def _protocol_members(protocol: type) -> set[str]:
    members = set(getattr(protocol, "__protocol_attrs__", set()))
    if not members:
        members |= set(get_type_hints(protocol).keys())
        for name in dir(protocol):
            if name.startswith("_"):
                continue
            members.add(name)
    return {m for m in members if not m.startswith("_")}


def test_every_port_has_an_explicit_binding_for_every_profile() -> None:
    settings = Settings.load(CONFIG_PATH)
    for port_name in PORT_PROTOCOLS:
        binding = settings.adapters.get(port_name, {})
        missing = set(config.RUNTIME_PROFILES) - set(binding)
        assert not missing, f"port '{port_name}' has no explicit bindings for {sorted(missing)}"


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_satisfies_protocol(profile: str, port_name: str) -> None:
    settings = _settings(profile)
    protocol = PORT_PROTOCOLS[port_name]
    dotted = settings.adapters[port_name][profile]

    adapter = instantiate(dotted, settings)

    assert isinstance(adapter, protocol), (
        f"{dotted} does not structurally satisfy {protocol.__name__}"
    )

    members = _protocol_members(protocol)
    declared = set().union(*(vars(klass) for klass in type(adapter).__mro__))
    for member in members:
        assert member in declared, (
            f"{dotted} is missing port method/attr '{member}' of {protocol.__name__}"
        )


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_constructs_with_single_settings_arg(profile: str, port_name: str) -> None:
    """The build contract: every adapter is ``Adapter(settings: Settings)``."""
    settings = _settings(profile)
    dotted = settings.adapters[port_name][profile]
    module_path, _, class_name = dotted.partition(":")

    cls = getattr(importlib.import_module(module_path), class_name)
    instance = cls(settings)
    assert instance is not None


def test_onprem_copy_fails_fast() -> None:
    """The on-prem stubs are fail-fast: a representative port raises NotImplementedError."""
    from creative_studio.domain.models import (
        Channel,
        CreativeBrief,
        Market,
        Vertical,
    )

    settings = _settings("onprem")
    adapter = instantiate(settings.adapters["copy"]["onprem"], settings)
    with pytest.raises(NotImplementedError):
        adapter.generate_variants(
            CreativeBrief(
                topic="x", market=Market.SG, vertical=Vertical.BANKING, channel=Channel.EMAIL
            )
        )


def test_local_copy_returns_real_variants() -> None:
    """The local stack is WORKING: copy generation returns real variants offline."""
    from creative_studio.domain.models import (
        Channel,
        CreativeBrief,
        Market,
        Vertical,
    )

    settings = _settings("local")
    adapter = instantiate(settings.adapters["copy"]["local"], settings)
    variants = adapter.generate_variants(
        CreativeBrief(
            topic="savings",
            market=Market.SG,
            vertical=Vertical.BANKING,
            channel=Channel.EMAIL,
            offer="4.10% p.a.",
        )
    )
    assert variants, "local copy returned no variants"
    assert all(v.headline for v in variants)


def test_shared_types_are_the_commons_objects_not_look_alike_copies() -> None:
    """The drift guard the structural tests above CANNOT provide.

    ``isinstance`` against a ``runtime_checkable`` Protocol passes for a hand-copied look-alike:
    that is the whole point of structural typing, and it is exactly why sixteen repositories each
    grew their own ``ObservabilityTracerPort`` / ``TokenUsage`` / ``EvalReport`` and drifted apart
    with every test still green. ``is`` does not pass for a copy. So this asserts object IDENTITY:
    re-declaring any of these locally, however faithfully, fails here.

    ``AuditSinkPort`` is deliberately absent. It is typed in this repo's own ``AuditEvent``
    vocabulary, so it is declared here on purpose rather than by drift.
    """
    import agent_eval_kit
    import hex_service_kit.observability as commons_observability

    from creative_studio.domain import models

    assert ports.ObservabilityTracerPort is commons_observability.ObservabilityTracerPort
    assert ports.TokenUsage is commons_observability.TokenUsage
    assert models.TokenUsage is commons_observability.TokenUsage
    assert ports.EvaluationGatePort is agent_eval_kit.EvaluationGatePort
    assert models.EvalReport is agent_eval_kit.EvalReport
    assert models.EvalMetricResult is agent_eval_kit.EvalMetricResult


def test_the_commons_eval_report_keeps_this_repo_s_fail_closed_rule() -> None:
    """Re-exporting must not silently WEAKEN a local guard, so the guard is re-proven here.

    The naive ``all(())`` is vacuously True, and ``eval/run_eval.py`` exits 0 on ``passed``, so a
    report that scored nothing would certify a promotion. This repo added the two extra guards;
    the commons type carries the same expression, and this test is what would catch the day it
    stops doing so.
    """
    from creative_studio.domain.models import EvalMetricResult, EvalReport

    row = EvalMetricResult(metric="groundedness", score=0.99, threshold=0.80, passed=True)
    assert EvalReport(dataset="d", results=(), n_examples=0).passed is False
    assert EvalReport(dataset="d", results=(), n_examples=12).passed is False
    assert EvalReport(dataset="d", results=(row,), n_examples=0).passed is False
    assert EvalReport(dataset="d", results=(row,), n_examples=12).passed is True


def test_all_protocols_are_runtime_checkable() -> None:
    for protocol in PORT_PROTOCOLS.values():
        assert issubclass(protocol, Protocol)  # type: ignore[arg-type]
        assert getattr(protocol, "_is_runtime_protocol", False), (
            f"{protocol.__name__} must be @runtime_checkable"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

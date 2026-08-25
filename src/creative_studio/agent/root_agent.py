"""Root ADK agent for the D3 Creative Studio system, hosted on Agent Runtime.

This is the agent the Gemini Enterprise Agent Platform **Agent Runtime** (ex-Agent Engine)
hosts. It wires together:

* the creative-studio domain-service :class:`FunctionTool` wrappers (``agent.tools``:
  ``generate_creative``, ``review_variant``),
* an optional governed **MCP** toolset (``MCPToolset``) when ``MKT_CREATIVE_MCP_SERVER_URL`` is
  set, so the same least-privilege catalog declared in ``adapters/gcp/mcp_tool_catalog.py`` can
  be served from an out-of-process MCP server (rule R4),
* the defense-in-depth model-boundary **callbacks** (guardrail + audit; ``agent.callbacks``),
  and
* the reasoning model ``settings.models.reasoning`` (``gemini-3.5-flash``) at ``thinking=high``
  (SPEC §3).

D3 grounds on the brand-guideline corpus via File Search (Hrz2), not public-web research, so it
carries no ``google_search`` grounding sub-agent.

ADK convention is honoured two ways: the module exposes a ``root_agent`` attribute (what ADK /
``adk web`` / Agent Runtime discover by default) **and** a ``build_root_agent(settings)`` factory
for explicit, test-friendly construction.

Import safety (SPEC §4): ``google.adk`` is heavy and GCP-only. All ADK imports are quarantined
inside :func:`build_root_agent`, and the module-level ``root_agent`` is built lazily via
:class:`_LazyRootAgent` so merely importing this module never requires ADK (the local / on-prem
/ test profile imports it cleanly).

Exposing over A2A: ``to_a2a(build_root_agent(settings))`` produces an A2A app that serves
``/.well-known/agent-card.json`` (see :func:`to_a2a_app` and ``agent.agent_card``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Settings
from ..envread import read_env_setting

if TYPE_CHECKING:  # pragma: no cover - typing only
    from google.adk.agents import LlmAgent

ROOT_AGENT_NAME = "creative_studio_agent"
MCP_SERVER_URL_ENV = "MKT_CREATIVE_MCP_SERVER_URL"

_ROOT_INSTRUCTION = (
    "You are the D3 Creative Studio agent for a bank or online retailer's brand / creative "
    "team. You draft on-brand ad copy and image variants and review them, generic across "
    "banking and online retail and the JP / AU / SG markets.\n\n"
    "Routing:\n"
    "- 'Create ad copy for <theme>' / generate variants -> call generate_creative.\n"
    "- 'Is this variant compliant?' / review an external draft -> call review_variant.\n\n"
    "Rules:\n"
    "- You draft copy, but the deterministic engines decide brand-safety and advertising-claim "
    "compliance. Never assert a variant is compliant yourself; report the check findings, each "
    "with its citation.\n"
    "- Creative is a consequential output: always state that it requires human review "
    "(maker-checker) before anything ships.\n"
    "- Final publication is governed by Mkt6 and screened by the Hrz1 guardrail (rules R7 / "
    "P-13); flag any variant that fails a claim or brand check rather than shipping it."
)


def build_root_agent(settings: Settings | None = None) -> LlmAgent:
    """Construct the root ADK ``LlmAgent`` for the agent.

    Wires the creative-studio FunctionTools, an optional governed ``MCPToolset``, and the
    guardrail / audit callbacks built from the DI container. The reasoning model runs at
    ``thinking=high`` (SPEC §3). All ADK imports are local to this function (SPEC §4).
    """
    settings = settings or Settings.load()

    from google.adk.agents import LlmAgent
    from google.genai import types

    from ..config import build_container
    from .callbacks import build_callbacks, configure_span_privacy
    from .tools import build_function_tools

    configure_span_privacy()

    container = build_container(settings)
    callbacks = build_callbacks(container)

    tools: list[Any] = list(build_function_tools())

    # Optional out-of-process governed MCP toolset (rule R4). Only wired when an MCP server URL
    # is configured; the in-process FunctionTools above are the default surface.
    mcp_toolset = _build_mcp_toolset()
    if mcp_toolset is not None:
        tools.append(mcp_toolset)

    generate_content_config = types.GenerateContentConfig(
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_budget=-1),
    )

    return LlmAgent(
        name=ROOT_AGENT_NAME,
        model=settings.models.reasoning,
        description=(
            "Creative studio agent: drafts on-brand ad copy and image variants and reviews "
            "them against per-market advertising-claim rules, brand guidelines and policy for "
            "a bank or online retailer across JP / AU / SG."
        ),
        instruction=_ROOT_INSTRUCTION,
        tools=tools,
        generate_content_config=generate_content_config,
        before_model_callback=callbacks["before_model_callback"],
        after_model_callback=callbacks["after_model_callback"],
        after_agent_callback=callbacks["after_agent_callback"],
    )


# ADK renamed its SSE/HTTP connection-params class across releases; resolve whichever this ADK
# exposes so the wiring survives a version bump (the toolset itself is stable).
_MCP_CONNECTION_PARAM_CLASSES = (
    "SseConnectionParams",
    "SseServerParams",
    "StreamableHTTPConnectionParams",
)


def _build_mcp_toolset() -> Any | None:
    """Build a governed ``MCPToolset`` from ``MKT_CREATIVE_MCP_SERVER_URL``, or ``None``.

    Realizes the wiring the ``mcp_tool_catalog`` adapter documents: the governed,
    least-privilege catalog declared in ``adapters/gcp/mcp_tool_catalog.py`` (MCP 2026-07-28) is
    served by an out-of-process MCP server, and the agent reaches it through an ``MCPToolset``.
    Offline there is no MCP server, so the in-process FunctionTools are the surface and this
    returns ``None``. ADK / MCP imports are lazy (SPEC §4).
    """
    server_url = read_env_setting(MCP_SERVER_URL_ENV).value
    if not server_url:
        return None

    from google.adk.tools.mcp_tool import mcp_session_manager
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

    params_cls = next(
        (
            cls
            for cls in (
                getattr(mcp_session_manager, n, None) for n in _MCP_CONNECTION_PARAM_CLASSES
            )
            if cls is not None
        ),
        None,
    )
    if params_cls is None:  # pragma: no cover - depends on the installed ADK build
        raise RuntimeError(
            "No known MCP connection-params class found in this google-adk build; "
            f"looked for {', '.join(_MCP_CONNECTION_PARAM_CLASSES)}."
        )
    return MCPToolset(connection_params=params_cls(url=server_url))


def to_a2a_app(settings: Settings | None = None) -> Any:
    """Expose the root agent as an A2A app (serves ``/.well-known/agent-card.json``).

    Thin wrapper over ADK's ``to_a2a`` so peers can discover and call the agent over A2A v1.0
    (SPEC §3/§6). ADK is imported lazily (SPEC §4).
    """
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    return to_a2a(build_root_agent(settings))


class _LazyRootAgent:
    """Lazy proxy so ``import root_agent`` never pulls in ADK.

    ADK discovers a module-level ``root_agent``. We expose that name without forcing ADK to be
    importable at module import time (local / on-prem / test profile, SPEC §4). The real
    ``LlmAgent`` is built on first attribute access and cached.
    """

    __slots__ = ("_agent",)

    def __init__(self) -> None:
        self._agent: LlmAgent | None = None

    def _resolve(self) -> LlmAgent:
        if self._agent is None:
            self._agent = build_root_agent()
        return self._agent

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        state = "unbuilt" if self._agent is None else "built"
        return f"<LazyRootAgent {ROOT_AGENT_NAME} ({state})>"


# ADK convention: a module-level ``root_agent`` the runtime discovers. Lazy so importing this
# module is safe without ADK installed (SPEC §4).
root_agent = _LazyRootAgent()

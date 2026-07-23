"""Product-neutral Agent construction and bootstrap result contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from loushang.harness.bootstrap import (
    BootstrapActivationPlan,
    BootstrapActivationRuntime,
)
from loushang.harness.config.activation import ConfigActivationStep
from loushang.harness.config.agent import ControlConfig
from loushang.harness.session.bootstrap_utils import (
    NoToolsMode,
    resolve_initial_active_tool_names,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry

SettingsT = TypeVar("SettingsT")
ModelRegistryT = TypeVar("ModelRegistryT")
ResourceLoaderT = TypeVar("ResourceLoaderT")
DiagnosticsT = TypeVar("DiagnosticsT")
ExecServiceT = TypeVar("ExecServiceT")
ServicesT = TypeVar("ServicesT")
BundleT = TypeVar("BundleT")
ExtensionT = TypeVar("ExtensionT")
DiagnosticRecordT = TypeVar("DiagnosticRecordT")
SessionT = TypeVar("SessionT")
AuditT = TypeVar("AuditT")
AgentT = TypeVar("AgentT")
RegistryT = TypeVar("RegistryT")
ActivationContextT = TypeVar("ActivationContextT")


@dataclass(frozen=True)
class StandardAgentSessionActivationEffects(Generic[ActivationContextT]):
    """Product effects bound to the standard Agent session activation order."""

    startup_checks: Callable[[object, ActivationContextT], object]
    package_sources: Callable[[object, ActivationContextT], object]
    resource_roots: Callable[[object, ActivationContextT], object]
    resources: Callable[[object, ActivationContextT], object]
    extensions: Callable[[object, ActivationContextT], object]
    cwd_audit: Callable[[object, ActivationContextT], object]
    model_registry: Callable[[object, ActivationContextT], object]


def standard_agent_session_activation_plan(
    effects: StandardAgentSessionActivationEffects[ActivationContextT],
) -> BootstrapActivationPlan[ControlConfig, ActivationContextT]:
    """Compose standard Agent startup capabilities over the shared graph runtime."""

    return BootstrapActivationPlan(
        steps=(
            ConfigActivationStep(
                "startup_checks",
                select=lambda config: config.package_roots,
                apply=effects.startup_checks,
            ),
            ConfigActivationStep(
                "package_sources",
                select=lambda config: config.package_sources,
                apply=effects.package_sources,
                depends_on=("startup_checks",),
            ),
            ConfigActivationStep(
                "resource_roots",
                select=lambda config: (
                    config.package_roots,
                    config.package_sources,
                    config.plugin_sources,
                    config.disabled_plugins,
                    config.resource_roots,
                ),
                apply=effects.resource_roots,
                depends_on=("package_sources",),
            ),
            ConfigActivationStep(
                "resources",
                select=lambda config: config.disabled_skills,
                apply=effects.resources,
                depends_on=("resource_roots",),
            ),
            ConfigActivationStep(
                "extensions",
                select=lambda config: (
                    config.disabled_skills,
                    config.disabled_plugins,
                ),
                apply=effects.extensions,
                depends_on=("resources",),
            ),
            ConfigActivationStep(
                "cwd_audit",
                select=lambda config: config.resource_roots,
                apply=effects.cwd_audit,
                depends_on=("extensions",),
            ),
            ConfigActivationStep(
                "model_registry",
                select=lambda config: config.enabled_models,
                apply=effects.model_registry,
                depends_on=("cwd_audit",),
            ),
        )
    )


def activate_standard_agent_session_configuration(
    config: ControlConfig,
    context: ActivationContextT,
    *,
    effects: StandardAgentSessionActivationEffects[ActivationContextT],
) -> ActivationContextT:
    """Execute the standard activation plan and propagate its first failure."""

    result = BootstrapActivationRuntime(
        standard_agent_session_activation_plan(effects)
    ).activate(config, context)
    if result.report.failures:
        raise result.report.failures[0].error
    return result.context


@dataclass(frozen=True)
class BootstrapServices(
    Generic[SettingsT, ModelRegistryT, ResourceLoaderT, DiagnosticsT, ExecServiceT]
):
    """Product service handles shared by a session bootstrap."""

    settings_manager: SettingsT
    model_registry: ModelRegistryT
    resource_loader: ResourceLoaderT
    diagnostics_service: DiagnosticsT
    exec_service: ExecServiceT | None = None


@dataclass(frozen=True)
class AgentSessionServices(
    Generic[ServicesT, BundleT, ExtensionT, DiagnosticRecordT]
):
    """Cwd-bound services and results of the shared resource bootstrap."""

    cwd: str
    services: ServicesT
    resource_bundle: BundleT | None = None
    extension_runner: ExtensionT | None = None
    diagnostics: tuple[DiagnosticRecordT, ...] = ()

    @property
    def settings_manager(self) -> object:
        return getattr(self.services, "settings_manager")

    @property
    def model_registry(self) -> object:
        return getattr(self.services, "model_registry")

    @property
    def resource_loader(self) -> object:
        return getattr(self.services, "resource_loader")

    @property
    def diagnostics_service(self) -> object:
        return getattr(self.services, "diagnostics_service")

    @property
    def exec_service(self) -> object:
        return getattr(self.services, "exec_service")


@dataclass(frozen=True)
class CreateAgentSessionResult(Generic[SessionT, BundleT, DiagnosticRecordT, AuditT]):
    """Product session plus the shared bootstrap outputs."""

    session: SessionT
    resource_bundle: BundleT | None
    diagnostics: tuple[DiagnosticRecordT, ...]
    cwd_bound_services_audit: AuditT | None = None


@dataclass(frozen=True)
class AgentBootstrapRequest:
    """Neutral values needed to construct one Agent instance."""

    session_id: str
    system_prompt: str
    thinking_level: object
    model: object | None
    convert_to_llm: Callable[..., object]
    steering_mode: object
    follow_up_mode: object
    thinking_budgets: object
    max_retry_delay_ms: int | None
    stream_fn: Callable[..., object] | None = None


class AgentBootstrapRuntime(Generic[AgentT, SessionT]):
    """Construct an Agent, then let the Product create its session facade."""

    def construct(
        self,
        request: AgentBootstrapRequest,
        *,
        agent_factory: Callable[..., AgentT],
        session_factory: Callable[[AgentT], SessionT],
    ) -> SessionT:
        initial_state: dict[str, object] = {
            "system_prompt": request.system_prompt,
            "thinking_level": request.thinking_level,
            "tools": [],
        }
        if request.model is not None:
            initial_state["model"] = request.model

        agent_kwargs: dict[str, object] = {
            "initial_state": initial_state,
            "session_id": request.session_id,
            "convert_to_llm": request.convert_to_llm,
            "steering_mode": request.steering_mode,
            "follow_up_mode": request.follow_up_mode,
            "thinking_budgets": request.thinking_budgets,
            "max_retry_delay_ms": request.max_retry_delay_ms,
        }
        if request.stream_fn is not None:
            agent_kwargs["stream_fn"] = request.stream_fn

        agent = agent_factory(**agent_kwargs)
        setattr(agent, "session_id", request.session_id)
        return session_factory(agent)


@dataclass(frozen=True)
class AgentSessionConstructionRequest(Generic[BundleT, RegistryT]):
    """Inputs for the shared tool and Agent construction pipeline."""

    session_id: str
    base_prompt: str
    resolved_prompt: str
    thinking_level: object
    model: object | None
    convert_to_llm: Callable[..., object]
    steering_mode: object
    follow_up_mode: object
    thinking_budgets: object
    max_retry_delay_ms: int | None
    stream_fn: Callable[..., object] | None
    resource_bundle: BundleT
    tools: Sequence[object] | None
    tool_registry: RegistryT | None
    allowed_tool_names: Sequence[str] | None
    active_tool_names: Sequence[str] | None
    no_tools_mode: NoToolsMode | None


class AgentSessionConstructionRuntime(Generic[AgentT, SessionT, BundleT, RegistryT]):
    """Compose shared tool registration and Agent construction steps."""

    def construct(
        self,
        request: AgentSessionConstructionRequest[BundleT, RegistryT],
        *,
        agent_factory: Callable[..., AgentT],
        register_extension_tools: Callable[
            [BundleT, RegistryT | None], tuple[BundleT, RegistryT | None, Sequence[object]]
        ],
        record_extension_diagnostics: Callable[[Sequence[object]], None],
        session_factory: Callable[
            [AgentT, BundleT, RegistryT | None, list[str] | None, str, NoToolsMode | None],
            SessionT,
        ],
    ) -> SessionT:
        resolved_registry = request.tool_registry
        allowed_tool_names = (
            set(request.allowed_tool_names)
            if request.allowed_tool_names is not None
            else None
        )
        if request.no_tools_mode == "all":
            allowed_tool_names = set()
        if resolved_registry is None and request.tools:
            resolved_registry = WorkspaceToolRegistry()
            for tool in request.tools:
                resolved_registry.register_tool(tool)

        resource_bundle, resolved_registry, extension_diagnostics = (
            register_extension_tools(request.resource_bundle, resolved_registry)
        )
        record_extension_diagnostics(extension_diagnostics)
        if request.no_tools_mode == "all" and resolved_registry is None:
            resolved_registry = WorkspaceToolRegistry()
        resolved_active_tool_names = resolve_initial_active_tool_names(
            active_tool_names=(
                list(request.active_tool_names)
                if request.active_tool_names is not None
                else None
            ),
            allowed_tool_names=allowed_tool_names,
            no_tools_mode=request.no_tools_mode,
            tool_registry=resolved_registry,
        )

        return AgentBootstrapRuntime[AgentT, SessionT]().construct(
            AgentBootstrapRequest(
                session_id=request.session_id,
                system_prompt=request.resolved_prompt,
                thinking_level=request.thinking_level,
                model=request.model,
                convert_to_llm=request.convert_to_llm,
                steering_mode=request.steering_mode,
                follow_up_mode=request.follow_up_mode,
                thinking_budgets=request.thinking_budgets,
                max_retry_delay_ms=request.max_retry_delay_ms,
                stream_fn=request.stream_fn,
            ),
            agent_factory=agent_factory,
            session_factory=lambda agent: session_factory(
                agent,
                resource_bundle,
                resolved_registry,
                resolved_active_tool_names,
                request.base_prompt,
                request.no_tools_mode,
            ),
        )


__all__ = [
    "AgentBootstrapRequest",
    "AgentBootstrapRuntime",
    "AgentSessionConstructionRequest",
    "AgentSessionConstructionRuntime",
    "AgentSessionServices",
    "BootstrapServices",
    "CreateAgentSessionResult",
    "StandardAgentSessionActivationEffects",
    "activate_standard_agent_session_configuration",
    "standard_agent_session_activation_plan",
]

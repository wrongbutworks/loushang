"""Product-neutral Agent construction and bootstrap result contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.bootstrap import (
    BootstrapActivationPlan,
    BootstrapActivationRuntime,
    StandardExtensionRuntime,
    create_standard_resource_bootstrap_runtime,
    register_resource_extension_tools,
)
from loushang.harness.capabilities.prompt_assembly import assemble_prompt
from loushang.harness.config.activation import ConfigActivationStep
from loushang.harness.config.agent import ControlConfig, SettingsManager
from loushang.harness.diagnostics.service import (
    DiagnosticsService,
    run_standard_startup_checks,
)
from loushang.harness.diagnostics.types import StartupCheckResult
from loushang.harness.model_catalog import ModelCatalog
from loushang.harness.resources.activation import SkillActivationRuntime
from loushang.harness.resources.loader import ResourceLoader
from loushang.harness.resources.packages.catalog_diagnostics import (
    record_package_lockfile_diagnostics,
)
from loushang.harness.resources.packages.materializer import PackageMaterializer
from loushang.harness.resources.packages.roots import (
    configure_resource_loader_roots,
)
from loushang.harness.resources.packages.source_resolver import (
    PackageSourceResolver,
)
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session.bootstrap_utils import (
    NoToolsMode,
    normalize_no_tools,
    resolve_base_system_prompt,
    resolve_initial_active_tool_names,
)
from loushang.harness.session.cwd_audit import (
    CwdBoundServicesAudit,
    audit_cwd_bound_services,
    project_root_from_settings_base,
    record_cwd_bound_services_audit,
)
from loushang.harness.session.model_resolution import (
    resolve_session_model,
    scoped_models_from_patterns,
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

ExtensionFlagValues = Mapping[str, bool | str]
ExtensionRuntimeFactory = Callable[[ResourceBundle], StandardExtensionRuntime]
SourceIdentityCheck = Callable[[str], StartupCheckResult]


@dataclass(frozen=True, slots=True)
class StandardAgentSessionConfigurationRequest:
    """Concrete shared services for one standard Agent session activation."""

    settings: ControlConfig
    settings_manager: SettingsManager
    model_registry: ModelCatalog
    resource_loader: ResourceLoader
    diagnostics_service: DiagnosticsService
    package_materializer: PackageMaterializer
    skill_activation_runtime: SkillActivationRuntime
    session_id: str
    cwd: str
    create_extension_runtime: ExtensionRuntimeFactory
    source_identity_check: SourceIdentityCheck
    extension_flag_values: ExtensionFlagValues | None = None


@dataclass(frozen=True, slots=True)
class StandardAgentSessionConfigurationResult:
    resource_bundle: ResourceBundle
    extension_runtime: StandardExtensionRuntime
    cwd_bound_services_audit: CwdBoundServicesAudit


@dataclass
class _StandardAgentSessionConfigurationContext:
    request: StandardAgentSessionConfigurationRequest
    resource_bundle: ResourceBundle | None = None
    extension_runtime: StandardExtensionRuntime | None = None
    cwd_bound_services_audit: CwdBoundServicesAudit | None = None


class StandardAgentSessionConfigurationRuntime:
    """Bind standard Harness resource services to the activation graph."""

    def configure(
        self,
        request: StandardAgentSessionConfigurationRequest,
    ) -> StandardAgentSessionConfigurationResult:
        context = _StandardAgentSessionConfigurationContext(request=request)
        activate_standard_agent_session_configuration(
            request.settings,
            context,
            effects=StandardAgentSessionActivationEffects(
                startup_checks=self._startup_checks,
                package_sources=self._package_sources,
                resource_roots=self._resource_roots,
                resources=self._resources,
                extensions=self._extensions,
                cwd_audit=self._cwd_audit,
                model_registry=self._model_registry,
            ),
        )
        if context.resource_bundle is None:
            raise RuntimeError("Session resources have not been configured.")
        if context.extension_runtime is None:
            raise RuntimeError("Session extensions have not been configured.")
        if context.cwd_bound_services_audit is None:
            raise RuntimeError("Session cwd-bound services have not been audited.")
        return StandardAgentSessionConfigurationResult(
            resource_bundle=context.resource_bundle,
            extension_runtime=context.extension_runtime,
            cwd_bound_services_audit=context.cwd_bound_services_audit,
        )

    @staticmethod
    def _startup_checks(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        record_package_lockfile_diagnostics(
            request.package_materializer.get_lockfile_diagnostics(),
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        )
        run_standard_startup_checks(
            request.diagnostics_service,
            cwd=request.cwd,
            package_roots=request.settings.package_roots,
            additional_checks=(lambda: request.source_identity_check(request.cwd),),
            session_id=request.session_id,
        )

    @staticmethod
    def _package_sources(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        PackageSourceResolver(
            settings_manager=request.settings_manager,
            materializer=request.package_materializer,
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        ).resolve_configured_sources_sync(
            missing_source_action="install",
            phase="startup",
        )

    @staticmethod
    def _resource_roots(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        configure_resource_loader_roots(
            resource_loader=request.resource_loader,
            settings_manager=request.settings_manager,
            materializer=request.package_materializer,
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        )

    @staticmethod
    def _resources(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        result = create_standard_resource_bootstrap_runtime(
            create_extension_runtime=request.create_extension_runtime,
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        ).discover(
            loader=request.resource_loader,
            cwd=request.cwd,
            transform_bundle=lambda bundle: request.skill_activation_runtime.apply(
                bundle,
                request.settings.disabled_skills,
            ),
        )
        request.diagnostics_service.record_many(result.diagnostics)
        context.resource_bundle = result.resource_bundle

    @staticmethod
    def _extensions(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        if context.resource_bundle is None:
            raise RuntimeError("Session resources have not been configured.")
        result = create_standard_resource_bootstrap_runtime(
            create_extension_runtime=request.create_extension_runtime,
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        ).activate_extensions(
            resource_bundle=context.resource_bundle,
            extension_flags=request.extension_flag_values,
            transform_bundle=lambda bundle: request.skill_activation_runtime.apply(
                bundle,
                request.settings.disabled_skills,
            ),
        )
        request.diagnostics_service.record_many(result.flag_diagnostics)
        request.diagnostics_service.record_many(result.extension_diagnostics)
        context.resource_bundle = result.resource_bundle
        context.extension_runtime = result.extension_runtime

    @staticmethod
    def _cwd_audit(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        if context.resource_bundle is None:
            raise RuntimeError("Session resources have not been configured.")
        audit = audit_cwd_bound_services(
            session_cwd=request.cwd,
            project_root=project_root_from_settings_base(
                request.settings_manager.project_base_dir
            ),
            resource_cwd=context.resource_bundle.cwd,
        )
        record_cwd_bound_services_audit(
            audit,
            diagnostics_service=request.diagnostics_service,
            session_id=request.session_id,
        )
        context.cwd_bound_services_audit = audit

    @staticmethod
    def _model_registry(
        selection: object,
        context: _StandardAgentSessionConfigurationContext,
    ) -> None:
        del selection
        request = context.request
        if context.resource_bundle is None:
            raise RuntimeError("Session resources have not been configured.")
        project_root = (
            context.resource_bundle.agents_path.parent
            if context.resource_bundle.agents_path is not None
            else Path(request.cwd)
        )
        request.model_registry.reload_if_project_layer(
            user_dir=Path.home() / ".loushang" / "models",
            project_dir=project_root / ".loushang" / "models",
        )


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
class AgentSessionServices(Generic[ServicesT, BundleT, ExtensionT, DiagnosticRecordT]):
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
            [BundleT, RegistryT | None],
            tuple[BundleT, RegistryT | None, Sequence[object]],
        ],
        record_extension_diagnostics: Callable[[Sequence[object]], None],
        session_factory: Callable[
            [
                AgentT,
                BundleT,
                RegistryT | None,
                list[str] | None,
                str,
                NoToolsMode | None,
            ],
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


@dataclass(frozen=True)
class AgentProductConstructionPorts(Generic[BundleT, ExtensionT, RegistryT]):
    """Product callbacks around the standard configured Agent construction."""

    activate_resources: Callable[[BundleT], object]
    prompt_section_composer: object
    tool_pack_composer: object
    list_tool_definitions: Callable[[ExtensionT], Sequence[object]]
    get_tool_source_info: Callable[[ExtensionT, str], object | None]
    dispose_capabilities: Callable[[], None]


@dataclass(frozen=True)
class AgentProductConstructionRequest(
    Generic[AgentT, SessionT, BundleT, ExtensionT, RegistryT]
):
    configuration: StandardAgentSessionConfigurationRequest
    ports: AgentProductConstructionPorts[BundleT, ExtensionT, RegistryT]
    default_system_prompt: str
    explicit_system_prompt: str | None
    append_system_prompt: Sequence[str]
    model: object | None
    thinking_level: object
    tools: Sequence[object] | None
    tool_registry: RegistryT | None
    allowed_tool_names: Sequence[str] | None
    active_tool_names: Sequence[str] | None
    no_tools: NoToolsMode | bool | None
    stream_fn: Callable[..., object] | None
    convert_to_llm: Callable[..., object]
    agent_factory: Callable[..., AgentT]
    session_factory: Callable[
        [
            AgentT,
            BundleT,
            ExtensionT,
            RegistryT | None,
            list[str] | None,
            str,
            NoToolsMode | None,
        ],
        SessionT,
    ]
    on_default_model_unavailable: Callable[[object, Exception, str], None]
    set_scoped_models: Callable[[SessionT, Sequence[object]], None]
    product_tool_pack_id: str = "product.registry"
    extension_tool_pack_id: str = "product.extensions"


@dataclass(frozen=True)
class AgentProductConstructionResult(Generic[SessionT]):
    session: SessionT
    configuration: StandardAgentSessionConfigurationResult


class AgentProductConstructionRuntime(
    Generic[AgentT, SessionT, BundleT, ExtensionT, RegistryT]
):
    """Compose existing configuration, prompt, model, tool, and Agent owners."""

    def construct(
        self,
        request: AgentProductConstructionRequest[
            AgentT,
            SessionT,
            BundleT,
            ExtensionT,
            RegistryT,
        ],
    ) -> AgentProductConstructionResult[SessionT]:
        try:
            configuration = StandardAgentSessionConfigurationRuntime().configure(
                request.configuration
            )
            resource_bundle = configuration.resource_bundle
            extension_runtime = configuration.extension_runtime
            settings = request.configuration.settings
            base_prompt = resolve_base_system_prompt(
                explicit_prompt=request.explicit_system_prompt,
                resource_loader=request.configuration.resource_loader,
                configured_prompt=settings.system_prompt,
                default_prompt=request.default_system_prompt,
                append_fragments=request.append_system_prompt,
            )
            resolved_prompt = assemble_prompt(
                base_prompt=base_prompt,
                resource_bundle=resource_bundle,
                resource_activation=request.ports.activate_resources(resource_bundle),
                prompt_section_composer=request.ports.prompt_section_composer,
            ).system_prompt
            resolved_model = resolve_session_model(
                request.model,
                default_selection=settings.default_model,
                build_model=request.configuration.model_registry.build_model,
                endpoint_lookup=(
                    request.configuration.model_registry.ai_registry.get_endpoint
                ),
                on_default_unavailable=request.on_default_model_unavailable,
            )

            def register_extension_tools(
                bundle: BundleT,
                registry: RegistryT | None,
            ) -> tuple[BundleT, RegistryT | None, Sequence[object]]:
                return register_resource_extension_tools(
                    extension_runtime=extension_runtime,
                    resource_bundle=bundle,
                    tool_registry=registry,
                    pack_composer=request.ports.tool_pack_composer,
                    list_tool_definitions=request.ports.list_tool_definitions,
                    get_tool_source_info=request.ports.get_tool_source_info,
                    product_pack_id=request.product_tool_pack_id,
                    extension_pack_id=request.extension_tool_pack_id,
                )

            session = AgentSessionConstructionRuntime[
                AgentT,
                SessionT,
                BundleT,
                RegistryT,
            ]().construct(
                AgentSessionConstructionRequest(
                    session_id=request.configuration.session_id,
                    base_prompt=base_prompt,
                    resolved_prompt=resolved_prompt,
                    thinking_level=request.thinking_level,
                    model=resolved_model,
                    convert_to_llm=request.convert_to_llm,
                    steering_mode=settings.steering_mode,
                    follow_up_mode=settings.follow_up_mode,
                    thinking_budgets=settings.thinking_budgets,
                    max_retry_delay_ms=settings.retry.provider_max_retry_delay_ms,
                    stream_fn=request.stream_fn,
                    resource_bundle=resource_bundle,
                    tools=request.tools,
                    tool_registry=request.tool_registry,
                    allowed_tool_names=request.allowed_tool_names,
                    active_tool_names=request.active_tool_names,
                    no_tools_mode=normalize_no_tools(request.no_tools),
                ),
                agent_factory=request.agent_factory,
                register_extension_tools=register_extension_tools,
                record_extension_diagnostics=lambda diagnostics: (
                    request.configuration.diagnostics_service.record_resource_diagnostics(
                        diagnostics,
                        phase="resource_loading",
                        source="bootstrap",
                        session_id=request.configuration.session_id,
                    )
                ),
                session_factory=lambda agent, bundle, registry, active, prompt, mode: (
                    request.session_factory(
                        agent,
                        bundle,
                        extension_runtime,
                        registry,
                        active,
                        prompt,
                        mode,
                    )
                ),
            )
            scoped_models = scoped_models_from_patterns(
                settings.enabled_models,
                resolve_model=request.configuration.model_registry.get_model,
            )
            if scoped_models:
                request.set_scoped_models(session, scoped_models)
            return AgentProductConstructionResult(
                session=session,
                configuration=configuration,
            )
        except Exception:
            request.ports.dispose_capabilities()
            raise


__all__ = [
    "AgentBootstrapRequest",
    "AgentBootstrapRuntime",
    "AgentSessionConstructionRequest",
    "AgentSessionConstructionRuntime",
    "AgentProductConstructionPorts",
    "AgentProductConstructionRequest",
    "AgentProductConstructionResult",
    "AgentProductConstructionRuntime",
    "AgentSessionServices",
    "BootstrapServices",
    "CreateAgentSessionResult",
    "StandardAgentSessionActivationEffects",
    "StandardAgentSessionConfigurationRequest",
    "StandardAgentSessionConfigurationResult",
    "StandardAgentSessionConfigurationRuntime",
    "activate_standard_agent_session_configuration",
    "standard_agent_session_activation_plan",
]

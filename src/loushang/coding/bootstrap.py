from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from loushang.agent import Agent, AgentTool, StreamFn, ThinkingLevel
from loushang.ai.model import Model
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.ai.types import Message, TextPart
from loushang.coding.capability_plan import resolve_coding_capability_profile
from loushang.coding.control import (
    ControlConfig,
    ModelRegistry,
    SettingsManager,
)
from loushang.coding.control.settings_store import (
    default_global_settings_path,
    default_project_settings_path,
)
from loushang.coding.extensions import ExtensionRunner
from loushang.coding.policy import InteractiveApprovalResolver
from loushang.coding.prompt import assemble_prompt
from loushang.coding.resource_runtime import (
    CodingPackageMaterializer as PackageMaterializer,
)
from loushang.coding.resource_runtime import (
    CodingResourceLoader as DefaultResourceLoader,
)
from loushang.coding.runtime import AgentSessionRuntime
from loushang.coding.session import AgentSession
from loushang.coding.source_info import executable_source_identity
from loushang.coding.store import SessionManager
from loushang.coding.types import ModelSelection
from loushang.harness.agent_transcript import context_item_to_model_message
from loushang.harness.capabilities import bind_capability_composition_runtime
from loushang.harness.capabilities.packs import (
    CapabilityPack,
    CapabilityPackComposer,
)
from loushang.harness.config import (
    ConfigActivationRuntime,
    ConfigActivationStep,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import DiagnosticRecord, StartupCheckResult
from loushang.harness.extensions.context import SessionStartEvent
from loushang.harness.resources.activation import SkillActivationRuntime
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.layout import resolve_user_resource_roots
from loushang.harness.resources.packages.materializer import (
    GitPackageMaterializerBackend,
)
from loushang.harness.resources.packages.roots import resolve_package_resource_roots
from loushang.harness.resources.packages.source_resolver import (
    PackageSourceResolver,
    package_source_scopes,
)
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.tools.contribution import (
    ToolContribution,
    ToolResolutionResult,
    resolve_tool_contributions,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import ExecService

AgentFactory = Callable[..., Agent]
ServicesFactory = Callable[[str], "BootstrapServices"]
NoToolsMode = Literal["all", "builtin"]
ExtensionFlagValues = Mapping[str, bool | str]


@dataclass(frozen=True)
class BootstrapServices:
    settings_manager: SettingsManager
    model_registry: ModelRegistry
    resource_loader: DefaultResourceLoader
    diagnostics_service: DiagnosticsService
    exec_service: ExecService = field(default_factory=ExecService)


@dataclass(frozen=True)
class CwdBoundServicesAuditIssue:
    code: str
    message: str
    details: dict[str, object]
    level: Literal["info", "warning", "error"] = "warning"


@dataclass(frozen=True)
class CwdBoundServicesAudit:
    session_cwd: str
    issues: list[CwdBoundServicesAuditIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class _SessionConfigurationState:
    services: BootstrapServices
    settings: ControlConfig
    session_manager: SessionManager
    package_materializer: PackageMaterializer
    extension_flag_values: ExtensionFlagValues | None
    skill_activation_runtime: SkillActivationRuntime
    resource_bundle: ResourceBundle | None = None
    extension_runner: ExtensionRunner | None = None
    cwd_bound_services_audit: CwdBoundServicesAudit | None = None

    @property
    def session_id(self) -> str:
        return self.session_manager.get_header().conversation_id


@dataclass(frozen=True)
class AgentSessionServices:
    cwd: str
    services: BootstrapServices
    resource_bundle: ResourceBundle | None = None
    extension_runner: ExtensionRunner | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = ()

    @property
    def settings_manager(self) -> SettingsManager:
        return self.services.settings_manager

    @property
    def model_registry(self) -> ModelRegistry:
        return self.services.model_registry

    @property
    def resource_loader(self) -> DefaultResourceLoader:
        return self.services.resource_loader

    @property
    def diagnostics_service(self) -> DiagnosticsService:
        return self.services.diagnostics_service

    @property
    def exec_service(self) -> ExecService:
        return self.services.exec_service


@dataclass(frozen=True)
class CreateAgentSessionResult:
    session: AgentSession
    resource_bundle: ResourceBundle | None
    diagnostics: tuple[DiagnosticRecord, ...]
    cwd_bound_services_audit: CwdBoundServicesAudit | None = None


def create_services(
    *,
    ai_model_registry: AiModelRegistry | None = None,
    resource_loader: DefaultResourceLoader | None = None,
    settings_manager: SettingsManager | None = None,
    exec_service: ExecService | None = None,
    default_model: ModelSelection | None = None,
    thinking_level: ThinkingLevel = "off",
    system_prompt: str = "",
) -> BootstrapServices:
    model_registry = ModelRegistry(ai_registry=ai_model_registry)
    resolved_settings_manager = settings_manager or SettingsManager(
        ControlConfig(
            default_model=default_model,
            thinking_level=thinking_level,
            system_prompt=system_prompt,
        )
    )
    return BootstrapServices(
        settings_manager=resolved_settings_manager,
        model_registry=model_registry,
        resource_loader=resource_loader or DefaultResourceLoader(),
        diagnostics_service=DiagnosticsService(),
        exec_service=exec_service or ExecService(),
    )


def create_agent_session_services(
    *,
    cwd: str | Path,
    services: BootstrapServices | None = None,
    ai_model_registry: AiModelRegistry | None = None,
    resource_loader: DefaultResourceLoader | None = None,
    settings_manager: SettingsManager | None = None,
    exec_service: ExecService | None = None,
    default_model: ModelSelection | None = None,
    thinking_level: ThinkingLevel = "off",
    system_prompt: str = "",
    global_settings_path: str | Path | None = None,
    project_settings_path: str | Path | None = None,
    resource_loader_options: dict[str, object] | None = None,
    extension_flag_values: ExtensionFlagValues | None = None,
) -> AgentSessionServices:
    resolved_cwd = Path(cwd).expanduser().resolve(strict=False)
    resolved_services = services
    if resolved_services is None:
        resolved_settings_manager = settings_manager or SettingsManager(
            global_settings_path=Path(global_settings_path)
            if global_settings_path is not None
            else default_global_settings_path(),
            project_settings_path=Path(project_settings_path)
            if project_settings_path is not None
            else default_project_settings_path(resolved_cwd),
        )
        resolved_services = create_services(
            ai_model_registry=ai_model_registry,
            resource_loader=resource_loader,
            settings_manager=resolved_settings_manager,
            exec_service=exec_service,
            default_model=default_model,
            thinking_level=thinking_level,
            system_prompt=system_prompt,
        )
    elif any(
        value is not None
        for value in (
            ai_model_registry,
            resource_loader,
            settings_manager,
            exec_service,
            default_model,
        )
    ):
        raise ValueError(
            "service components cannot be overridden when services is provided"
        )

    _apply_resource_loader_options(
        resolved_services.resource_loader, resource_loader_options
    )
    resource_bundle = resolved_services.resource_loader.discover_resources(resolved_cwd)
    loader_diagnostics = tuple(resource_bundle.diagnostics)
    extension_runner = ExtensionRunner(resource_bundle.extensions)
    flag_diagnostics = _apply_extension_flag_values(
        extension_runner, extension_flag_values
    )
    resource_bundle = extension_runner.discover_resources(resource_bundle)
    diagnostics = tuple(
        resolved_services.diagnostics_service.normalize_resource_diagnostic(
            diagnostic,
            phase="resource_loading",
            source=source,
        )
        for source, source_diagnostics in (
            ("loader", loader_diagnostics),
            ("extensions", extension_runner.get_diagnostics()),
            ("bootstrap", flag_diagnostics),
        )
        for diagnostic in source_diagnostics
    )
    return AgentSessionServices(
        cwd=str(resolved_cwd),
        services=resolved_services,
        resource_bundle=resource_bundle,
        extension_runner=extension_runner,
        diagnostics=diagnostics,
    )


def audit_cwd_bound_services(
    *,
    session_manager: SessionManager,
    services: BootstrapServices,
    resource_bundle: ResourceBundle | None = None,
) -> CwdBoundServicesAudit:
    session_cwd = _resolve_for_audit(session_manager.get_cwd())
    issues: list[CwdBoundServicesAuditIssue] = []
    project_root = _settings_project_root(services.settings_manager)
    if project_root is not None and not _path_is_at_or_under(session_cwd, project_root):
        issues.append(
            CwdBoundServicesAuditIssue(
                code="settings_project_cwd_mismatch",
                message=(
                    "Project-scoped settings are bound to a different project root "
                    "than the session cwd."
                ),
                details={
                    "project_root": str(project_root),
                    "session_cwd": str(session_cwd),
                },
            )
        )
    if resource_bundle is not None:
        resource_cwd = _resolve_for_audit(resource_bundle.cwd)
        if resource_cwd != session_cwd:
            issues.append(
                CwdBoundServicesAuditIssue(
                    code="resource_bundle_cwd_mismatch",
                    message="Resource bundle cwd does not match the session cwd.",
                    details={
                        "resource_cwd": str(resource_cwd),
                        "session_cwd": str(session_cwd),
                    },
                )
            )
    return CwdBoundServicesAudit(session_cwd=str(session_cwd), issues=issues)


def create_agent_session(
    *,
    session_manager: SessionManager,
    model: Model | ModelSelection | None = None,
    stream_fn: StreamFn | None = None,
    system_prompt: str | None = None,
    thinking_level: ThinkingLevel | None = None,
    tools: list[AgentTool[Any]] | None = None,
    tool_registry: WorkspaceToolRegistry | None = None,
    allowed_tool_names: list[str] | None = None,
    active_tool_names: list[str] | None = None,
    no_tools: NoToolsMode | bool | None = None,
    services: BootstrapServices | None = None,
    agent_factory: AgentFactory = Agent,
    session_start_event: SessionStartEvent | None = None,
    package_materializer: PackageMaterializer | None = None,
    append_system_prompt: list[str] | tuple[str, ...] | None = None,
    extension_flag_values: ExtensionFlagValues | None = None,
    approval_resolver: InteractiveApprovalResolver | None = None,
) -> AgentSession:
    services = services or create_services()
    settings = services.settings_manager.get_settings()
    capability_runtime = bind_capability_composition_runtime(
        resolve_coding_capability_profile()
    )
    resolved_package_materializer = (
        package_materializer or _default_package_materializer(session_manager)
    )
    resolved_thinking = (
        settings.thinking_level if thinking_level is None else thinking_level
    )
    session_id = session_manager.get_header().conversation_id
    try:
        configuration = _activate_session_configuration(
            settings=settings,
            services=services,
            session_manager=session_manager,
            package_materializer=resolved_package_materializer,
            extension_flag_values=extension_flag_values,
            skill_activation_runtime=capability_runtime.skill_activation,
        )
        resource_bundle = _require_configured_resource_bundle(configuration)
        extension_runner = _require_configured_extension_runner(configuration)
        cwd_bound_services_audit = configuration.cwd_bound_services_audit
        loader_system_prompt = _loader_system_prompt_override(services.resource_loader)
        base_prompt = (
            system_prompt
            if system_prompt is not None
            else loader_system_prompt
            if loader_system_prompt is not None
            else settings.system_prompt
        )
        append_fragments = [
            *_loader_append_system_prompt(services.resource_loader),
            *(append_system_prompt or ()),
        ]
        base_prompt = _append_system_prompt_fragments(base_prompt, append_fragments)
        prompt_assembly = assemble_prompt(
            base_prompt=base_prompt,
            resource_bundle=resource_bundle,
            resource_activation=capability_runtime.activate_resources(resource_bundle),
            prompt_section_composer=capability_runtime.prompt_section_composer,
        )
        resolved_prompt = prompt_assembly.system_prompt
        resolved_model: Model | None
        if model is None:
            default_selection = settings.default_model
            resolved_model = _resolve_default_model_candidate(
                default_selection,
                model_registry=services.model_registry,
                diagnostics_service=services.diagnostics_service,
                session_id=session_id,
            )
        elif isinstance(model, ModelSelection):
            resolved_model = services.model_registry.build_model(model)
        else:
            resolved_model = model

        no_tools_mode = _normalize_no_tools(no_tools)
        resolved_tool_registry = tool_registry
        allowed_tool_names_set = (
            set(allowed_tool_names) if allowed_tool_names is not None else None
        )
        if no_tools_mode == "all":
            allowed_tool_names_set = set()
        if resolved_tool_registry is None and tools:
            resolved_tool_registry = WorkspaceToolRegistry()
            for tool in tools:
                resolved_tool_registry.register_tool(tool)

        resource_bundle, resolved_tool_registry, extension_tool_diagnostics = (
            _register_extension_tools(
                extension_runner=extension_runner,
                resource_bundle=resource_bundle,
                tool_registry=resolved_tool_registry,
                pack_composer=capability_runtime.tool_pack_composer,
            )
        )
        _record_resource_diagnostics(
            diagnostics_service=services.diagnostics_service,
            diagnostics=extension_tool_diagnostics,
            phase="resource_loading",
            source="bootstrap",
            session_id=session_id,
        )
        if no_tools_mode == "all" and resolved_tool_registry is None:
            resolved_tool_registry = WorkspaceToolRegistry()
        resolved_active_tool_names = _resolve_initial_active_tool_names(
            active_tool_names=active_tool_names,
            allowed_tool_names_set=allowed_tool_names_set,
            no_tools_mode=no_tools_mode,
            tool_registry=resolved_tool_registry,
        )
        initial_state: dict[str, object] = {
            "system_prompt": resolved_prompt,
            "thinking_level": resolved_thinking,
            "tools": [],
        }
        if resolved_model is not None:
            initial_state["model"] = resolved_model

        agent_kwargs: dict[str, object] = {
            "initial_state": initial_state,
            "session_id": session_id,
            "convert_to_llm": _convert_to_llm_with_block_images(
                services.settings_manager
            ),
            "steering_mode": settings.steering_mode,
            "follow_up_mode": settings.follow_up_mode,
            "thinking_budgets": settings.thinking_budgets,
            "max_retry_delay_ms": settings.retry.provider_max_retry_delay_ms,
        }
        if stream_fn is not None:
            agent_kwargs["stream_fn"] = stream_fn

        agent = agent_factory(**agent_kwargs)
        agent.session_id = session_id
        session = AgentSession(
            agent=agent,
            session_manager=session_manager,
            settings_manager=services.settings_manager,
            model_registry=services.model_registry,
            resource_loader=services.resource_loader,
            resource_bundle=resource_bundle,
            extension_runner=extension_runner,
            tool_registry=resolved_tool_registry,
            allowed_tool_names=[] if no_tools_mode == "all" else allowed_tool_names,
            active_tool_names=resolved_active_tool_names,
            default_activate_new_tools=(
                no_tools_mode != "all" and active_tool_names is None
            ),
            show_empty_tool_prompt=no_tools_mode == "all",
            base_prompt=base_prompt,
            diagnostics_service=services.diagnostics_service,
            session_start_event=session_start_event,
            package_materializer=resolved_package_materializer,
            exec_service=services.exec_service,
            approval_resolver=approval_resolver,
            capability_runtime=capability_runtime,
        )
        session.cwd_bound_services_audit = cwd_bound_services_audit
        scoped_models = _scoped_models_from_enabled_patterns(
            settings.enabled_models, services.model_registry
        )
        if scoped_models:
            session.set_scoped_models(scoped_models)
        return session
    except Exception:
        capability_runtime.dispose()
        raise


def _activate_session_configuration(
    *,
    settings: ControlConfig,
    services: BootstrapServices,
    session_manager: SessionManager,
    package_materializer: PackageMaterializer,
    extension_flag_values: ExtensionFlagValues | None,
    skill_activation_runtime: SkillActivationRuntime | None = None,
) -> _SessionConfigurationState:
    state = _SessionConfigurationState(
        services=services,
        settings=settings,
        session_manager=session_manager,
        package_materializer=package_materializer,
        extension_flag_values=extension_flag_values,
        skill_activation_runtime=skill_activation_runtime or SkillActivationRuntime(),
    )
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "startup_checks",
                select=lambda config: config.package_roots,
                apply=_activate_startup_checks,
            ),
            ConfigActivationStep(
                "package_sources",
                select=lambda config: config.package_sources,
                apply=_activate_package_sources,
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
                apply=_activate_resource_roots,
                depends_on=("package_sources",),
            ),
            ConfigActivationStep(
                "resources",
                select=lambda config: config.disabled_skills,
                apply=_activate_resources,
                depends_on=("resource_roots",),
            ),
            ConfigActivationStep(
                "extensions",
                select=lambda config: (
                    config.disabled_skills,
                    config.disabled_plugins,
                ),
                apply=_activate_extensions,
                depends_on=("resources",),
            ),
            ConfigActivationStep(
                "cwd_audit",
                select=lambda config: config.resource_roots,
                apply=_activate_cwd_audit,
                depends_on=("extensions",),
            ),
            ConfigActivationStep(
                "model_registry",
                select=lambda config: config.enabled_models,
                apply=_activate_model_registry,
                depends_on=("cwd_audit",),
            ),
        )
    )
    report = runtime.start(settings, state)
    if report.failures:
        raise report.failures[0].error
    return state


def _activate_startup_checks(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    _record_package_lockfile_diagnostics(
        diagnostics_service=state.services.diagnostics_service,
        materializer=state.package_materializer,
        session_id=state.session_id,
    )
    _run_bootstrap_startup_checks(
        diagnostics_service=state.services.diagnostics_service,
        session_manager=state.session_manager,
        package_roots=state.settings.package_roots,
    )


def _activate_package_sources(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    _resolve_configured_remote_packages(
        materializer=state.package_materializer,
        settings_manager=state.services.settings_manager,
        diagnostics_service=state.services.diagnostics_service,
        session_id=state.session_id,
    )


def _activate_resource_roots(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    services = state.services
    settings = state.settings
    set_package_roots = getattr(services.resource_loader, "set_package_roots", None)
    if callable(set_package_roots):
        package_resource_roots = resolve_package_resource_roots(
            package_roots=settings.package_roots,
            plugin_sources=settings.plugin_sources,
            package_sources=settings.package_sources,
            materializer=state.package_materializer,
            package_source_scopes=package_source_scopes(services.settings_manager),
            global_base_dir=services.settings_manager.global_base_dir,
            project_base_dir=services.settings_manager.project_base_dir,
            disabled_plugins=settings.disabled_plugins,
            diagnostics_service=services.diagnostics_service,
            session_id=state.session_id,
        )
        set_package_roots(package_resource_roots.roots, package_resource_roots.filters)
    set_user_resource_roots = getattr(
        services.resource_loader,
        "set_user_resource_roots",
        None,
    )
    if callable(set_user_resource_roots):
        global_resource_roots = tuple(
            services.settings_manager.get_global_settings().get(
                "resource_roots",
                (),
            )
        )
        user_roots, explicit_roots = _resolve_user_resource_roots(
            global_resource_roots,
            global_base_dir=services.settings_manager.global_base_dir,
        )
        set_user_resource_roots(user_roots, explicit_roots=explicit_roots)


def _activate_resources(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    bundle = state.services.resource_loader.discover_resources(
        state.session_manager.get_cwd()
    )
    bundle = state.skill_activation_runtime.apply(
        bundle, state.settings.disabled_skills
    )
    _record_resource_diagnostics(
        diagnostics_service=state.services.diagnostics_service,
        diagnostics=bundle.diagnostics,
        phase="resource_loading",
        source="loader",
        session_id=state.session_id,
    )
    state.resource_bundle = bundle


def _activate_extensions(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    bundle = _require_configured_resource_bundle(state)
    runner = ExtensionRunner(bundle.extensions)
    flag_diagnostics = _apply_extension_flag_values(
        runner,
        state.extension_flag_values,
    )
    _record_resource_diagnostics(
        diagnostics_service=state.services.diagnostics_service,
        diagnostics=flag_diagnostics,
        phase="resource_loading",
        source="bootstrap",
        session_id=state.session_id,
    )
    bundle = runner.discover_resources(bundle)
    bundle = state.skill_activation_runtime.apply(
        bundle, state.settings.disabled_skills
    )
    _record_resource_diagnostics(
        diagnostics_service=state.services.diagnostics_service,
        diagnostics=runner.get_diagnostics(),
        phase="resource_loading",
        source="extensions",
        session_id=state.session_id,
    )
    state.resource_bundle = bundle
    state.extension_runner = runner


def _activate_cwd_audit(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    audit = audit_cwd_bound_services(
        session_manager=state.session_manager,
        services=state.services,
        resource_bundle=_require_configured_resource_bundle(state),
    )
    _record_cwd_bound_services_audit(
        diagnostics_service=state.services.diagnostics_service,
        audit=audit,
        session_id=state.session_id,
    )
    state.cwd_bound_services_audit = audit


def _activate_model_registry(
    selection: object,
    state: _SessionConfigurationState,
) -> None:
    del selection
    _reload_model_registry_with_project_layer(
        state.services.model_registry,
        resource_bundle=_require_configured_resource_bundle(state),
        session_cwd=state.session_manager.get_cwd(),
    )


def _require_configured_resource_bundle(
    state: _SessionConfigurationState,
) -> ResourceBundle:
    if state.resource_bundle is None:
        raise RuntimeError("Session resources have not been configured.")
    return state.resource_bundle


def _require_configured_extension_runner(
    state: _SessionConfigurationState,
) -> ExtensionRunner:
    if state.extension_runner is None:
        raise RuntimeError("Session extensions have not been configured.")
    return state.extension_runner


def _resolve_default_model_candidate(
    selection: ModelSelection | None,
    *,
    model_registry: ModelRegistry,
    diagnostics_service: DiagnosticsService,
    session_id: str,
) -> Model | None:
    if selection is None:
        return None
    try:
        return model_registry.build_model(selection)
    except (KeyError, ValueError) as error:
        _record_default_model_unavailable(
            selection,
            error=error,
            model_registry=model_registry,
            diagnostics_service=diagnostics_service,
            session_id=session_id,
        )
        return None


def _record_default_model_unavailable(
    selection: ModelSelection,
    *,
    error: Exception,
    model_registry: ModelRegistry,
    diagnostics_service: DiagnosticsService,
    session_id: str,
) -> None:
    reason = _default_model_unavailable_reason(
        selection,
        error=error,
        model_registry=model_registry,
    )
    selection_ref = (
        f"{selection.provider}:{selection.endpoint_id}:{selection.model_id}"
        if selection.endpoint_id
        else f"{selection.provider}:{selection.model_id}"
    )
    message = f"Default model unavailable: {selection_ref}; using startup fallback."
    diagnostics_service.record(
        diagnostics_service.normalize_error(
            code="default_model_unavailable",
            error=message,
            phase="startup",
            source="model",
            level="warning",
            session_id=session_id,
            details={
                "provider": selection.provider,
                "model_id": selection.model_id,
                "endpoint_id": selection.endpoint_id,
                "reason": reason,
                "error": str(error),
            },
        )
    )


def _default_model_unavailable_reason(
    selection: ModelSelection,
    *,
    error: Exception,
    model_registry: ModelRegistry,
) -> str:
    if selection.endpoint_id:
        endpoint = model_registry.ai_registry.get_endpoint(
            selection.provider,
            selection.endpoint_id,
        )
        if endpoint is None:
            return "endpoint_unavailable"
        return "missing"
    if isinstance(error, ValueError):
        return "ambiguous"
    return "missing"


def create_agent_session_from_services(
    *,
    agent_services: AgentSessionServices,
    session_manager: SessionManager,
    model: Model | ModelSelection | None = None,
    stream_fn: StreamFn | None = None,
    system_prompt: str | None = None,
    thinking_level: ThinkingLevel | None = None,
    tools: list[AgentTool[Any]] | None = None,
    tool_registry: WorkspaceToolRegistry | None = None,
    allowed_tool_names: list[str] | None = None,
    active_tool_names: list[str] | None = None,
    no_tools: NoToolsMode | bool | None = None,
    agent_factory: AgentFactory = Agent,
    session_start_event: SessionStartEvent | None = None,
    package_materializer: PackageMaterializer | None = None,
    append_system_prompt: list[str] | tuple[str, ...] | None = None,
    approval_resolver: InteractiveApprovalResolver | None = None,
) -> CreateAgentSessionResult:
    extension_flag_values = (
        agent_services.extension_runner.get_flag_values()
        if agent_services.extension_runner is not None
        else None
    )
    return create_agent_session_result(
        session_manager=session_manager,
        model=model,
        stream_fn=stream_fn,
        system_prompt=system_prompt,
        thinking_level=thinking_level,
        tools=tools,
        tool_registry=tool_registry,
        allowed_tool_names=allowed_tool_names,
        active_tool_names=active_tool_names,
        no_tools=no_tools,
        services=agent_services.services,
        agent_factory=agent_factory,
        session_start_event=session_start_event,
        package_materializer=package_materializer,
        append_system_prompt=append_system_prompt,
        extension_flag_values=extension_flag_values,
        approval_resolver=approval_resolver,
    )


def create_agent_session_result(
    *,
    session_manager: SessionManager,
    model: Model | ModelSelection | None = None,
    stream_fn: StreamFn | None = None,
    system_prompt: str | None = None,
    thinking_level: ThinkingLevel | None = None,
    tools: list[AgentTool[Any]] | None = None,
    tool_registry: WorkspaceToolRegistry | None = None,
    allowed_tool_names: list[str] | None = None,
    active_tool_names: list[str] | None = None,
    no_tools: NoToolsMode | bool | None = None,
    services: BootstrapServices | None = None,
    agent_factory: AgentFactory = Agent,
    session_start_event: SessionStartEvent | None = None,
    package_materializer: PackageMaterializer | None = None,
    append_system_prompt: list[str] | tuple[str, ...] | None = None,
    extension_flag_values: ExtensionFlagValues | None = None,
    approval_resolver: InteractiveApprovalResolver | None = None,
) -> CreateAgentSessionResult:
    resolved_services = services or create_services()
    session = create_agent_session(
        session_manager=session_manager,
        model=model,
        stream_fn=stream_fn,
        system_prompt=system_prompt,
        thinking_level=thinking_level,
        tools=tools,
        tool_registry=tool_registry,
        allowed_tool_names=allowed_tool_names,
        active_tool_names=active_tool_names,
        no_tools=no_tools,
        services=resolved_services,
        agent_factory=agent_factory,
        session_start_event=session_start_event,
        package_materializer=package_materializer,
        append_system_prompt=append_system_prompt,
        extension_flag_values=extension_flag_values,
        approval_resolver=approval_resolver,
    )
    return CreateAgentSessionResult(
        session=session,
        resource_bundle=session.resource_bundle,
        diagnostics=tuple(
            resolved_services.diagnostics_service.get_diagnostics(
                session_id=session.session_id
            )
        ),
        cwd_bound_services_audit=session.cwd_bound_services_audit,
    )


def _apply_resource_loader_options(
    resource_loader: DefaultResourceLoader,
    options: dict[str, object] | None,
) -> None:
    if not options:
        return
    setter = getattr(resource_loader, "set_runtime_options", None)
    if callable(setter):
        setter(**options)


def _apply_extension_flag_values(
    extension_runner: ExtensionRunner,
    flag_values: ExtensionFlagValues | None,
) -> list[ResourceDiagnostic]:
    if not flag_values:
        return []

    flags_by_name = {flag.name: flag for flag in extension_runner.get_flags()}
    diagnostics: list[ResourceDiagnostic] = []
    for raw_name, value in flag_values.items():
        name = raw_name[2:] if raw_name.startswith("--") else raw_name
        flag = flags_by_name.get(name)
        if flag is None:
            diagnostics.append(
                ResourceDiagnostic(
                    code="unknown_extension_flag",
                    message=f"Unknown extension flag: --{name}",
                    metadata={"flag": name},
                )
            )
            continue
        if flag.type == "string":
            if not isinstance(value, str):
                diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_flag_value_required",
                        message=f'Extension flag "--{name}" requires a value.',
                        source_path=flag.source_info.path,
                        metadata={"flag": name},
                    )
                )
                continue
            extension_runner.set_flag_value(name, value)
            continue
        extension_runner.set_flag_value(name, bool(value))
    return diagnostics


def _default_package_materializer(
    session_manager: SessionManager,
) -> PackageMaterializer:
    session_dir = session_manager.get_session_dir()
    if session_dir.name == "sessions":
        install_root = session_dir.parent / "packages"
    elif str(session_dir):
        install_root = session_dir / "packages"
    else:
        install_root = Path(session_manager.get_cwd()) / ".loushang" / "packages"
    return PackageMaterializer(
        install_root=install_root,
        backend=GitPackageMaterializerBackend(),
    )


def _normalize_no_tools(no_tools: NoToolsMode | bool | None) -> NoToolsMode | None:
    if no_tools is True:
        return "all"
    if no_tools in (False, None):
        return None
    if no_tools in {"all", "builtin"}:
        return no_tools
    raise ValueError("no_tools must be 'all', 'builtin', True, False, or None")


def _loader_system_prompt_override(resource_loader: object) -> str | None:
    getter = getattr(resource_loader, "get_system_prompt_override", None)
    if not callable(getter):
        return None
    value = getter()
    return value if isinstance(value, str) else None


def _loader_append_system_prompt(resource_loader: object) -> list[str]:
    getter = getattr(resource_loader, "get_append_system_prompt_overrides", None)
    if not callable(getter):
        return []
    values = getter()
    if not isinstance(values, list | tuple):
        return []
    return [value for value in values if isinstance(value, str) and value.strip()]


def _append_system_prompt_fragments(base_prompt: str, fragments: list[str]) -> str:
    parts = (
        [base_prompt.strip()]
        if isinstance(base_prompt, str) and base_prompt.strip()
        else []
    )
    parts.extend(
        fragment.strip()
        for fragment in fragments
        if isinstance(fragment, str) and fragment.strip()
    )
    return "\n\n".join(parts)


def _resolve_initial_active_tool_names(
    *,
    active_tool_names: list[str] | None,
    allowed_tool_names_set: set[str] | None,
    no_tools_mode: NoToolsMode | None,
    tool_registry: WorkspaceToolRegistry | None,
) -> list[str] | None:
    if no_tools_mode == "all":
        return []
    if active_tool_names is not None:
        names = list(active_tool_names)
    elif no_tools_mode == "builtin":
        names = _non_builtin_tool_names(tool_registry)
    else:
        return None
    if allowed_tool_names_set is not None:
        return [name for name in names if name in allowed_tool_names_set]
    return names


def _non_builtin_tool_names(tool_registry: WorkspaceToolRegistry | None) -> list[str]:
    if tool_registry is None:
        return []
    builtin_names = {"bash", "read", "ls", "find", "grep", "write", "edit"}
    return [
        definition.name
        for definition in tool_registry.list_enabled_definitions()
        if definition.name not in builtin_names
    ]


def _reload_model_registry_with_project_layer(
    model_registry: ModelRegistry,
    *,
    resource_bundle: ResourceBundle,
    session_cwd: str,
) -> None:
    project_root = (
        resource_bundle.agents_path.parent
        if resource_bundle.agents_path is not None
        else Path(session_cwd)
    )
    project_models_dir = project_root / ".loushang" / "models"
    if not project_models_dir.is_dir():
        return
    user_models_dir = Path.home() / ".loushang" / "models"
    model_registry.reload(
        user_dir=user_models_dir if user_models_dir.is_dir() else None,
        project_dir=project_models_dir,
    )


def _resolve_user_resource_roots(
    resource_roots: tuple[str, ...],
    *,
    global_base_dir: Path | None,
) -> tuple[list[str], set[str]]:
    roots, explicit = resolve_user_resource_roots(
        resource_roots,
        global_base_dir=global_base_dir,
    )
    return [str(root) for root in roots], {str(root) for root in explicit}


def _resolve_for_audit(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _settings_project_root(settings_manager: SettingsManager) -> Path | None:
    project_base_dir = settings_manager.project_base_dir
    if project_base_dir is None:
        return None
    resolved = _resolve_for_audit(project_base_dir)
    return resolved.parent if resolved.name == ".loushang" else resolved


def _path_is_at_or_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _scoped_models_from_enabled_patterns(
    patterns: tuple[str, ...] | None,
    model_registry: ModelRegistry,
) -> list[dict[str, object]]:
    if not patterns:
        return []
    scoped_models: list[dict[str, object]] = []
    for pattern in patterns:
        model_name, thinking_level = _split_model_thinking_pattern(pattern)
        selection = model_registry.get_model(model_name)
        if selection is None:
            continue
        model_payload: dict[str, object] = {
            "provider": selection.provider,
            "model_id": selection.model_id,
        }
        if selection.endpoint_id:
            model_payload["endpoint_id"] = selection.endpoint_id
        scoped: dict[str, object] = {"model": model_payload}
        if thinking_level is not None:
            scoped["thinkingLevel"] = thinking_level
        scoped_models.append(scoped)
    return scoped_models


def _split_model_thinking_pattern(pattern: str) -> tuple[str, ThinkingLevel | None]:
    name, separator, suffix = pattern.rpartition(":")
    if (
        separator
        and suffix in {"off", "minimal", "low", "medium", "high", "xhigh"}
        and name
    ):
        return name, suffix
    return pattern, None


def _register_extension_tools(
    *,
    extension_runner: ExtensionRunner,
    resource_bundle: ResourceBundle,
    tool_registry: WorkspaceToolRegistry | None,
    pack_composer: CapabilityPackComposer | None = None,
) -> tuple[ResourceBundle, WorkspaceToolRegistry | None, list[ResourceDiagnostic]]:
    extension_tools = extension_runner.list_tool_definitions()
    if not extension_tools:
        return resource_bundle, tool_registry, []
    resolved_tool_registry = tool_registry
    if resolved_tool_registry is None:
        resolved_tool_registry = WorkspaceToolRegistry()

    resolution = _resolve_extension_tool_contributions(
        extension_runner=extension_runner,
        tool_registry=resolved_tool_registry,
        pack_composer=pack_composer,
    )
    conflict_diagnostics = _extension_tool_conflict_diagnostics(resolution)
    diagnostics: list[ResourceDiagnostic] = list(conflict_diagnostics.values())
    for contribution in _extension_tool_registration_contributions(
        resolution, conflict_names=set(conflict_diagnostics)
    ):
        resolved_tool_registry.register_tool(
            contribution.definition,
            source_info=contribution.source_info,
        )

    if diagnostics:
        resource_bundle = resource_bundle.merge(diagnostics=diagnostics)
    return resource_bundle, resolved_tool_registry, diagnostics


def _resolve_extension_tool_contributions(
    *,
    extension_runner: ExtensionRunner,
    tool_registry: WorkspaceToolRegistry,
    pack_composer: CapabilityPackComposer | None = None,
) -> ToolResolutionResult:
    return resolve_tool_contributions(
        (pack_composer or CapabilityPackComposer())
        .compose(
            (
                CapabilityPack(
                    pack_id="coding.registry",
                    source="product",
                    priority=100,
                    items=tool_registry.list_contributions(),
                ),
                CapabilityPack(
                    pack_id="coding.extensions",
                    source="extension",
                    items=_extension_tool_contributions(extension_runner),
                ),
            )
        )
        .items,
        fail_on_errors=False,
    )


def _extension_tool_registration_contributions(
    resolution: ToolResolutionResult,
    *,
    conflict_names: set[str],
) -> tuple[ToolContribution, ...]:
    contributions: list[ToolContribution] = []
    for contribution in resolution.contributions:
        if not _is_extension_tool_contribution(contribution):
            continue
        if contribution.definition.name in conflict_names:
            continue
        contributions.append(contribution)
    return tuple(contributions)


def _extension_tool_contributions(
    extension_runner: ExtensionRunner,
) -> tuple[ToolContribution, ...]:
    return tuple(
        ToolContribution(
            definition,
            source_info=extension_runner.get_tool_source_info(definition.name),
            metadata={
                "kind": "extension_tool",
                "extension_tool": definition.name,
            },
        )
        for definition in extension_runner.list_tool_definitions()
    )


def _extension_tool_conflict_diagnostics(
    resolution: ToolResolutionResult,
) -> dict[str, ResourceDiagnostic]:
    conflicts: dict[str, ResourceDiagnostic] = {}
    for diagnostic in resolution.diagnostics:
        if diagnostic.code != "duplicate_tool":
            continue
        name = diagnostic.details.get("name")
        if not isinstance(name, str):
            continue
        conflicts[name] = ResourceDiagnostic(
            code="extension_tool_conflict",
            message=f"Extension tool '{name}' conflicts with an existing registry tool.",
        )
    return conflicts


def _is_extension_tool_contribution(contribution: ToolContribution) -> bool:
    return contribution.metadata.get("kind") == "extension_tool"


def _convert_to_llm_with_block_images(settings_manager: SettingsManager):
    def _convert(messages) -> list[Message]:
        converted = [
            projected
            for message in messages
            if (projected := context_item_to_model_message(message)) is not None
        ]
        if not settings_manager.get_block_images():
            return converted
        return [_replace_images_with_placeholder(message) for message in converted]

    return _convert


def _replace_images_with_placeholder(message: Message) -> Message:
    if getattr(message, "role", None) not in {"user", "toolResult"}:
        return message
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return message

    placeholder = TextPart(type="text", text="Image reading is disabled.")
    filtered: list[object] = []
    for block in content:
        if getattr(block, "type", None) == "image":
            if not (
                filtered
                and isinstance(filtered[-1], TextPart)
                and filtered[-1].text == placeholder.text
            ):
                filtered.append(placeholder)
            continue
        filtered.append(block)

    if filtered == content:
        return message
    return replace(message, content=filtered)


def _record_package_lockfile_diagnostics(
    *,
    diagnostics_service: DiagnosticsService,
    materializer: PackageMaterializer,
    session_id: str | None,
) -> None:
    for diagnostic in materializer.get_lockfile_diagnostics():
        diagnostics_service.capture_failure(
            code=str(diagnostic.get("code") or "package_lockfile_unreadable"),
            error=str(
                diagnostic.get("message") or "Package lockfile could not be read."
            ),
            phase="startup",
            source="bootstrap",
            level="warning",
            session_id=session_id,
            source_path=Path(str(diagnostic["path"]))
            if isinstance(diagnostic.get("path"), str)
            else None,
            details={
                key: value
                for key, value in diagnostic.items()
                if key not in {"code", "message", "path"}
            },
        )


def _resolve_configured_remote_packages(
    *,
    materializer: PackageMaterializer,
    settings_manager: SettingsManager,
    diagnostics_service: DiagnosticsService,
    session_id: str,
) -> None:
    PackageSourceResolver(
        settings_manager=settings_manager,
        materializer=materializer,
        diagnostics_service=diagnostics_service,
        session_id=session_id,
    ).resolve_configured_sources_sync(missing_source_action="install", phase="startup")


def _skill_disabled(skill, disabled: set[str]) -> bool:
    return any(
        value in disabled
        for value in (
            getattr(skill, "name", None),
            getattr(skill, "id", None),
            getattr(skill, "canonical_name", None),
            str(getattr(skill, "source_path", "")),
        )
    )


def _run_bootstrap_startup_checks(
    *,
    diagnostics_service: DiagnosticsService,
    session_manager: SessionManager,
    package_roots: tuple[str, ...],
) -> None:
    cwd = session_manager.get_cwd()

    def cwd_check() -> StartupCheckResult | None:
        cwd_path = Path(cwd).expanduser()
        if cwd_path.is_dir():
            return None
        return StartupCheckResult(
            name="cwd",
            ok=False,
            code="cwd_unavailable",
            level="warning",
            message=f"Session cwd is not an available directory: {cwd_path}",
            details={"cwd": str(cwd_path)},
        )

    def executable_source_identity_check() -> StartupCheckResult:
        return StartupCheckResult(
            name="executable_source_identity",
            ok=True,
            code="executable_source_identity",
            level="info",
            message="Executable and import source identity captured.",
            source_path=Path(__file__).resolve(strict=False),
            details=executable_source_identity(cwd=cwd),
        )

    checks = [cwd_check]
    for root in package_roots:
        checks.append(_package_root_check(root))
    checks.append(executable_source_identity_check)

    diagnostics_service.run_startup_checks(
        checks,
        session_id=session_manager.get_header().conversation_id,
    )


def _package_root_check(root: str) -> Callable[[], StartupCheckResult | None]:
    def check() -> StartupCheckResult | None:
        root_path = Path(root).expanduser()
        if root_path.is_dir():
            return None
        return StartupCheckResult(
            name="package_root",
            ok=False,
            code="package_root_unavailable",
            level="warning",
            message=f"Package root is not an available directory: {root_path}",
            details={"package_root": str(root_path)},
        )

    return check


def _record_resource_diagnostics(
    *,
    diagnostics_service: DiagnosticsService,
    diagnostics: list[ResourceDiagnostic],
    phase,
    source,
    session_id: str,
) -> None:
    diagnostics_service.record_many(
        diagnostics_service.normalize_resource_diagnostic(
            diagnostic,
            phase=phase,
            source=source,
            session_id=session_id,
        )
        for diagnostic in diagnostics
    )


def _record_cwd_bound_services_audit(
    *,
    diagnostics_service: DiagnosticsService,
    audit: CwdBoundServicesAudit,
    session_id: str,
) -> None:
    for issue in audit.issues:
        diagnostics_service.capture_failure(
            code=issue.code,
            error=issue.message,
            phase="startup",
            source="bootstrap",
            level=issue.level,
            session_id=session_id,
            details=issue.details,
        )


def create_agent_session_runtime(
    *,
    session_dir: Path,
    model: Model | ModelSelection | None = None,
    stream_fn: StreamFn | None = None,
    system_prompt: str | None = None,
    thinking_level: ThinkingLevel | None = None,
    tools: list[AgentTool[Any]] | None = None,
    tool_registry: WorkspaceToolRegistry | None = None,
    allowed_tool_names: list[str] | None = None,
    active_tool_names: list[str] | None = None,
    no_tools: NoToolsMode | bool | None = None,
    services: BootstrapServices | None = None,
    services_factory: ServicesFactory | None = None,
    agent_factory: AgentFactory = Agent,
    persist: bool = True,
    append_system_prompt: list[str] | tuple[str, ...] | None = None,
    approval_resolver: InteractiveApprovalResolver | None = None,
) -> AgentSessionRuntime:
    fixed_services = services if services is not None else create_services()
    runtime_diagnostics_service = fixed_services.diagnostics_service

    def _session_factory(
        session_manager: SessionManager,
        *,
        session_start_event: SessionStartEvent | None = None,
    ) -> AgentSession:
        session_services = (
            services_factory(session_manager.get_cwd())
            if services_factory is not None
            else fixed_services
        )
        session = create_agent_session(
            session_manager=session_manager,
            model=model,
            stream_fn=stream_fn,
            system_prompt=system_prompt,
            thinking_level=thinking_level,
            tools=tools,
            tool_registry=tool_registry,
            allowed_tool_names=allowed_tool_names,
            active_tool_names=active_tool_names,
            no_tools=no_tools,
            services=session_services,
            agent_factory=agent_factory,
            session_start_event=session_start_event,
            append_system_prompt=append_system_prompt,
            approval_resolver=approval_resolver,
        )
        if not persist:
            session.agent.session_id = None
        return session

    return AgentSessionRuntime(
        session_dir=Path(session_dir),
        session_factory=_session_factory,
        persist=persist,
        diagnostics_service=runtime_diagnostics_service,
    )

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from loushang.agent import Agent, AgentTool, StreamFn, ThinkingLevel
from loushang.ai.model import Model, ModelSelection
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.coding.control.settings_store import (
    default_global_settings_path,
    default_project_settings_path,
)
from loushang.coding.diagnostics.profile import coding_runtime_identity
from loushang.coding.policy import InteractiveApprovalResolver
from loushang.coding.product_plan import CODING_CAPABILITY_PROFILE
from loushang.coding.prompt.defaults import DEFAULT_CODING_SYSTEM_PROMPT
from loushang.coding.resource_runtime import (
    CodingPackageMaterializer as PackageMaterializer,
)
from loushang.coding.resource_runtime import (
    CodingResourceLoader as DefaultResourceLoader,
)
from loushang.coding.runtime import AgentSessionRuntime
from loushang.coding.session import AgentSession
from loushang.coding.session_manager import SessionManager
from loushang.harness.agent_transcript import context_items_to_model_messages
from loushang.harness.bootstrap import (
    create_standard_resource_bootstrap_runtime,
)
from loushang.harness.capabilities import bind_capability_composition_runtime
from loushang.harness.config.agent import ControlConfig, SettingsManager
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import StartupCheckResult
from loushang.harness.extensions.agent import ExtensionRunner
from loushang.harness.extensions.context import SessionStartEvent
from loushang.harness.model_catalog import ModelCatalog
from loushang.harness.resources.packages.materializer import (
    GitPackageMaterializerBackend,
    resolve_session_package_install_root,
)
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session import (
    AgentProductConstructionPorts,
    AgentProductConstructionRequest,
    AgentProductConstructionRuntime,
    AgentSessionServices,
    BootstrapServices,
    CreateAgentSessionResult,
    CwdBoundServicesAudit,
    StandardAgentSessionConfigurationRequest,
    project_root_from_settings_base,
    record_default_model_unavailable,
)
from loushang.harness.session import (
    CwdBoundServicesAuditIssue as _CwdBoundServicesAuditIssue,
)
from loushang.harness.session import (
    audit_cwd_bound_services as _audit_cwd_bound_services,
)
from loushang.harness.session import (
    prepare_agent_session_services as prepare_standard_agent_session_services,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import ExecService

AgentFactory = Callable[..., Agent]
ServicesFactory = Callable[[str], "BootstrapServices"]
NoToolsMode = Literal["all", "builtin"]
ExtensionFlagValues = Mapping[str, bool | str]
CwdBoundServicesAuditIssue = _CwdBoundServicesAuditIssue


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
    model_registry = ModelCatalog(ai_registry=ai_model_registry)
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
    def create_cwd_services(resolved_cwd: Path) -> BootstrapServices:
        resolved_settings_manager = settings_manager or SettingsManager(
            global_settings_path=Path(global_settings_path)
            if global_settings_path is not None
            else default_global_settings_path(),
            project_settings_path=Path(project_settings_path)
            if project_settings_path is not None
            else default_project_settings_path(resolved_cwd),
        )
        return create_services(
            ai_model_registry=ai_model_registry,
            resource_loader=resource_loader,
            settings_manager=resolved_settings_manager,
            exec_service=exec_service,
            default_model=default_model,
            thinking_level=thinking_level,
            system_prompt=system_prompt,
        )

    return prepare_standard_agent_session_services(
        cwd=cwd,
        services=services,
        create_services=create_cwd_services,
        service_overrides={
            "ai_model_registry": ai_model_registry,
            "resource_loader": resource_loader,
            "settings_manager": settings_manager,
            "exec_service": exec_service,
            "default_model": default_model,
        },
        build_resource_bootstrap=lambda resolved_services: (
            create_standard_resource_bootstrap_runtime(
                create_extension_runtime=lambda bundle: ExtensionRunner(
                    bundle.extensions
                ),
                diagnostics_service=resolved_services.diagnostics_service,
            )
        ),
        get_resource_loader=lambda resolved_services: resolved_services.resource_loader,
        resource_loader_options=resource_loader_options,
        configure_resource_loader=lambda loader, options: loader.set_runtime_options(
            **dict(options)
        ),
        extension_flag_values=extension_flag_values,
    )


def audit_cwd_bound_services(
    *,
    session_manager: SessionManager,
    services: BootstrapServices,
    resource_bundle: ResourceBundle | None = None,
) -> CwdBoundServicesAudit:
    return _audit_cwd_bound_services(
        session_cwd=session_manager.get_cwd(),
        project_root=project_root_from_settings_base(
            services.settings_manager.project_base_dir
        ),
        resource_cwd=resource_bundle.cwd if resource_bundle is not None else None,
    )


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
    capability_runtime = bind_capability_composition_runtime(CODING_CAPABILITY_PROFILE)
    resolved_package_materializer = (
        package_materializer or _default_package_materializer(session_manager)
    )
    resolved_thinking = (
        settings.thinking_level if thinking_level is None else thinking_level
    )
    session_id = session_manager.get_header().conversation_id

    def _create_session(
        agent: Agent,
        bundle: ResourceBundle,
        extension_runner: ExtensionRunner,
        registry: WorkspaceToolRegistry | None,
        initial_active_tool_names: list[str] | None,
        session_base_prompt: str,
        session_no_tools_mode: NoToolsMode | None,
    ) -> AgentSession:
        return AgentSession(
            agent=agent,
            session_manager=session_manager,
            settings_manager=services.settings_manager,
            model_registry=services.model_registry,
            resource_loader=services.resource_loader,
            resource_bundle=bundle,
            extension_runner=extension_runner,
            tool_registry=registry,
            allowed_tool_names=[]
            if session_no_tools_mode == "all"
            else allowed_tool_names,
            active_tool_names=initial_active_tool_names,
            default_activate_new_tools=(
                session_no_tools_mode != "all" and active_tool_names is None
            ),
            show_empty_tool_prompt=session_no_tools_mode == "all",
            base_prompt=session_base_prompt,
            diagnostics_service=services.diagnostics_service,
            session_start_event=session_start_event,
            package_materializer=resolved_package_materializer,
            exec_service=services.exec_service,
            approval_resolver=approval_resolver,
            capability_runtime=capability_runtime,
        )

    result = AgentProductConstructionRuntime[
        Agent,
        AgentSession,
        ResourceBundle,
        ExtensionRunner,
        WorkspaceToolRegistry,
    ]().construct(
        AgentProductConstructionRequest(
            configuration=StandardAgentSessionConfigurationRequest(
                settings=settings,
                settings_manager=services.settings_manager,
                model_registry=services.model_registry,
                resource_loader=services.resource_loader,
                diagnostics_service=services.diagnostics_service,
                package_materializer=resolved_package_materializer,
                skill_activation_runtime=capability_runtime.skill_activation,
                session_id=session_id,
                cwd=session_manager.get_cwd(),
                create_extension_runtime=lambda bundle: ExtensionRunner(
                    bundle.extensions
                ),
                source_identity_check=_source_identity_startup_check,
                extension_flag_values=extension_flag_values,
            ),
            ports=AgentProductConstructionPorts(
                activate_resources=capability_runtime.activate_resources,
                prompt_section_composer=capability_runtime.prompt_section_composer,
                tool_pack_composer=capability_runtime.tool_pack_composer,
                list_tool_definitions=lambda runner: runner.list_tool_definitions(),
                get_tool_source_info=lambda runner, name: runner.get_tool_source_info(
                    name
                ),
                dispose_capabilities=capability_runtime.dispose,
            ),
            default_system_prompt=DEFAULT_CODING_SYSTEM_PROMPT,
            explicit_system_prompt=system_prompt,
            append_system_prompt=append_system_prompt or (),
            model=model,
            thinking_level=resolved_thinking,
            tools=tools,
            tool_registry=tool_registry,
            allowed_tool_names=allowed_tool_names,
            active_tool_names=active_tool_names,
            no_tools=no_tools,
            stream_fn=stream_fn,
            convert_to_llm=lambda messages: context_items_to_model_messages(
                messages,
                image_placeholder=(
                    "Image reading is disabled."
                    if services.settings_manager.get_block_images()
                    else None
                ),
            ),
            agent_factory=agent_factory,
            session_factory=_create_session,
            on_default_model_unavailable=lambda selection, error, reason: (
                record_default_model_unavailable(
                    selection,
                    error=error,
                    reason=reason,
                    diagnostics_service=services.diagnostics_service,
                    session_id=session_id,
                )
            ),
            set_scoped_models=lambda session, scoped_models: session.set_scoped_models(
                scoped_models
            ),
            product_tool_pack_id="coding.registry",
            extension_tool_pack_id="coding.extensions",
        )
    )
    result.session.cwd_bound_services_audit = (
        result.configuration.cwd_bound_services_audit
    )
    return result.session


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


def _default_package_materializer(
    session_manager: SessionManager,
) -> PackageMaterializer:
    return PackageMaterializer(
        install_root=resolve_session_package_install_root(
            session_dir=session_manager.get_session_dir(),
            cwd=session_manager.get_cwd(),
        ),
        backend=GitPackageMaterializerBackend(),
    )


def _source_identity_startup_check(cwd: str) -> StartupCheckResult:
    return StartupCheckResult(
        name="executable_source_identity",
        ok=True,
        code="executable_source_identity",
        level="info",
        message="Executable and import source identity captured.",
        source_path=Path(__file__).resolve(strict=False),
        details=coding_runtime_identity(cwd=cwd),
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

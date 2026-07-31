"""Product-neutral assembly of the standard Agent session runtimes.

The composition function deliberately accepts callbacks instead of importing a
Product session.  A Product therefore supplies policy and content while the
Harness owns construction and lifetime of transcript, queue, retry,
compaction, tools, resources, extensions, and command runtimes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from loushang.agent import Agent
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.model import Model, ModelSelection
from loushang.ai.utils import is_context_overflow
from loushang.harness.approval import ApprovalResolver
from loushang.harness.capabilities import CapabilityCompositionRuntime
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import DiagnosticDraft
from loushang.harness.events import (
    ConversationMetadataChanged,
)
from loushang.harness.extensions import ExtensionProviderRuntime
from loushang.harness.extensions.agent import (
    ExtensionAgentEventRuntime,
    ExtensionInputRuntime,
)
from loushang.harness.extensions.agent.hooks import ExtensionAgentHookPort
from loushang.harness.extensions.agent.input_adapter import ExtensionInputAdapter
from loushang.harness.extensions.agent.lifecycle import ExtensionEventPort
from loushang.harness.extensions.agent.replacement import ExtensionReplacementRuntime
from loushang.harness.extensions.context import (
    SessionActionDecision,
    SessionBeforeCompactResult,
    SessionBeforeForkResult,
    SessionBeforeTreeResult,
    SessionStartEvent,
)
from loushang.harness.extensions.runtime_bindings import (
    ExtensionRuntimeBindingFactory,
    ExtensionRuntimeBindings,
)
from loushang.harness.extensions.session_runtime import SessionExtensionRuntimePort
from loushang.harness.policy import PolicyEvaluator
from loushang.harness.resources.packages.session import SessionPackageController
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.resources.watcher import ResourceChangeWatcher
from loushang.harness.runtime import CancellationSignal
from loushang.harness.runtime.retry import RetryPolicy
from loushang.harness.session.bash import (
    BashCommandHook,
    BashExecutionPorts,
    BashExecutionRuntime,
)
from loushang.harness.session.bindings import (
    SessionExtensionBinding,
    SessionIdentityBinding,
    SessionMaintenanceBinding,
    SessionModelBinding,
)
from loushang.harness.session.command_controller import SessionCommandController
from loushang.harness.session.command_sources import ExtensionCommandProvider
from loushang.harness.session.diagnostics import (
    ExtensionDiagnosticsPort,
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
)
from loushang.harness.session.extension_bridge import AgentSessionExtensionBridge
from loushang.harness.session.extension_composition import (
    AgentSessionExtensionCompositionPorts,
    compose_agent_session_extensions,
)
from loushang.harness.session.inspection import AgentSessionInspector
from loushang.harness.session.resource_refresh import (
    ResourceLoaderPort,
    ResourceSettingsPort,
    SessionResourceRefreshRuntime,
)
from loushang.harness.session.runtime import (
    AfterTurnPolicyPort,
    SessionRuntime,
    TranscriptRuntimePort,
    TurnPolicyPort,
)
from loushang.harness.session.settings import SessionSettingsBinding
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace import ExecServiceBashOperations
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
    AgentTranscriptCompactionCapability,
    AgentTranscriptCompactionRuntime,
    AgentTranscriptContext,
    AgentTranscriptNavigationRuntime,
    AgentTranscriptRetryRuntime,
    AgentTranscriptSelectionRuntime,
    BranchSummaryOutput,
    CompactionHookDecision,
    CompactionHookRequest,
    CompactionPreparation,
    CompactionResult,
    ModelSelectionCatalog,
    ProductTranscriptSession,
    TranscriptCompactionPolicy,
)
from loushang.harness.workspace.exec import ExecService

if TYPE_CHECKING:
    from loushang.harness.session.tool_controller import SessionToolController

AsyncEvent = Callable[[object], Awaitable[None]]
EventDispatcher = Callable[..., Awaitable[None]]
CompactionExecutor = Callable[..., Awaitable[CompactionResult]]
CompactionRunner = Callable[..., Awaitable[CompactionResult | None]]
BranchSummaryExecutor = Callable[..., Awaitable[BranchSummaryOutput]]


class ModelDetailRegistryPort(Protocol):
    """Read-only model details needed by Product session presentation."""

    def list_models(self) -> Sequence[object]: ...


class SessionModelCatalogPort(ModelSelectionCatalog, Protocol):
    """Model selection plus detail projection used during session composition."""

    @property
    def ai_registry(self) -> ModelDetailRegistryPort: ...


class SessionExtensionCompositionPort(
    ExtensionDiagnosticsPort,
    ExtensionEventPort,
    ExtensionAgentHookPort,
    ExtensionCommandProvider,
    SessionExtensionRuntimePort[ExtensionRuntimeBindings],
    Protocol,
):
    """Extension operations consumed while composing one Agent session."""

    def list_extensions(self) -> list[dict[str, object]]: ...

    def has_handlers(self, hook_name: str) -> bool: ...

    async def emit_user_bash(
        self,
        event: object,
        *,
        cwd: str = "",
    ) -> object | None: ...

    async def emit_session_shutdown(self, event: object) -> None: ...

    async def before_session_compact(
        self,
        event: object,
    ) -> SessionBeforeCompactResult | None: ...

    async def before_session_fork(
        self,
        event: object,
    ) -> SessionBeforeForkResult | None: ...

    async def before_session_switch(
        self,
        event: object,
    ) -> SessionActionDecision | None: ...

    async def before_session_tree(
        self,
        event: object,
    ) -> SessionBeforeTreeResult | None: ...


@dataclass(frozen=True)
class SessionCompositionPorts:
    """Product inputs needed to assemble a standard session.

    These are intentionally ports and callbacks rather than Coding types.  A
    Research, Design, or OEM product can provide the same values without
    depending on ``loushang.coding``.
    """

    agent: Agent
    session_manager: ProductTranscriptSession[Any, Any]
    settings: SessionSettingsBinding
    model_registry: SessionModelCatalogPort | None
    api_provider_registry: ApiProviderRegistry
    resource_loader: ResourceLoaderPort | None
    get_resource_bundle: Callable[[], ResourceBundle | None]
    extension_runner: SessionExtensionCompositionPort | None
    tool_registry: WorkspaceToolRegistry | None
    allowed_tool_names: list[str] | None
    active_tool_names: list[str] | None
    default_activate_new_tools: bool | None
    show_empty_tool_prompt: bool
    base_prompt: str
    diagnostics_service: DiagnosticsService | None
    session_start_event: SessionStartEvent
    footer_data_provider: object
    tool_exec_service: ExecService | None
    approval_resolver: ApprovalResolver | None
    tool_policy_evaluator: PolicyEvaluator | None
    capability_runtime: CapabilityCompositionRuntime

    # Product policy and presentation callbacks.
    apply_context: Callable[[AgentTranscriptContext], None]
    refresh_agent_messages: Callable[[], None]
    dispatch_event: EventDispatcher
    record_runtime_exception: Callable[..., None]
    before_bash: BashCommandHook | None
    get_bash_definition: Callable[[], ToolDefinition | None]
    create_bash_call_id: Callable[[], str]
    command_controller: Callable[
        [SessionDiagnosticsRuntime], SessionCommandController[Any]
    ]
    extension_provider_controller: ExtensionProviderRuntime | None
    extension_replacement_controller: ExtensionReplacementRuntime | None
    extension_runtime_binding_factory: ExtensionRuntimeBindingFactory | None
    extension_bridge: AgentSessionExtensionBridge
    get_context_usage: Callable[[], object | None]
    package_controller: SessionPackageController | None
    get_resource_watch_paths: Callable[[], list[Path]]
    prepare_resource_refresh: Callable[[], None]
    rebuild_prompt_and_tools_view: Callable[[], None]
    set_resource_bundle: Callable[[ResourceBundle], None]
    record_extension_runtime_diagnostic: Callable[[DiagnosticDraft], None]
    execute_compaction: CompactionExecutor
    execute_branch_summary: BranchSummaryExecutor
    before_compaction: Callable[[CompactionHookRequest], Awaitable[CompactionHookDecision | None]]
    after_compaction: Callable[[CompactionResult, str, bool], Awaitable[None]]
    before_agent_start_system_prompt_options: Callable[[], dict[str, object]]
    compact_before_prompt: Callable[[], Awaitable[object | None]]
    sleep_for_retry: Callable[[int, CancellationSignal], Awaitable[None]]
    continue_run: Callable[[], Awaitable[None]]
    compact_internal: CompactionRunner


@dataclass
class SessionComposition:
    """All standard runtime objects assembled for one Product session."""

    capability_runtime: CapabilityCompositionRuntime
    diagnostics_bridge: SessionDiagnosticsRuntime
    tool_controller: SessionToolController
    resource_refresh_runtime: SessionResourceRefreshRuntime
    resource_watch_controller: ResourceChangeWatcher
    navigation_runtime: AgentTranscriptNavigationRuntime
    compaction_capability: AgentTranscriptCompactionCapability
    compaction_runtime: AgentTranscriptCompactionRuntime
    bash_runtime: BashExecutionRuntime
    package_controller: SessionPackageController | None
    command_controller: SessionCommandController[Any]
    extension_event_sink: ExtensionAgentEventRuntime
    retry_runtime: AgentTranscriptRetryRuntime
    session_runtime: SessionRuntime
    extension_input_runtime: ExtensionInputRuntime
    extension_message_controller: ExtensionInputAdapter
    extension_provider_controller: ExtensionProviderRuntime
    extension_replacement_controller: ExtensionReplacementRuntime
    extension_runtime_binding_factory: ExtensionRuntimeBindingFactory
    extension_bridge: AgentSessionExtensionBridge
    selection_runtime: AgentTranscriptSelectionRuntime
    model_binding: SessionModelBinding
    identity_binding: SessionIdentityBinding
    maintenance_binding: SessionMaintenanceBinding
    extension_binding: SessionExtensionBinding
    session_inspector: AgentSessionInspector


def compose_session_runtime(ports: SessionCompositionPorts) -> SessionComposition:
    """Build the standard Agent session runtime from Product ports."""

    agent = ports.agent
    session = ports.session_manager
    settings = ports.settings
    capability_runtime = ports.capability_runtime

    async def refresh_extension_runtime(reason: str) -> None:
        await ports.extension_bridge.refresh(reason=reason)

    diagnostics_bridge = SessionDiagnosticsRuntime(
        diagnostics_service=ports.diagnostics_service,
        get_scope=lambda: SessionDiagnosticScope(
            session_id=session.get_header().conversation_id,
            entry_id=session.get_leaf_id(),
        ),
        get_extension_diagnostics=lambda: ports.extension_runner,
        recorded_extension_diagnostics=(
            len(ports.extension_runner.get_diagnostics())
            if ports.extension_runner is not None
            else 0
        ),
    )

    tool_controller = _build_tool_controller(ports, diagnostics_bridge)
    resource_refresh_runtime = SessionResourceRefreshRuntime(
        get_resource_loader=lambda: ports.resource_loader,
        get_resource_bundle=ports.get_resource_bundle,
        get_cwd=session.get_cwd,
        get_extension_runtime=lambda: ports.extension_runner,
        get_settings=lambda: cast(
            ResourceSettingsPort | None,
            settings.get_settings_manager(),
        ),
        set_resource_bundle=ports.set_resource_bundle,
        rebuild_prompt_and_tools_view=ports.rebuild_prompt_and_tools_view,
        record_refresh_failure=lambda error: ports.record_extension_runtime_diagnostic(
            DiagnosticDraft(
                code="extension_resource_refresh_failed",
                message=f"Extension resource refresh failed: {error}",
            )
        ),
        sync_extension_diagnostics=lambda: diagnostics_bridge.sync_extension_diagnostics(
            phase="resource_loading"
        ),
        prepare_resource_refresh=ports.prepare_resource_refresh,
        skill_activation_runtime=capability_runtime.skill_activation,
    )
    resource_watch_controller = ResourceChangeWatcher(
        get_paths=ports.get_resource_watch_paths,
        on_change=lambda: _reload_resources_from_watch(
            resource_refresh_runtime,
            ports.extension_runner,
            lambda: resource_refresh_runtime.refresh_async(reason="reload"),
        ),
    )
    navigation_runtime = AgentTranscriptNavigationRuntime(
        session=session,
        apply_context=lambda: ports.apply_context(session.build_session_context()),
        dispatch_event=ports.dispatch_event,
        on_failure=lambda error: ports.record_runtime_exception(
            code="branch_summary_failed", exc=error
        ),
    )
    compaction_capability = _resolve_compaction_capability(session)
    compaction_runtime = AgentTranscriptCompactionRuntime(
        transcript=session,
        get_policy=lambda: _compaction_policy(
            settings.get_compaction_settings(), compaction_capability.policy
        ),
        get_model=lambda: agent.model,
        get_context_messages=lambda: list(session.build_session_context().messages),
        refresh_context=ports.refresh_agent_messages,
        prepare_compaction=compaction_capability.prepare,
        execute_compaction=lambda preparation, custom_instructions: _execute_compaction(
            ports.execute_compaction,
            agent,
            preparation,
            custom_instructions,
        ),
        dispatch_event=ports.dispatch_event,
        has_queued_messages=agent.has_queued_messages,
        before_compaction=ports.before_compaction,
        after_compaction=ports.after_compaction,
        record_runtime_exception=ports.record_runtime_exception,
    )
    bash_runtime = BashExecutionRuntime(
        BashExecutionPorts(
            get_cwd=session.get_cwd,
            get_definition=ports.get_bash_definition,
            execute_definition=tool_controller.execute_tool_definition,
            create_call_id=ports.create_bash_call_id,
            append_record=session.append_message,
            refresh_context=ports.refresh_agent_messages,
            before_execute=ports.before_bash,
            operations=(
                ExecServiceBashOperations(ports.tool_exec_service)
                if ports.tool_exec_service is not None
                else None
            ),
        )
    )

    package_controller = ports.package_controller
    command_controller = ports.command_controller(diagnostics_bridge)
    extension_event_sink = ExtensionAgentEventRuntime(
        get_extension_runtime=lambda: ports.extension_runner,
        get_cwd=session.get_cwd,
    )
    retry_runtime = AgentTranscriptRetryRuntime(
        get_policy=lambda: _retry_policy(settings.get_retry_settings()),
        get_messages=lambda: list(agent.state.messages),
        set_messages=agent.state.set_messages,
        get_context_window=lambda: agent.model.context_window,
        dispatch_event=ports.dispatch_event,
        continue_run=ports.continue_run,
        record_runtime_exception=ports.record_runtime_exception,
        sleep_for_retry=ports.sleep_for_retry,
        is_context_overflow_fn=is_context_overflow,
        wait_for_idle=lambda: session_runtime.wait_for_idle(),
    )
    session_runtime = SessionRuntime(
        agent=agent,
        transcript=TranscriptRuntimePort(
            session_id=session.get_header().conversation_id,
            append_message=session.append_message,
            commit_application_message=session.commit_application_message,
            refresh_context=lambda: ports.apply_context(session.build_session_context()),
            set_commit_observer=session.set_commit_observer,
        ),
        turn_policy=TurnPolicyPort(
            get_extension_runner=lambda: ports.extension_runner,
            get_cwd=session.get_cwd,
            extract_extension_command_invocation=(
                command_controller.extract_extension_command_invocation
            ),
            execute_command_async=command_controller.execute_command_async,
            preflight_user_input=command_controller.preflight_user_input,
            reject_queued_extension_command=(
                command_controller.raise_if_queued_extension_command
            ),
            preflight_user_input_async=command_controller.preflight_user_input_async,
            before_agent_start_system_prompt_options=ports.before_agent_start_system_prompt_options,
            sync_extension_diagnostics=diagnostics_bridge.sync_extension_diagnostics,
            compact_before_prompt_async=ports.compact_before_prompt,
        ),
        after_turn_policy=AfterTurnPolicyPort(
            emit_extension_agent_event=extension_event_sink.emit_agent_event,
            record_tool_execution_error=diagnostics_bridge.record_tool_execution_error,
            retry_controller=retry_runtime,
            compaction_controller=compaction_runtime,
            sync_extension_diagnostics=diagnostics_bridge.sync_extension_diagnostics,
            record_assistant_response_error=diagnostics_bridge.record_assistant_response_error,
            check_auto_compaction=lambda message: compaction_runtime.maybe_compact_after_turn(
                message,
                compact_internal_fn=ports.compact_internal,
                continue_run_fn=ports.continue_run,
                is_context_overflow_fn=is_context_overflow,
            ),
        ),
    )
    # The retry and turn policies close over ``session_runtime`` above.  Their
    # callbacks are invoked only after construction, so the late binding is
    # intentional and keeps the composition acyclic.
    selection_runtime = AgentTranscriptSelectionRuntime(
        session=session,
        get_model=lambda: agent.model,
        set_model=lambda model: setattr(agent, "model", model),
        get_thinking_level=lambda: agent.thinking_level,
        set_thinking_level_value=lambda level: setattr(agent, "thinking_level", level),
        get_model_catalog=lambda: ports.model_registry,
    )

    async def apply_model_selection(
        selection: object,
        *,
        source: str = "set",
    ) -> None:
        await _set_model(
            selection_runtime,
            selection,
            agent,
            ports.extension_runner,
            resource_refresh_runtime,
            refresh_extension_runtime,
            session.get_cwd,
            source=source,
        )

    extension_composition = compose_agent_session_extensions(
        AgentSessionExtensionCompositionPorts(
            agent=agent,
            session=session,
            model_registry=ports.model_registry,
            api_provider_registry=ports.api_provider_registry,
            extension_runner=ports.extension_runner,
            provider_controller=ports.extension_provider_controller,
            replacement_controller=ports.extension_replacement_controller,
            runtime_binding_factory=ports.extension_runtime_binding_factory,
            bridge=ports.extension_bridge,
            session_start_event=ports.session_start_event,
            tool_controller=tool_controller,
            command_controller=command_controller,
            selection_runtime=selection_runtime,
            session_runtime=session_runtime,
            navigation_runtime=navigation_runtime,
            resource_refresh_runtime=resource_refresh_runtime,
            resource_watch_controller=resource_watch_controller,
            footer_data_provider=ports.footer_data_provider,
            get_context_usage=ports.get_context_usage,
            set_model=apply_model_selection,
            set_session_name=lambda name: _set_session_name(
                session,
                ports.dispatch_event,
                name,
            ),
            compact=partial(
                _compact_manual,
                session_runtime,
                compaction_runtime,
            ),
            execute_branch_summary=ports.execute_branch_summary,
            record_runtime_diagnostic=ports.record_extension_runtime_diagnostic,
            sync_extension_diagnostics=(
                diagnostics_bridge.sync_extension_diagnostics
            ),
        )
    )
    model_binding = SessionModelBinding(
        get_model_selection_callback=selection_runtime.get_model_selection,
        set_model_callback=apply_model_selection,
        cycle_model_selection_callback=selection_runtime.cycle_model_selection,
        apply_cycled_model_callback=lambda selection: apply_model_selection(
            selection,
            source="cycle",
        ),
        cycle_scoped_selection_callback=selection_runtime.cycle_scoped_selection,
        set_thinking_level_callback=selection_runtime.set_thinking_level,
        cycle_thinking_level_callback=selection_runtime.cycle_thinking_level,
        supports_thinking_callback=selection_runtime.supports_thinking,
        available_thinking_levels_callback=selection_runtime.get_available_thinking_levels,
        available_models_callback=selection_runtime.get_available_models,
        available_model_details_callback=lambda: (
            list(ports.model_registry.ai_registry.list_models())
            if ports.model_registry is not None
            else []
        ),
        get_scoped_models_callback=selection_runtime.get_scoped_models,
        set_scoped_models_callback=selection_runtime.set_scoped_models,
    )
    identity_binding = SessionIdentityBinding(
        get_session_id=lambda: session.get_session_record().session_id,
        get_session_name=lambda: session.get_session_record().metadata.name,
        set_session_name_callback=lambda name: _set_session_name(
            session, ports.dispatch_event, name
        ),
    )
    maintenance_binding = SessionMaintenanceBinding(
        is_compacting_callback=lambda: compaction_runtime.is_compacting
        or navigation_runtime.is_summarizing,
        auto_retry_enabled_callback=lambda: settings.auto_retry_enabled,
        auto_compaction_enabled_callback=lambda: settings.auto_compaction_enabled,
        set_auto_retry_enabled_callback=settings.set_auto_retry_enabled,
        set_auto_compaction_enabled_callback=settings.set_auto_compaction_enabled,
        compact_callback=partial(
            _compact_manual,
            session_runtime,
            compaction_runtime,
        ),
        abort_compaction_callback=lambda: _abort_session(session_runtime),
    )
    session_inspector = AgentSessionInspector(
        agent=agent,
        session=session,
        get_session_id=lambda: session.get_session_record().session_id,
        get_session_name=lambda: session.get_session_record().metadata.name,
        get_active_tool_names=tool_controller.get_active_tool_names,
        is_retrying=lambda: retry_runtime.is_retrying,
        is_compacting=lambda: compaction_runtime.is_compacting
        or navigation_runtime.is_summarizing,
        get_last_diagnostics=diagnostics_bridge.get_last_diagnostics,
        get_model_selection=selection_runtime.get_model_selection,
        is_host_running=lambda: session_runtime.is_active,
        get_compaction_reserve_tokens=lambda: _compaction_policy(
            settings.get_compaction_settings(),
            compaction_capability.policy,
        ).reserve_tokens,
        get_compaction_compact_percent=lambda: _compaction_policy(
            settings.get_compaction_settings(),
            compaction_capability.policy,
        ).compact_percent,
        get_compaction_keep_recent_tokens=lambda: _compaction_policy(
            settings.get_compaction_settings(),
            compaction_capability.policy,
        ).keep_recent_tokens,
    )
    return SessionComposition(
        capability_runtime=capability_runtime,
        diagnostics_bridge=diagnostics_bridge,
        tool_controller=tool_controller,
        resource_refresh_runtime=resource_refresh_runtime,
        resource_watch_controller=resource_watch_controller,
        navigation_runtime=navigation_runtime,
        compaction_capability=compaction_capability,
        compaction_runtime=compaction_runtime,
        bash_runtime=bash_runtime,
        package_controller=package_controller,
        command_controller=command_controller,
        extension_event_sink=extension_event_sink,
        retry_runtime=retry_runtime,
        session_runtime=session_runtime,
        extension_input_runtime=extension_composition.input_runtime,
        extension_message_controller=extension_composition.message_controller,
        extension_provider_controller=extension_composition.provider_controller,
        extension_replacement_controller=(
            extension_composition.replacement_controller
        ),
        extension_runtime_binding_factory=(
            extension_composition.runtime_binding_factory
        ),
        extension_bridge=ports.extension_bridge,
        selection_runtime=selection_runtime,
        model_binding=model_binding,
        identity_binding=identity_binding,
        maintenance_binding=maintenance_binding,
        extension_binding=extension_composition.binding,
        session_inspector=session_inspector,
    )


def _build_tool_controller(
    ports: SessionCompositionPorts,
    diagnostics: SessionDiagnosticsRuntime,
) -> SessionToolController:
    from loushang.harness.session.tool_controller import ToolController

    return ToolController(
        agent=ports.agent,
        get_cwd=ports.session_manager.get_cwd,
        tool_registry=ports.tool_registry,
        allowed_tool_names=(
            set(ports.allowed_tool_names)
            if ports.allowed_tool_names is not None
            else None
        ),
        initial_active_tool_names=list(
            ports.active_tool_names
            or [tool.name for tool in ports.agent.tools]
        ),
        default_activate_new_tools=(
            ports.active_tool_names is None
            if ports.default_activate_new_tools is None
            else ports.default_activate_new_tools
        ),
        show_empty_tool_prompt=ports.show_empty_tool_prompt,
        base_prompt=ports.base_prompt,
        get_resource_bundle=ports.get_resource_bundle,
        get_diagnostics_service=lambda: ports.diagnostics_service,
        get_exec_service=(
            (lambda: ports.tool_exec_service)
            if ports.tool_exec_service is not None
            else None
        ),
        get_approval_resolver=lambda: ports.approval_resolver,
        policy_evaluator=ports.tool_policy_evaluator,
        emit_tool_audit_event=ports.dispatch_event,
        resource_activation_runtime=ports.capability_runtime.resource_runtime,
        prompt_section_composer=ports.capability_runtime.prompt_section_composer,
    )


def _resolve_compaction_capability(
    session: ProductTranscriptSession[Any, Any],
) -> AgentTranscriptCompactionCapability:
    capability = getattr(session, "get_runtime_capability", None)
    if callable(capability):
        value = capability("context.compaction")
        if isinstance(value, AgentTranscriptCompactionCapability):
            return value
    from loushang.harness.transcript import (
        create_agent_transcript_compaction_capability,
    )

    return create_agent_transcript_compaction_capability(
        implementation=TURN_AWARE_SUMMARY_IMPLEMENTATION,
        implementation_version=TURN_AWARE_SUMMARY_VERSION,
        config={
            "enabled": True,
            "compactPercent": 80.0,
            "reserveTokens": 8_192,
            "keepRecentTokens": 32_768,
        },
    )


def _retry_policy(settings: object) -> RetryPolicy:
    return RetryPolicy(
        enabled=bool(getattr(settings, "enabled", False)),
        max_attempts=int(getattr(settings, "max_retries", 0)),
        base_delay_ms=int(getattr(settings, "base_delay_ms", 0)),
    )


def _compaction_policy(settings: object, capability: TranscriptCompactionPolicy):
    if not getattr(settings, "enabled", False) and not any(
        hasattr(settings, field)
        for field in ("reserve_tokens", "compact_percent", "keep_recent_tokens")
    ):
        return capability
    return TranscriptCompactionPolicy(
        enabled=bool(getattr(settings, "enabled", capability.enabled)),
        reserve_tokens=_int_setting(
            settings,
            "reserve_tokens",
            capability.reserve_tokens,
        ),
        compact_percent=_float_setting(
            settings,
            "compact_percent",
            capability.compact_percent,
        ),
        keep_recent_tokens=_optional_int_setting(
            settings,
            "keep_recent_tokens",
            capability.keep_recent_tokens,
        ),
    )


def _int_setting(settings: object, name: str, fallback: int) -> int:
    value = getattr(settings, name, fallback)
    return fallback if value is None else int(value)


def _float_setting(settings: object, name: str, fallback: float) -> float:
    value = getattr(settings, name, fallback)
    return fallback if value is None else float(value)


def _optional_int_setting(
    settings: object,
    name: str,
    fallback: int | None,
) -> int | None:
    value = getattr(settings, name, fallback)
    return None if value is None else int(value)


async def sleep_for_retry(delay_ms: int, signal: CancellationSignal) -> None:
    """Sleep in abort-aware intervals for the standard Agent retry runtime."""

    remaining = max(delay_ms, 0) / 1000
    while remaining > 0:
        if getattr(signal, "aborted", False):
            raise asyncio.CancelledError
        interval = min(0.05, remaining)
        await asyncio.sleep(interval)
        remaining -= interval
    if getattr(signal, "aborted", False):
        raise asyncio.CancelledError


async def _execute_compaction(
    executor: CompactionExecutor,
    agent: Agent,
    preparation: CompactionPreparation,
    custom_instructions: str | None,
) -> CompactionResult:
    kwargs: dict[str, object] = {
        "preparation": preparation,
        "model": agent.model,
        "headers": None,
        "signal": agent.signal,
    }
    if custom_instructions is not None:
        kwargs["custom_instructions"] = custom_instructions
    return await executor(**kwargs)


async def _compact_manual(
    session_runtime: SessionRuntime,
    compaction_runtime: AgentTranscriptCompactionRuntime,
    custom_instructions: str | None = None,
) -> CompactionResult:
    session_runtime.abort()
    await session_runtime.wait_for_idle()
    result = await compaction_runtime.compact(
        reason="manual",
        will_retry=False,
        raise_on_error=True,
        custom_instructions=custom_instructions,
    )
    assert result is not None
    return result


def _abort_session(session_runtime: SessionRuntime) -> None:
    session_runtime.abort()


async def _set_model(
    selection_runtime: AgentTranscriptSelectionRuntime,
    selection: object,
    agent: Agent,
    extension_runner: ExtensionEventPort | None,
    resource_refresh_runtime: SessionResourceRefreshRuntime,
    refresh_extension_runtime: Callable[[str], Awaitable[None]],
    get_cwd: Callable[[], str],
    source: str = "set",
) -> None:
    resolved = selection_runtime.resolve_model(
        cast(Model | ModelSelection, selection)
    )
    previous = agent.model
    endpoint_id = selection.endpoint_id if isinstance(selection, ModelSelection) else None
    await selection_runtime.apply_model(resolved, endpoint_id=endpoint_id)
    await refresh_extension_runtime("model_selection_changed")
    if extension_runner is not None and previous != resolved:
        await extension_runner.emit_agent_event(
            {
                "type": "model_select",
                "model": resolved,
                "previous_model": previous,
                "source": source,
            },
            cwd=get_cwd(),
        )


async def _set_session_name(
    session: ProductTranscriptSession[Any, Any],
    dispatch: EventDispatcher,
    name: str | None,
) -> None:
    record_id = await session.append_session_info(name)
    await dispatch(
        ConversationMetadataChanged(name=name),
        source_record_id=record_id,
    )


async def _reload_resources_from_watch(
    refresh_runtime: SessionResourceRefreshRuntime,
    extension_runner: SessionExtensionCompositionPort | None,
    refresh_async: Callable[[], Awaitable[None]],
) -> None:
    await refresh_runtime.refresh_async(reason="watch")
    if extension_runner is not None:
        await refresh_async()


__all__ = [
    "SessionComposition",
    "SessionCompositionPorts",
    "compose_session_runtime",
    "sleep_for_retry",
]

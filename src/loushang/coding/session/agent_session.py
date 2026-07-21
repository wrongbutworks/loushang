from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from loushang.agent import (
    AbortSignal,
    Agent,
    AgentEvent,
    ThinkingLevel,
)
from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
from loushang.ai.model import Model, ModelSelection, Provider
from loushang.ai.types import AssistantMessage
from loushang.ai.utils import is_context_overflow
from loushang.coding.capability_plan import resolve_coding_capability_profile
from loushang.coding.compaction.adapter import (
    execute_coding_branch_summary,
    execute_coding_compaction,
)
from loushang.coding.control import (
    CompactionSettings,
    ModelRegistry,
    RetrySettings,
    SettingsManager,
)
from loushang.coding.event import (
    AgentSessionEvent,
    project_runtime_event_to_session_event,
)
from loushang.coding.extensions import ExtensionRunner
from loushang.coding.platform.footer_data_provider import FooterDataProvider
from loushang.coding.platform.session_projection import (
    project_pi_session_stats,
)
from loushang.coding.policy import InteractiveApprovalResolver
from loushang.coding.resource_runtime import (
    CodingPackageMaterializer as PackageMaterializer,
)
from loushang.coding.resource_runtime import (
    CodingResourceLoader as DefaultResourceLoader,
)
from loushang.coding.session.bash_controller import BashController
from loushang.coding.session.builtin_commands import (
    BuiltinCommandBackend,
    read_changelog_for_cwd,
)
from loushang.coding.session.command_controller import CommandController
from loushang.coding.session.export import (
    export_session_to_html,
    export_session_to_jsonl,
)
from loushang.coding.session.extension_input_adapter import (
    CodingExtensionInputAdapter,
)
from loushang.coding.session.extension_provider_controller import (
    ExtensionProviderController,
)
from loushang.coding.session.extension_replacement_controller import (
    ExtensionReplacementController,
)
from loushang.coding.session.extension_runtime_bindings import (
    ExtensionRuntimeBindingFactory,
)
from loushang.coding.session.package_controller import PackageController
from loushang.coding.session.session_settings_controller import (
    SessionSettingsController,
)
from loushang.coding.session.tool_controller import ToolController
from loushang.coding.session.types import (
    CommandExecutionResult,
)
from loushang.coding.session.usage_payload import serialize_context_usage_payload
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
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
    CompactionStatus,
    TranscriptCompactionPolicy,
    TranscriptNavigationPlan,
    TranscriptNavigationResult,
    create_agent_transcript_compaction_capability,
    normalize_branch_summary_output,
)
from loushang.harness.capabilities import (
    CapabilityCompositionRuntime,
    bind_capability_composition_runtime,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import (
    DiagnosticRecord,
    DiagnosticsQuery,
    DiagnosticSummary,
    ErrorReport,
)
from loushang.harness.events import (
    CompactionReason,
    ConversationMetadataChanged,
    PackageProgressChanged,
    RuntimeEvent,
    SessionRuntimeEventPayload,
)
from loushang.harness.extensions.agent import (
    ExtensionAgentEventRuntime,
    ExtensionAgentHookRuntime,
    ExtensionInputRuntime,
)
from loushang.harness.extensions.context import (
    ReplacedSessionContext,
    SessionBeforeCompactEvent,
    SessionBeforeTreeEvent,
    SessionShutdownEvent,
    SessionStartEvent,
)
from loushang.harness.extensions.session_runtime import ExtensionSessionRuntime
from loushang.harness.host.retry import RetryPolicy
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.packages.materializer import PackageProgressEvent
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
)
from loushang.harness.resources.watcher import ResourceChangeWatcher
from loushang.harness.runtime import CancellationSignal
from loushang.harness.session import (
    AfterTurnPolicyPort,
    SessionControlPort,
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
    SessionFacade,
    SessionResourceRefreshRuntime,
    SessionRuntime,
    TranscriptRuntimePort,
    TurnPolicyPort,
)
from loushang.harness.session.inspection import AgentSessionInspector
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import (
    ExecOutputChunk,
    ExecRequest,
    ExecResult,
    ExecService,
    ExecUpdateCallback,
)

SessionEventListener = Callable[[AgentSessionEvent], Awaitable[None] | None]
RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]


async def _execute_coding_compaction(**kwargs: object) -> object:
    """Run Coding's Product-owned summary executor for a Harness plan."""

    return await execute_coding_compaction(**kwargs)


def _retry_policy(settings: RetrySettings) -> RetryPolicy:
    """Bind Coding's persisted retry settings to the neutral retry policy."""

    return RetryPolicy(
        enabled=settings.enabled,
        max_attempts=settings.max_retries,
        base_delay_ms=settings.base_delay_ms,
    )


class AgentSession(SessionFacade):
    def __init__(
        self,
        *,
        agent: Agent,
        session_manager: SessionManager,
        settings_manager: SettingsManager | None = None,
        model_registry: ModelRegistry | None = None,
        resource_loader: DefaultResourceLoader | None = None,
        resource_bundle: ResourceBundle | None = None,
        extension_runner: ExtensionRunner | None = None,
        tool_registry: WorkspaceToolRegistry | None = None,
        allowed_tool_names: list[str] | None = None,
        active_tool_names: list[str] | None = None,
        default_activate_new_tools: bool | None = None,
        show_empty_tool_prompt: bool = False,
        base_prompt: str | None = None,
        diagnostics_service: DiagnosticsService | None = None,
        package_materializer: PackageMaterializer | None = None,
        session_start_event: SessionStartEvent | None = None,
        api_provider_registry: ApiProviderRegistry | None = None,
        footer_data_provider: FooterDataProvider | None = None,
        exec_service: ExecService | None = None,
        approval_resolver: InteractiveApprovalResolver | None = None,
        capability_runtime: CapabilityCompositionRuntime | None = None,
    ) -> None:
        self.agent = agent
        self._session_default_model = agent.model
        self.session_manager = session_manager
        self._settings_controller = SessionSettingsController(settings_manager)
        self.model_registry = model_registry
        self.api_provider_registry = (
            api_provider_registry or get_default_api_provider_registry()
        )
        self._resource_loader = resource_loader
        self.resource_bundle = resource_bundle
        self._extension_runner = extension_runner
        self._tool_registry = tool_registry
        self.diagnostics_service = diagnostics_service
        self._package_materializer = package_materializer
        self._exec_service = exec_service or ExecService()
        capability_runtime = capability_runtime or bind_capability_composition_runtime(
            resolve_coding_capability_profile()
        )
        self._capability_runtime = capability_runtime
        self.footer_data_provider = footer_data_provider or FooterDataProvider(
            self.session_manager.get_cwd()
        )
        self._base_prompt = (
            base_prompt if base_prompt is not None else self.agent.system_prompt
        )
        session_id = self.session_manager.get_header().conversation_id
        self._bind_package_progress_events()
        self._extension_ui_context: object | None = None
        self._extension_runtime_host: object | None = None
        self._session_start_event = session_start_event or SessionStartEvent(
            reason="startup"
        )
        self._approval_resolver = approval_resolver
        self._approval_session_state = (
            "active" if approval_resolver is not None else "closed"
        )
        self._diagnostics_bridge = SessionDiagnosticsRuntime(
            diagnostics_service=self.diagnostics_service,
            get_scope=lambda: SessionDiagnosticScope(
                session_id=self.session_manager.get_header().conversation_id,
                entry_id=self.session_manager.get_leaf_id(),
            ),
            get_extension_diagnostics=lambda: self._extension_runner,
            recorded_extension_diagnostics=len(extension_runner.get_diagnostics())
            if extension_runner is not None
            else 0,
        )
        self._tool_controller = ToolController(
            agent=self.agent,
            session_manager=self.session_manager,
            tool_registry=self._tool_registry,
            allowed_tool_names=set(allowed_tool_names)
            if allowed_tool_names is not None
            else None,
            initial_active_tool_names=list(
                active_tool_names or [tool.name for tool in self.agent.tools]
            ),
            default_activate_new_tools=(
                active_tool_names is None
                if default_activate_new_tools is None
                else default_activate_new_tools
            ),
            show_empty_tool_prompt=show_empty_tool_prompt,
            base_prompt=self._base_prompt,
            get_resource_bundle=lambda: self.resource_bundle,
            get_diagnostics_service=lambda: self.diagnostics_service,
            emit_tool_audit_event=self._dispatch_event,
            resource_activation_runtime=capability_runtime.resource_runtime,
            prompt_section_composer=capability_runtime.prompt_section_composer,
        )
        self._resource_refresh_runtime = SessionResourceRefreshRuntime(
            get_resource_loader=lambda: self._resource_loader,
            get_resource_bundle=lambda: self.resource_bundle,
            get_cwd=self.session_manager.get_cwd,
            get_extension_runtime=lambda: self._extension_runner,
            get_settings=self._settings_controller.get_settings_manager,
            set_resource_bundle=self._set_resource_bundle,
            rebuild_prompt_and_tools_view=self._rebuild_prompt_and_tools_view,
            record_refresh_failure=lambda error: (
                self._record_extension_runtime_diagnostic(
                    ResourceDiagnostic(
                        code="extension_resource_refresh_failed",
                        message=f"Extension resource refresh failed: {error}",
                    )
                )
            ),
            sync_extension_diagnostics=lambda: self._sync_extension_diagnostics(
                phase="resource_loading"
            ),
            prepare_resource_refresh=self._prepare_resource_refresh,
            skill_activation_runtime=capability_runtime.skill_activation,
        )
        self._resource_watch_controller = ResourceChangeWatcher(
            get_paths=self._resource_watch_paths,
            on_change=self._reload_resources_from_watch,
        )
        self._navigation_runtime = AgentTranscriptNavigationRuntime(
            session=self.session_manager,
            apply_context=self._refresh_agent_transcript_context,
            dispatch_event=self._dispatch_event,
            on_failure=lambda error: self._record_runtime_exception(
                code="branch_summary_failed",
                exc=error,
            ),
        )
        self._compaction_capability = _default_compaction_capability()
        runtime_capability = getattr(
            self.session_manager,
            "get_runtime_capability",
            None,
        )
        if callable(runtime_capability):
            runtime = runtime_capability("context.compaction")
            if isinstance(runtime, AgentTranscriptCompactionCapability):
                self._compaction_capability = runtime
        self._compaction_runtime = AgentTranscriptCompactionRuntime(
            transcript=self.session_manager,
            get_policy=lambda: _compaction_policy(
                self._get_compaction_settings(),
                self._compaction_capability.policy,
            ),
            get_model=lambda: self.agent.model,
            get_context_messages=lambda: list(
                self.session_manager.build_session_context().messages
            ),
            refresh_context=self._refresh_agent_messages,
            prepare_compaction=self._compaction_capability.prepare,
            execute_compaction=self._execute_selected_compaction,
            dispatch_event=self._dispatch_event,
            has_queued_messages=self.agent.has_queued_messages,
            before_compaction=self._before_coding_compaction,
            after_compaction=self._after_coding_compaction,
            record_runtime_exception=self._record_runtime_exception,
        )
        self._bash_controller = BashController(
            agent=self.agent,
            session_manager=self.session_manager,
            get_extension_runner=lambda: self._extension_runner,
            get_tool_registry=lambda: self._tool_registry,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
        )
        self._package_controller = PackageController(
            session_manager=self.session_manager,
            get_settings_manager=self._settings_controller.get_settings_manager,
            get_package_materializer=lambda: self._package_materializer,
            get_resource_loader=lambda: self._resource_loader,
            get_diagnostics_service=lambda: self.diagnostics_service,
            refresh_resources=self._refresh_resources_for_extension_runtime,
        )
        self._command_controller = CommandController(
            session_manager=self.session_manager,
            get_extension_runner=lambda: self._extension_runner,
            get_resource_bundle=lambda: self.resource_bundle,
            get_diagnostics_service=lambda: self.diagnostics_service,
            diagnostics_runtime=self._diagnostics_bridge,
            builtin_backend=BuiltinCommandBackend(
                get_session_info=self._get_builtin_session_info,
                set_session_name=self.set_session_name,
                export_to_html=self.export_to_html,
                export_to_jsonl=self.export_to_jsonl,
                compact=self.compact,
                reload=self.reload_extension_runtime,
                get_recent_assistant_texts=self.get_recent_assistant_texts,
                get_last_assistant_text=self.get_last_assistant_text,
                get_changelog=lambda args: read_changelog_for_cwd(
                    self.session_manager.get_cwd(), args
                ),
                new_session=self._new_session_from_extension,
                resume_session=self._switch_session_from_extension,
                fork_session=self._fork_from_extension,
                clone_session=lambda: (
                    self._extension_replacement_controller.clone_session()
                ),
                navigate_tree=self._navigate_tree_from_extension,
                import_session=(
                    lambda input_path, cwd_override=None: (
                        self._extension_replacement_controller.import_session(
                            input_path,
                            cwd_override,
                        )
                    )
                ),
                get_active_tool_names=self.get_active_tool_names,
                get_all_tools=self.get_all_tool_infos,
                set_active_tools=self.set_active_tools,
                get_default_active_tool_names=self._default_active_tool_names,
                get_extensions=self.list_extensions,
            ),
            pack_composer=capability_runtime.command_pack_composer,
        )
        self._extension_event_sink = ExtensionAgentEventRuntime(
            get_extension_runtime=lambda: self._extension_runner,
            get_cwd=self.session_manager.get_cwd,
        )
        self._retry_runtime = AgentTranscriptRetryRuntime(
            get_policy=lambda: _retry_policy(self._get_retry_settings()),
            get_messages=lambda: list(self.agent.state.messages),
            set_messages=self.agent.state.set_messages,
            get_context_window=lambda: self.agent.model.context_window,
            dispatch_event=self._dispatch_event,
            continue_run=lambda: self.continue_run(),
            record_runtime_exception=self._record_runtime_exception,
            sleep_for_retry=lambda delay_ms, signal: _sleep_for_retry(delay_ms, signal),
            is_context_overflow_fn=is_context_overflow,
            wait_for_idle=self.wait_for_idle,
        )
        self._session_runtime = SessionRuntime(
            agent=self.agent,
            transcript=TranscriptRuntimePort(
                session_id=session_id,
                append_message=self.session_manager.append_message,
                commit_application_message=(
                    self.session_manager.commit_application_message
                ),
                refresh_context=lambda: self._apply_agent_transcript_context(
                    self.session_manager.build_session_context()
                ),
                set_commit_observer=self.session_manager.set_commit_observer,
            ),
            turn_policy=TurnPolicyPort(
                get_extension_runner=lambda: self._extension_runner,
                get_cwd=self.session_manager.get_cwd,
                extract_extension_command_invocation=(
                    self._extract_extension_command_invocation
                ),
                execute_command_async=self.execute_command_async,
                preflight_user_input=self._preflight_user_input,
                reject_queued_extension_command=(
                    self._raise_if_queued_extension_command
                ),
                preflight_user_input_async=self._preflight_user_input_async,
                before_agent_start_system_prompt_options=(
                    self._before_agent_start_system_prompt_options
                ),
                sync_extension_diagnostics=self._sync_extension_diagnostics,
                compact_before_prompt_async=self._compact_before_prompt,
            ),
            after_turn_policy=AfterTurnPolicyPort(
                emit_extension_agent_event=self._emit_extension_agent_event,
                record_tool_execution_error=self._record_tool_execution_error,
                retry_controller=self._retry_runtime,
                compaction_controller=self._compaction_runtime,
                sync_extension_diagnostics=self._sync_extension_diagnostics,
                record_assistant_response_error=self._record_assistant_response_error,
                check_auto_compaction=self._check_auto_compaction,
            ),
        )
        self._extension_input_runtime = ExtensionInputRuntime(
            application_inputs=self._session_runtime.application_inputs,
            prepared_user_inputs=self._session_runtime.queue,
            run_prompt=self._session_runtime.run_agent_prompt,
        )
        self._extension_message_controller = CodingExtensionInputAdapter(
            agent=self.agent,
            runtime=self._extension_input_runtime,
        )
        self._extension_provider_controller = ExtensionProviderController(
            model_registry=self.model_registry,
            api_provider_registry=self.api_provider_registry,
        )
        self._extension_replacement_controller = ExtensionReplacementController(
            get_runtime_host=lambda: self._extension_runtime_host,
        )
        self._extension_runtime_binding_factory = ExtensionRuntimeBindingFactory(
            get_cwd=self.session_manager.get_cwd,
            session_manager=self.session_manager,
            model_registry=self.model_registry,
            get_active_tool_names=self.get_active_tool_names,
            get_all_tools=lambda: list(self.get_all_tools()),
            get_model_selection=self.get_model_selection,
            set_active_tools=self._set_active_tools_from_extension,
            set_model=self._set_model_from_extension,
            register_tool=self._register_extension_runtime_tool,
            append_entry=self._append_extension_entry,
            send_message=self._extension_message_controller.send_message,
            send_user_message=self._extension_message_controller.send_user_message,
            get_signal=lambda: self.agent.signal,
            set_session_name=self.set_session_name,
            get_session_name=lambda: self.session_name,
            set_label=self._set_extension_label,
            list_commands=self.list_commands,
            request_resource_refresh=self.request_resource_refresh,
            shutdown=self.abort,
            record_diagnostic=self._record_extension_runtime_diagnostic,
            abort=self.abort,
            is_idle=lambda: not self.agent.is_streaming,
            has_pending_messages=self._extension_message_controller.has_pending_messages,
            get_context_usage=self.get_context_usage,
            get_thinking_level=lambda: self.agent.thinking_level,
            set_thinking_level=self.set_thinking_level,
            register_provider=self._register_provider_from_extension,
            unregister_provider=self._unregister_provider_from_extension,
            set_extension_status=self._set_extension_status_from_extension,
            get_footer_data_provider=lambda: self.footer_data_provider,
            compact=self._compact_from_extension,
            get_system_prompt=lambda: self.agent.system_prompt,
            wait_for_idle=self.wait_for_idle,
            reload=self._reload_from_extension,
            navigate_tree=self._navigate_tree_from_extension,
            fork=self._fork_from_extension,
            new_session=self._new_session_from_extension,
            switch_session=self._switch_session_from_extension,
            get_ui_context=lambda: self._extension_ui_context,
            exec_command=self._exec_command_from_extension,
        )
        self._extension_runtime_controller = ExtensionSessionRuntime(
            extension_runtime=self._extension_runner,
            build_bindings=self._extension_runtime_binding_factory.build,
            session_start_event=self._session_start_event,
            refresh_resources=self._refresh_resources_for_extension_runtime_async,
            record_runtime_diagnostic=self._record_extension_runtime_diagnostic,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
        )
        self._selection_runtime = AgentTranscriptSelectionRuntime(
            session=self.session_manager,
            get_model=lambda: self.agent.model,
            set_model=lambda model: setattr(self.agent, "model", model),
            get_thinking_level=lambda: self.agent.thinking_level,
            set_thinking_level_value=lambda level: setattr(
                self.agent,
                "thinking_level",
                level,
            ),
            get_model_catalog=lambda: self.model_registry,
        )
        self._session_inspector = AgentSessionInspector(
            agent=self.agent,
            session=self.session_manager,
            get_session_id=lambda: self.session_manager.get_session_record().session_id,
            get_session_name=lambda: (
                self.session_manager.get_session_record().metadata.name
            ),
            get_active_tool_names=self.get_active_tool_names,
            is_retrying=lambda: self.is_retrying,
            is_compacting=lambda: self.is_compacting,
            get_last_diagnostics=lambda limit=50: self.get_last_diagnostics(limit),
            get_model_selection=self.get_model_selection,
            is_host_running=lambda: self._session_runtime.is_active,
            get_compaction_reserve_tokens=lambda: (
                self._get_compaction_settings().reserve_tokens
            ),
            get_compaction_compact_percent=lambda: (
                self._get_compaction_settings().compact_percent
            ),
            get_compaction_keep_recent_tokens=lambda: (
                self._get_compaction_settings().keep_recent_tokens
            ),
        )
        super().__init__(
            runtime=self._session_runtime,
            transcript=self.session_manager,
            tools=self._tool_controller,
            commands=self._command_controller,
            command_execution=self._bash_controller,
            view=self._session_inspector,
            retry=self._retry_runtime,
            identity=self,
            maintenance=self,
            resources=self._resource_refresh_runtime,
        )
        session_context = self.session_manager.build_session_context()
        self._apply_agent_transcript_context(session_context)
        if self._tool_registry is not None:
            initial_active_tool_names = (
                list(active_tool_names)
                if active_tool_names is not None
                else self._tool_controller.default_active_tool_names()
            )
            self._apply_active_tools(initial_active_tool_names)
        elif show_empty_tool_prompt:
            self._rebuild_prompt_and_tools_view()
        if self._extension_runner is not None:
            self._wire_extension_hooks()
            self._bind_extension_runtime_bindings()
        self._sync_footer_available_provider_count()

    # Public facade: state, commands, diagnostics, packages, and exports.

    def _apply_agent_transcript_context(
        self,
        session_context: AgentTranscriptContext,
    ) -> None:
        self.agent.state.set_messages(session_context.messages)
        if self.session_manager.get_entries():
            self.agent.thinking_level = session_context.thinking_level

        resolved_model = self._session_default_model
        if session_context.model is not None and self.model_registry is not None:
            selection = ModelSelection(
                provider=session_context.model["provider"],
                model_id=session_context.model["model_id"],
                endpoint_id=session_context.model.get("endpoint_id"),
            )
            with suppress(KeyError, ValueError):
                resolved_model = self.model_registry.build_model(selection)
        self.agent.model = resolved_model

    def _refresh_agent_transcript_context(self) -> None:
        self._apply_agent_transcript_context(
            self.session_manager.build_session_context()
        )

    def _refresh_agent_messages(self) -> None:
        self.agent.state.set_messages(
            list(self.session_manager.build_session_context().messages)
        )

    def set_approval_presenter(
        self,
        presenter: Callable[[dict[str, object]], Awaitable[None] | None] | None,
        *,
        dismisser: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> None:
        if self._approval_resolver is None or self._approval_session_state != "active":
            return
        if presenter is None:
            self._approval_resolver.close_session(
                "Approval presenter closed before approval was resolved"
            )
            self._approval_resolver.set_request_presenter(None)
            return
        self._approval_resolver.set_request_presenter(
            presenter,
            dismisser=dismisser,
        )
        self._approval_resolver.open_session()

    async def handle_screen_approval(self, event: Mapping[str, object]) -> bool:
        if self._approval_resolver is None:
            return False
        action_id = event.get("action_id")
        if not isinstance(action_id, str):
            return False
        reason = event.get("reason")
        if reason is not None and not isinstance(reason, str):
            reason = None
        return await self._approval_resolver.handle_result(
            action_id=action_id,
            approved=bool(event.get("approved")),
            reason=reason,
        )

    def get_model_selection(self) -> ModelSelection | None:
        return self._selection_runtime.get_model_selection()

    def get_all_tool_infos(self) -> list[dict[str, object]]:
        return self._tool_controller.get_all_tool_infos()

    def list_extensions(self) -> list[dict[str, object]]:
        return self._extension_runner.list_extensions()

    def _execute_resource_command(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        return self._command_controller.execute_resource_command(invocation_name, args)

    def _record_command_not_found(self, invocation_name: str, args: str) -> None:
        self._command_controller.record_command_not_found(invocation_name, args)

    async def get_command_argument_completions(
        self, invocation_name: str, prefix: str
    ) -> list[object] | None:
        return await self._command_controller.get_command_argument_completions(
            invocation_name, prefix
        )

    def _record_extension_command_error(
        self, *, command: object, exc: BaseException
    ) -> None:
        self._command_controller.record_extension_command_error(
            command=command, exc=exc
        )

    def get_last_diagnostics(self, limit: int = 50) -> list[DiagnosticRecord]:
        return self._diagnostics_bridge.get_last_diagnostics(limit=limit)

    def get_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        return self._diagnostics_bridge.get_diagnostics(query=query)

    def get_session_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        return self._diagnostics_bridge.get_session_diagnostics(query=query)

    def get_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        return self._diagnostics_bridge.get_diagnostics_summary(query=query)

    def get_session_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        return self._diagnostics_bridge.get_session_diagnostics_summary(query=query)

    def get_last_error_report(self) -> ErrorReport | None:
        return self._diagnostics_bridge.get_last_error_report()

    def get_packages(
        self, *, catalog_path: str | None = None
    ) -> list[dict[str, object]]:
        return self._package_controller.get_packages(catalog_path=catalog_path)

    async def materialize_package(self, source: str) -> dict[str, object]:
        return await self._package_controller.materialize_package(source)

    async def install_package(
        self, source: str, *, scope: str = "project"
    ) -> dict[str, object]:
        return await self._package_controller.install_package(source, scope=scope)

    async def update_package(self, source: str) -> dict[str, object]:
        return await self._package_controller.update_package(source)

    async def update_packages(self) -> list[dict[str, object]]:
        return await self._package_controller.update_packages()

    async def check_package_updates(self) -> list[dict[str, object]]:
        return await self._package_controller.check_package_updates()

    def remove_package(self, source: str) -> dict[str, object]:
        return self._package_controller.remove_package(source)

    def uninstall_package(
        self, source: str, *, scope: str = "project"
    ) -> dict[str, object]:
        return self._package_controller.uninstall_package(source, scope=scope)

    def get_context_usage(self):
        return serialize_context_usage_payload(super().get_context_usage())

    def get_session_stats(self) -> dict[str, object]:
        return project_pi_session_stats(
            agent=self.agent,
            session_manager=self.session_manager,
            context_usage=super().get_context_usage(),
        )

    def export_to_jsonl(self, output_path: str | None = None) -> str:
        return export_session_to_jsonl(self, output_path)

    def export_to_html(self, output_path: str | None = None) -> str:
        return export_session_to_html(self, output_path)

    def _get_builtin_session_info(self) -> dict[str, object]:
        record = self.session_manager.get_session_record()
        stats = self._session_inspector.build_session_stats()
        session_file = record.session_file
        return {
            "session_id": record.session_id,
            "session_name": record.metadata.name,
            "session_file": str(session_file) if session_file is not None else None,
            "cwd": record.cwd,
            "parent_session": record.parent_session,
            "leaf_id": record.leaf_id,
            "entry_count": stats.entry_count,
            "message_count": stats.message_count,
            "custom_message_count": stats.custom_message_count,
            "active_tool_count": stats.active_tool_count,
            "is_retrying": stats.is_retrying,
            "is_compacting": stats.is_compacting,
        }

    # Public facade: standard session properties.

    @property
    def is_compacting(self) -> bool:
        return (
            self._compaction_runtime.is_compacting
            or self._navigation_runtime.is_summarizing
        )

    @property
    def model(self) -> Model:
        return self.agent.model

    @property
    def thinking_level(self) -> ThinkingLevel:
        return self.agent.thinking_level

    @property
    def is_streaming(self) -> bool:
        return self.agent.is_streaming

    @property
    def system_prompt(self) -> str:
        return self.agent.system_prompt

    @property
    def retry_attempt(self) -> int:
        return self._retry_runtime.attempt

    @property
    def messages(self) -> list:
        return self.agent.state.messages

    @property
    def session_file(self):
        return super().get_session_file()

    @property
    def extension_runner(self) -> ExtensionRunner | None:
        return self._extension_runner

    @property
    def session_id(self) -> str:
        return self.session_manager.get_session_record().session_id

    @property
    def session_control(self) -> SessionControlPort:
        """Expose common controls without exposing Coding protocol semantics."""

        return self

    @property
    def session_name(self) -> str | None:
        return self.session_manager.get_session_record().metadata.name

    @property
    def scoped_models(self) -> list[dict[str, object]]:
        return self._selection_runtime.get_scoped_models()

    def set_scoped_models(self, scoped_models: list[dict[str, object]]) -> None:
        self._selection_runtime.set_scoped_models(scoped_models)

    @property
    def prompt_templates(self) -> list[PromptFragmentDescriptor]:
        return super().get_prompt_templates()

    @property
    def settings_manager(self) -> SettingsManager | None:
        return self._settings_controller.get_settings_manager()

    @property
    def resource_loader(self) -> DefaultResourceLoader | None:
        return self._resource_loader

    def subscribe(self, listener: SessionEventListener) -> Callable[[], None]:
        def project(event: RuntimeEvent[object]) -> AgentSessionEvent | None:
            return project_runtime_event_to_session_event(event)

        return super().subscribe(
            listener,
            project=project,
        )

    # Public facade: model, thinking, tools, and session metadata.

    async def set_model(self, model: Model | ModelSelection) -> None:
        await self._set_model_internal(model, emit_refresh=True, source="set")

    async def cycle_model(self, direction: str = "forward") -> ModelSelection | None:
        scoped_selection = await self._cycle_scoped_model(direction)
        if scoped_selection is not None:
            return scoped_selection
        selection = self._selection_runtime.cycle_model_selection(direction)
        if selection is None:
            return None
        await self._set_model_internal(selection, emit_refresh=True, source="cycle")
        return selection

    async def _cycle_scoped_model(self, direction: str) -> ModelSelection | None:
        selected = self._selection_runtime.cycle_scoped_selection(direction)
        if selected is None:
            return None
        selection, thinking_level = selected
        await self._set_model_internal(selection, emit_refresh=True, source="cycle")
        if thinking_level is not None:
            await self.set_thinking_level(thinking_level)
        return selection

    def _model_selection_from_scoped_model(
        self, scoped: dict[str, object]
    ) -> ModelSelection | None:
        return self._selection_runtime.model_selection_from_scoped_model(scoped)

    async def set_thinking_level(self, level: ThinkingLevel) -> None:
        await self._selection_runtime.set_thinking_level(level)

    async def cycle_thinking_level(self) -> ThinkingLevel | None:
        return await self._selection_runtime.cycle_thinking_level()

    def supports_thinking(self) -> bool:
        return self._selection_runtime.supports_thinking()

    def supports_xhigh_thinking(self) -> bool:
        return self.supports_thinking()

    def get_available_thinking_levels(self) -> list[ThinkingLevel]:
        return self._selection_runtime.get_available_thinking_levels()

    @property
    def steering_mode(self) -> str:
        return self.agent.steering_mode

    def set_steering_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported steering mode: {mode}")
        self.agent.steering_mode = mode
        self._persist_queue_mode("steering", mode)

    @property
    def follow_up_mode(self) -> str:
        return self.agent.follow_up_mode

    def set_follow_up_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported follow-up mode: {mode}")
        self.agent.follow_up_mode = mode
        self._persist_queue_mode("follow_up", mode)

    async def set_active_tools(self, tool_names: list[str]) -> None:
        await self._set_active_tools_internal(tool_names, emit_refresh=True)

    def get_available_models(self) -> list[ModelSelection]:
        return self._selection_runtime.get_available_models()

    def get_available_model_details(self) -> list[Model]:
        registry = self.model_registry
        if registry is None:
            return []
        return registry.ai_registry.list_models()

    async def set_session_name(self, name: str | None) -> None:
        record_id = await self.session_manager.append_session_info(name)
        await self._dispatch_event(
            ConversationMetadataChanged(name=self.session_name),
            source_record_id=record_id,
        )

    # Public facade: bash execution.

    async def execute_bash(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: list[list[str] | tuple[str, str]]
        | tuple[tuple[str, str], ...]
        | None = None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
        exclude_from_context: bool = False,
        on_output: Callable[[ExecOutputChunk], Awaitable[None] | None] | None = None,
        operations: object | None = None,
    ) -> dict[str, object]:
        return await super().execute_command_tool(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            exclude_from_context=exclude_from_context,
            on_output=on_output,
            operations=operations,
        )

    async def record_bash_result(
        self,
        command: str,
        result: dict[str, object],
        *,
        exclude_from_context: bool = False,
    ) -> None:
        await self._bash_controller.record_result(
            command=command,
            result=result,
            exclude_from_context=exclude_from_context,
        )

    @property
    def is_bash_running(self) -> bool:
        return super().is_command_running

    @property
    def has_pending_bash_messages(self) -> bool:
        return super().has_pending_command_messages

    # Public facade: extension runtime configuration.

    async def reload_extension_runtime(self) -> None:
        await self._bind_extension_runtime(reason="reload")

    async def poll_resource_changes(self) -> bool:
        return await self._resource_watch_controller.poll_once()

    def start_resource_watcher(self, *, interval_seconds: float = 1.0) -> None:
        self._resource_watch_controller.start(interval_seconds=interval_seconds)

    async def stop_resource_watcher(self) -> None:
        await self._resource_watch_controller.stop()

    def set_extension_ui_context(self, ui_context: object | None) -> None:
        self._extension_ui_context = ui_context
        self._refresh_extension_runtime_bindings()

    def set_extension_runtime_host(self, runtime_host: object | None) -> None:
        self._extension_runtime_host = runtime_host
        self._refresh_extension_runtime_bindings()

    def create_replaced_session_context(self) -> ReplacedSessionContext:
        return self._create_replaced_session_context(self)

    # Internal ports shared by model and tool controllers.

    async def _set_model_internal(
        self, model: Model | ModelSelection, *, emit_refresh: bool, source: str = "set"
    ) -> None:
        previous_model = self.agent.model
        resolved_model = self._selection_runtime.resolve_model(model)
        endpoint_id = model.endpoint_id if isinstance(model, ModelSelection) else None
        await self._selection_runtime.apply_model(
            resolved_model,
            endpoint_id=endpoint_id,
        )
        if emit_refresh:
            await self._refresh_extension_runtime(reason="model_selection_changed")
        extension_runner = self._extension_runner
        if extension_runner is not None and not _models_are_equal(
            previous_model,
            resolved_model,
        ):
            await extension_runner.emit_event(
                {
                    "type": "model_select",
                    "model": resolved_model,
                    "previous_model": previous_model,
                    "source": source,
                },
                cwd=self.session_manager.get_cwd(),
            )

    def _apply_active_tools(self, tool_names: list[str]) -> None:
        self._tool_controller.apply_active_tools(tool_names)

    async def _set_active_tools_internal(
        self, tool_names: list[str], *, emit_refresh: bool
    ) -> None:
        self._apply_active_tools(tool_names)
        if emit_refresh:
            await self._refresh_extension_runtime(reason="active_tools_changed")

    # Public facade: run controls, retry, compaction, and tree navigation.

    def abort(self) -> bool:
        return super().abort()

    def abort_bash(self) -> None:
        super().abort_command()

    @property
    def auto_retry_enabled(self) -> bool:
        return self._settings_controller.auto_retry_enabled

    @property
    def auto_compaction_enabled(self) -> bool:
        return self._settings_controller.auto_compaction_enabled

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self._settings_controller.set_auto_retry_enabled(enabled)

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        self._settings_controller.set_auto_compaction_enabled(enabled)

    async def compact(self, custom_instructions: str | None = None) -> CompactionResult:
        self.abort()
        await self.wait_for_idle()
        result = await self._compact_internal(
            reason="manual",
            will_retry=False,
            raise_on_error=True,
            custom_instructions=custom_instructions,
        )
        assert result is not None
        return result

    async def compact_session(
        self, custom_instructions: str | None = None
    ) -> CompactionResult:
        return await self.compact(custom_instructions=custom_instructions)

    async def maybe_compact_after_turn(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._check_auto_compaction(assistant_message)

    def get_compaction_status(self) -> CompactionStatus:
        return CompactionStatus(
            is_compacting=self._compaction_runtime.is_compacting,
            is_branch_summarizing=self._navigation_runtime.is_summarizing,
        )

    def abort_compaction(self) -> None:
        self.abort()

    async def navigate_tree(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
        label: str | None = None,
    ) -> TranscriptNavigationResult:
        plan = self._navigation_runtime.prepare(target_id)
        if plan is None:
            return TranscriptNavigationResult(cancelled=False)

        summary_override: BranchSummaryOutput | None = None
        if self._extension_runner is not None:
            (
                custom_instructions,
                replace_instructions,
                label,
                summary_override,
                cancelled,
            ) = await self._apply_before_tree_hook(
                plan,
                summarize=summarize,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
                label=label,
            )
            if cancelled:
                return TranscriptNavigationResult(cancelled=True)

        result = await self._navigation_runtime.navigate(
            plan,
            summarize=summarize,
            label=label,
            summary_override=summary_override,
            summary_runner=(
                self._branch_summary_runner(
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                )
                if summarize
                else None
            ),
        )
        if not summarize and self._extension_runner is not None:
            await self._extension_runner.emit_event(
                {
                    "type": "session_tree",
                    "new_leaf_id": self.session_manager.get_leaf_id(),
                    "old_leaf_id": plan.old_leaf_id,
                    "summary_entry": None,
                    "from_extension": False,
                },
                cwd=self.session_manager.get_cwd(),
            )
        return result

    def abort_branch_summary(self) -> None:
        self._navigation_runtime.abort()

    async def _apply_before_tree_hook(
        self,
        plan: TranscriptNavigationPlan,
        *,
        summarize: bool,
        custom_instructions: str | None,
        replace_instructions: bool,
        label: str | None,
    ) -> tuple[
        str | None,
        bool,
        str | None,
        BranchSummaryOutput | None,
        bool,
    ]:
        assert self._extension_runner is not None
        decision = await self._extension_runner.before_session_tree(
            SessionBeforeTreeEvent(
                target_id=plan.target_id,
                old_leaf_id=plan.old_leaf_id,
                new_leaf_id=plan.new_leaf_id,
                cwd=str(self.session_manager.get_cwd()),
                summarize=summarize,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
                label=label,
            )
        )
        if decision is not None and decision.cancel:
            self._sync_extension_diagnostics(phase="runtime")
            return (
                custom_instructions,
                replace_instructions,
                label,
                None,
                True,
            )
        if decision is None:
            return custom_instructions, replace_instructions, label, None, False
        return (
            (
                decision.custom_instructions
                if decision.custom_instructions is not None
                else custom_instructions
            ),
            (
                decision.replace_instructions
                if decision.replace_instructions is not None
                else replace_instructions
            ),
            decision.label if decision.label is not None else label,
            (
                normalize_branch_summary_output(decision.summary, from_hook=True)
                if decision.summary is not None
                else None
            ),
            False,
        )

    def _branch_summary_runner(
        self,
        *,
        custom_instructions: str | None,
        replace_instructions: bool,
    ) -> Callable[
        [Sequence[object], CancellationSignal], Awaitable[BranchSummaryOutput]
    ]:
        async def run(
            entries: Sequence[object],
            signal: CancellationSignal,
        ) -> BranchSummaryOutput:
            return await execute_coding_branch_summary(
                entries,
                model=self.agent.model,
                signal=signal,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )

        return run

    async def dispose(
        self, session_shutdown_event: SessionShutdownEvent | None = None
    ) -> None:
        try:
            await self.stop_resource_watcher()
            if self._extension_runner is not None:
                await self._extension_runner.emit_session_shutdown(
                    session_shutdown_event or SessionShutdownEvent(reason="quit")
                )
        finally:
            self._close_session_approvals()
            try:
                await self._session_runtime.dispose()
            finally:
                try:
                    await self._dispose_session_runtime_profile()
                finally:
                    self._finalize_after_session_shutdown()

    async def _dispose_after_session_shutdown(self) -> None:
        self._close_session_approvals()
        try:
            await self._session_runtime.dispose()
        finally:
            try:
                await self.stop_resource_watcher()
            finally:
                try:
                    await self._dispose_session_runtime_profile()
                finally:
                    self._finalize_after_session_shutdown()

    async def _dispose_session_runtime_profile(self) -> None:
        try:
            dispose = getattr(self.session_manager, "dispose_runtime_profile", None)
            if callable(dispose):
                result = dispose()
                if asyncio.iscoroutine(result):
                    await result
        finally:
            if self._capability_runtime is not None:
                self._capability_runtime.dispose()
                self._capability_runtime = None

    def _finalize_after_session_shutdown(self) -> None:
        self._close_session_approvals()
        if self._extension_runner is not None:
            self._invalidate_extension_contexts(
                "Extension context is stale after session replacement or shutdown."
            )
        self.footer_data_provider.dispose()

    def _stage_session_approvals(self) -> None:
        self._approval_session_state = "staged"

    def _unbind_approval_presenter_host(self) -> None:
        if self._approval_resolver is None:
            return
        if self._approval_session_state == "active":
            self._approval_resolver.close_session(
                "Approval presenter closed before approval was resolved"
            )
        self._approval_resolver.set_request_presenter(None)

    def _open_session_approvals(self) -> None:
        if self._approval_resolver is None:
            return
        self._approval_resolver.open_session()
        self._approval_session_state = "active"

    def _close_session_approvals(
        self,
        reason: str = "Session closed before approval was resolved",
    ) -> None:
        if self._approval_resolver is None or self._approval_session_state != "active":
            return
        self._approval_session_state = "closed"
        self._approval_resolver.close_session(reason)

    # Internal ports shared by extension runtime and controllers.

    def _register_provider_from_extension(self, name: str, config: object) -> None:
        self._extension_provider_controller.register_provider(name, config)
        self._sync_footer_available_provider_count()

    def _unregister_provider_from_extension(self, name: str) -> None:
        self._extension_provider_controller.unregister_provider(name)
        self._sync_footer_available_provider_count()

    def _set_extension_status_from_extension(self, key: str, text: str | None) -> None:
        self.footer_data_provider.set_extension_status(key, text)

    def _sync_footer_available_provider_count(self) -> None:
        providers = {
            selection.provider
            for selection in self._selection_runtime.get_available_models()
            if isinstance(getattr(selection, "provider", None), str)
        }
        self.footer_data_provider.set_available_provider_count(len(providers))

    def _get_registered_provider(self, name: str) -> Provider | None:
        return self._extension_provider_controller.get_registered_provider(name)

    async def start_extension_runtime(self, *, reason: str = "startup") -> None:
        await self._bind_extension_runtime(reason=reason)

    async def _bind_extension_runtime(self, *, reason: str) -> None:
        await self._extension_runtime_controller.bind(reason=reason)

    def _bind_extension_runtime_bindings(self) -> None:
        self._extension_runtime_controller.bind_bindings()

    async def _refresh_extension_runtime(self, *, reason: str) -> None:
        await self._extension_runtime_controller.refresh(reason=reason)

    def _refresh_extension_runtime_bindings(self) -> None:
        self._extension_runtime_controller.refresh_bindings()

    def _before_agent_start_system_prompt_options(self) -> dict[str, object]:
        return {
            "cwd": self.session_manager.get_cwd(),
            "selected_tools": list(self.get_active_tool_names()),
            "skills": list(self.resource_bundle.skills)
            if self.resource_bundle is not None
            else [],
            "context_files": [],
        }

    def _default_active_tool_names(self) -> list[str]:
        return self._tool_controller.default_active_tool_names()

    def _register_extension_runtime_tool(
        self, tool: object, source_info: object | None = None
    ) -> None:
        definition = self._tool_controller.register_runtime_tool(
            tool, source_info=source_info
        )
        if self._tool_registry is None:
            self._tool_registry = self._tool_controller.tool_registry
        if definition.name in self.get_active_tool_names():
            self._refresh_extension_runtime_bindings()

    def _rebuild_prompt_and_tools_view(self) -> None:
        self._tool_controller.rebuild_prompt_and_tools_view()

    def _set_resource_bundle(self, resource_bundle: ResourceBundle) -> None:
        self.resource_bundle = resource_bundle

    def _refresh_resources_for_extension_runtime(self) -> None:
        self._resource_refresh_runtime.refresh()

    async def _refresh_resources_for_extension_runtime_async(self) -> None:
        await self._resource_refresh_runtime.refresh_async(reason="reload")

    async def _reload_resources_from_watch(self) -> None:
        await self._resource_refresh_runtime.refresh_async(reason="watch")
        if self._extension_runner is not None:
            await self._refresh_extension_runtime(reason="resource_watch")

    def _resource_watch_paths(self) -> list[Path]:
        cwd = Path(self.session_manager.get_cwd())
        paths: set[Path] = {
            cwd / "AGENTS.md",
            cwd / "CLAUDE.md",
            cwd / "prompts",
            cwd / "skills",
            cwd / "extensions",
            cwd / "themes",
        }
        bundle = self.resource_bundle
        if bundle is not None:
            for descriptor in [
                *bundle.prompts,
                *bundle.skills,
                *bundle.extensions,
                *bundle.themes,
            ]:
                source_root = getattr(descriptor, "source_root", None)
                source_path = getattr(descriptor, "source_path", None)
                if isinstance(source_root, Path):
                    paths.add(source_root)
                elif isinstance(source_path, Path):
                    paths.add(source_path.parent)
        return sorted(paths, key=lambda path: path.as_posix())

    def _prepare_resource_refresh(self) -> None:
        settings_manager = self._settings_controller.get_settings_manager()
        if settings_manager is not None:
            settings_manager.reload()
        self._configure_package_resource_roots()

    def _refresh_package_resources(self) -> None:
        self._package_controller.refresh_package_resources()

    async def _prepare_configured_remote_package_records(self) -> None:
        await self._package_controller.prepare_configured_remote_package_records()

    def _record_package_projection_diagnostics(
        self, packages: list[dict[str, object]]
    ) -> None:
        self._package_controller.record_package_projection_diagnostics(packages)

    def _record_package_update_check_diagnostics(
        self, updates: list[dict[str, object]]
    ) -> None:
        self._package_controller.record_package_update_check_diagnostics(updates)

    def _configure_package_resource_roots(self) -> None:
        self._package_controller.configure_package_resource_roots()

    async def _set_active_tools_from_extension(self, tool_names: list[str]) -> None:
        await self._set_active_tools_internal(
            tool_names,
            emit_refresh=not self._extension_runtime_controller.is_refreshing,
        )

    async def _set_model_from_extension(self, selection: ModelSelection) -> None:
        resolved_model = self._selection_runtime.resolve_model(selection)
        await self._selection_runtime.apply_model(
            resolved_model,
            endpoint_id=selection.endpoint_id,
        )
        if not self._extension_runtime_controller.is_refreshing:
            await self._refresh_extension_runtime(reason="model_selection_changed")

    async def _append_extension_entry(
        self, custom_type: str, data: object | None = None
    ) -> None:
        await self.session_manager.append_custom_entry(custom_type, data)

    async def _set_extension_label(self, target_id: str, label: str | None) -> None:
        await self.session_manager.append_label(target_id, label)

    async def _send_message_from_extension(
        self, message: object, options: object | None = None
    ) -> None:
        await self._extension_message_controller.send_message(message, options)

    async def send_message(
        self, message: object, options: object | None = None
    ) -> None:
        """Submit an application message through the standard session input path."""
        await self._send_message_from_extension(message, options)

    def _create_replaced_session_context(
        self, session: object | None
    ) -> ReplacedSessionContext:
        if not isinstance(session, AgentSession):
            raise RuntimeError(
                "Session replacement callback requires a valid AgentSession instance."
            )
        return self._extension_replacement_controller.create_context(session)

    async def _send_user_message_from_extension_async(
        self, content: object, options: object | None = None
    ) -> None:
        await self._extension_message_controller.send_user_message(content, options)

    async def send_user_message(
        self, content: object, options: object | None = None
    ) -> None:
        """Submit user input through the standard session input path."""
        await self._send_user_message_from_extension_async(content, options)

    async def _exec_command_from_extension(
        self,
        command: str,
        args: Sequence[str] = (),
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
        preview_max_lines: int = 2000,
        preview_max_bytes: int = 50 * 1024,
        artifact_dir: str | None = None,
        capture_full_output: bool = True,
        rolling_max_bytes: int = 100 * 1024,
    ) -> ExecResult:
        request = ExecRequest(
            command=_normalize_extension_exec_command(command, args),
            cwd=_resolve_extension_exec_cwd(self.session_manager.get_cwd(), cwd),
            env=_normalize_extension_exec_env(env),
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            preview_max_lines=preview_max_lines,
            preview_max_bytes=preview_max_bytes,
            artifact_dir=str(artifact_dir) if artifact_dir is not None else None,
            capture_full_output=capture_full_output,
            rolling_max_bytes=rolling_max_bytes,
        )
        return await self._exec_service.execute(
            request,
            signal=self.agent.signal if signal is None else signal,
            on_update=on_update,
        )

    async def _compact_from_extension(
        self, custom_instructions: str | None = None
    ) -> object | None:
        return await self.compact(custom_instructions)

    async def _reload_from_extension(self) -> None:
        await self.reload_extension_runtime()

    def _invalidate_extension_contexts(self, message: str) -> None:
        self._extension_runtime_controller.invalidate_contexts(message)

    async def _navigate_tree_from_extension(
        self, target_id: str, options: object | None = None
    ) -> dict[str, object]:
        opts = options if isinstance(options, dict) else {}
        result = await self.navigate_tree(
            target_id,
            summarize=bool(opts.get("summarize", False)),
            custom_instructions=_optional_string(
                opts.get("customInstructions", opts.get("custom_instructions"))
            ),
            replace_instructions=bool(
                opts.get("replaceInstructions", opts.get("replace_instructions", False))
            ),
            label=_optional_string(opts.get("label")),
        )
        return {"cancelled": result.cancelled}

    async def _fork_from_extension(
        self, entry_id: str, options: object | None = None
    ) -> dict[str, object]:
        return await self._extension_replacement_controller.fork(entry_id, options)

    async def _new_session_from_extension(
        self, options: object | None = None
    ) -> dict[str, object]:
        return await self._extension_replacement_controller.new_session(options)

    async def _switch_session_from_extension(
        self, session_path: str, options: object | None = None
    ) -> dict[str, object]:
        return await self._extension_replacement_controller.switch_session(
            session_path, options
        )

    def _record_extension_runtime_diagnostic(
        self, diagnostic: ResourceDiagnostic
    ) -> None:
        self._diagnostics_bridge.record_extension_runtime_diagnostic(diagnostic)

    # Run-loop hooks and event routing.

    def _wire_extension_hooks(self) -> None:
        if self._extension_runner is None:
            return
        ExtensionAgentHookRuntime(
            agent=self.agent,
            extension_runtime=self._extension_runner,
            get_cwd=self.session_manager.get_cwd,
        ).install()

    async def _handle_agent_event(self, event: AgentEvent, signal: AbortSignal) -> None:
        await self._session_runtime.handle_agent_event(event, signal)

    async def _emit_extension_agent_event(self, event: AgentEvent) -> None:
        await self._extension_event_sink.emit_agent_event(event)

    def _bind_package_progress_events(self) -> None:
        if self._package_materializer is None:
            return
        self._package_materializer.set_progress_callback(self._emit_package_progress)

    def _emit_package_progress(self, progress: PackageProgressEvent) -> None:
        event = PackageProgressChanged(
            progress_type=progress.type,
            action=progress.action,
            source=progress.source,
            message=progress.message,
            target_path=(
                str(progress.target_path) if progress.target_path is not None else None
            ),
        )
        try:
            self._session_runtime.schedule_event_dispatch(event)
        except RuntimeError:
            self._session_runtime.dispatch_event_without_loop(event)

    async def _dispatch_event(
        self,
        event: AgentEvent | SessionRuntimeEventPayload | Mapping[str, object],
        *,
        source_record_id: str | None = None,
    ) -> None:
        await self._session_runtime.dispatch_event(
            event,
            source_record_id=source_record_id,
        )

    # Internal compatibility shims for controller-owned state.

    def _get_compaction_settings(self) -> CompactionSettings:
        return self._settings_controller.get_compaction_settings()

    def _get_retry_settings(self) -> RetrySettings:
        return self._settings_controller.get_retry_settings()

    def _ensure_settings_manager(self) -> SettingsManager:
        return self._settings_controller.ensure_settings_manager()

    def _persist_queue_mode(self, kind: str, mode: str) -> None:
        self._settings_controller.persist_queue_mode(kind, mode)

    async def _check_auto_compaction(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._compaction_runtime.maybe_compact_after_turn(
            assistant_message,
            compact_internal_fn=self._compact_internal,
            continue_run_fn=self.continue_run,
            is_context_overflow_fn=is_context_overflow,
        )

    async def _compact_before_prompt(self) -> CompactionResult | None:
        assistant_message = self._last_assistant_message()
        if assistant_message is None:
            return None
        return await self._check_auto_compaction(assistant_message)

    def _last_assistant_message(self) -> AssistantMessage | None:
        for message in reversed(self.agent.state.messages):
            if isinstance(message, AssistantMessage):
                return message
        return None

    async def _compact_internal(
        self,
        *,
        reason: CompactionReason,
        will_retry: bool,
        raise_on_error: bool,
        custom_instructions: str | None = None,
    ) -> CompactionResult | None:
        return await self._compaction_runtime.compact(
            reason=reason,
            will_retry=will_retry,
            raise_on_error=raise_on_error,
            custom_instructions=custom_instructions,
        )

    async def _execute_selected_compaction(
        self,
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> CompactionResult:
        return await self._execute_compaction_with(
            _execute_coding_compaction,
            preparation,
            custom_instructions,
        )

    async def _execute_compaction_with(
        self,
        compact_fn: Callable[..., Awaitable[CompactionResult]],
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> CompactionResult:
        kwargs: dict[str, object] = {
            "preparation": preparation,
            "model": self.agent.model,
            "headers": None,
            "signal": self.agent.signal,
        }
        if custom_instructions is not None:
            kwargs["custom_instructions"] = custom_instructions
        return await compact_fn(**kwargs)

    async def _before_coding_compaction(
        self,
        request: CompactionHookRequest,
    ) -> CompactionHookDecision | None:
        extension_runner = self._extension_runner
        if extension_runner is None:
            return None
        decision = await extension_runner.before_session_compact(
            SessionBeforeCompactEvent(
                reason=request.reason,
                cwd=str(self.session_manager.get_cwd()),
                custom_instructions=request.custom_instructions,
            )
        )
        if decision is not None and decision.cancel:
            self._sync_extension_diagnostics(phase="runtime")
            return CompactionHookDecision(cancel=True)
        result = getattr(decision, "compaction", None)
        return CompactionHookDecision(result=result) if result is not None else None

    async def _after_coding_compaction(
        self,
        result: CompactionResult,
        record_id: str,
        from_hook: bool,
    ) -> None:
        extension_runner = self._extension_runner
        if extension_runner is None:
            return
        await extension_runner.emit_event(
            {
                "type": "session_compact",
                "compaction": result,
                "compaction_entry": self.session_manager.get_entry(record_id),
                "from_extension": from_hook,
            },
            cwd=self.session_manager.get_cwd(),
        )

    def _record_runtime_exception(self, *, code: str, exc: Exception | str) -> None:
        self._diagnostics_bridge.record_runtime_exception(code=code, exc=exc)

    def _record_assistant_response_error(
        self, assistant_message: AssistantMessage
    ) -> None:
        self._diagnostics_bridge.record_assistant_response_error(assistant_message)

    def _record_tool_execution_error(self, event: AgentEvent) -> None:
        self._diagnostics_bridge.record_tool_execution_error(event)

    def _preflight_user_input(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        return self._command_controller.preflight_user_input(
            user_input,
            allow_extension_commands=allow_extension_commands,
        )

    async def _preflight_user_input_async(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        return await self._command_controller.preflight_user_input_async(
            user_input,
            allow_extension_commands=allow_extension_commands,
        )

    def _extract_extension_command_invocation(
        self, user_input: str
    ) -> tuple[str, str] | None:
        return self._command_controller.extract_extension_command_invocation(user_input)

    def _raise_if_queued_extension_command(self, user_input: str) -> None:
        self._command_controller.raise_if_queued_extension_command(user_input)

    def _record_preflight_diagnostics(
        self, diagnostics: tuple[ResourceDiagnostic, ...]
    ) -> None:
        self._command_controller.record_preflight_diagnostics(diagnostics)

    def _sync_extension_diagnostics(self, *, phase: str) -> None:
        self._diagnostics_bridge.sync_extension_diagnostics(phase=phase)


async def _sleep_for_retry(delay_ms: int, signal: CancellationSignal) -> None:
    remaining = max(delay_ms, 0) / 1000
    step = 0.05
    while remaining > 0:
        if signal.aborted:
            raise asyncio.CancelledError
        interval = min(step, remaining)
        await asyncio.sleep(interval)
        remaining -= interval
    if signal.aborted:
        raise asyncio.CancelledError


def _default_compaction_capability() -> AgentTranscriptCompactionCapability:
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


def _compaction_policy(
    settings: CompactionSettings,
    capability_policy: TranscriptCompactionPolicy,
) -> TranscriptCompactionPolicy:
    if settings == CompactionSettings():
        return capability_policy
    return TranscriptCompactionPolicy(
        enabled=settings.enabled,
        reserve_tokens=settings.reserve_tokens,
        compact_percent=settings.compact_percent,
        keep_recent_tokens=settings.keep_recent_tokens,
    )


def _models_are_equal(left: Model | None, right: Model | None) -> bool:
    if left is None or right is None:
        return left is right
    return (
        getattr(left, "provider_id", None) == getattr(right, "provider_id", None)
        and getattr(left, "endpoint_id", None) == getattr(right, "endpoint_id", None)
        and getattr(left, "id", None) == getattr(right, "id", None)
    )


def _normalize_extension_exec_command(
    command: str, args: Sequence[str]
) -> tuple[str, ...]:
    if not isinstance(command, str):
        raise TypeError("exec_command command must be a string")
    if not command:
        raise ValueError("exec_command command must not be empty")
    if isinstance(args, str):
        raise TypeError("exec_command args must be a sequence of strings, not a string")
    normalized_args = tuple(args)
    if not all(isinstance(arg, str) for arg in normalized_args):
        raise TypeError("exec_command args must contain strings")
    return (command, *normalized_args)


def _normalize_extension_exec_env(
    env: Mapping[str, str] | Sequence[tuple[str, str]] | None,
) -> tuple[tuple[str, str], ...]:
    if env is None:
        return ()
    if isinstance(env, Mapping):
        return tuple(env.items())
    return tuple(env)


def _resolve_extension_exec_cwd(session_cwd: str, cwd: str | Path | None) -> str:
    base = Path(session_cwd)
    if cwd is None:
        return str(base)
    path = Path(cwd)
    if path.is_absolute():
        return str(path)
    return str(base / path)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None

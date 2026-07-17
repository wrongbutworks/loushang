from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import cast

from loushang.agent import (
    AbortController,
    AbortSignal,
    Agent,
    AgentEvent,
    AgentMessage,
    ThinkingLevel,
)
from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
from loushang.ai.auth.registry import OAuthProviderRegistry, get_default_oauth_registry
from loushang.ai.model import Model, Provider
from loushang.ai.types import AssistantMessage, ImagePart
from loushang.coding.compaction import (
    CompactionResult,
    CompactionStatus,
    compact,
    generate_branch_summary,
    prepare_compaction,
)
from loushang.coding.control import (
    AuthManager,
    CompactionSettings,
    ModelRegistry,
    RetrySettings,
    SettingsManager,
)
from loushang.coding.event import (
    AgentSessionEvent,
    project_runtime_event_to_session_event,
)
from loushang.coding.extensions import (
    ExtensionRunner,
    ReplacedSessionContext,
    SessionShutdownEvent,
    SessionStartEvent,
)
from loushang.coding.loader import DefaultResourceLoader
from loushang.coding.package.materializer import (
    PackageMaterializer,
    PackageProgressEvent,
)
from loushang.coding.platform.footer_data_provider import FooterDataProvider
from loushang.coding.policy import InteractiveApprovalResolver
from loushang.coding.session.auth_bridge_controller import AuthBridgeController
from loushang.coding.session.auth_commands import (
    SessionOAuthLoginCallbacks,
    login_scope_kwargs,
    resolve_auth_login_target,
    validate_oauth_login_target,
)
from loushang.coding.session.bash_controller import BashController
from loushang.coding.session.builtin_commands import (
    BuiltinCommandBackend,
    read_changelog_for_cwd,
)
from loushang.coding.session.command_controller import CommandController
from loushang.coding.session.compaction_controller import CompactionController
from loushang.coding.session.export_html import export_session_to_html
from loushang.coding.session.export_jsonl import export_session_to_jsonl
from loushang.coding.session.extension_event_sink import ExtensionEventSink
from loushang.coding.session.extension_hooks import ExtensionHooks
from loushang.coding.session.extension_message_controller import (
    ExtensionMessageController,
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
from loushang.coding.session.extension_runtime_controller import (
    ExtensionRuntimeController,
)
from loushang.coding.session.package_controller import PackageController
from loushang.coding.session.resource_refresh_controller import (
    ResourceRefreshController,
)
from loushang.coding.session.resource_watcher import ResourceChangeWatcher
from loushang.coding.session.retry_controller import RetryController
from loushang.coding.session.selection_controller import SelectionController
from loushang.coding.session.session_diagnostics_bridge import SessionDiagnosticsBridge
from loushang.coding.session.session_settings_controller import (
    SessionSettingsController,
)
from loushang.coding.session.session_view_controller import SessionViewController
from loushang.coding.session.tool_controller import ToolController
from loushang.coding.session.tree_controller import TreeController
from loushang.coding.session.types import (
    AgentSessionState,
    CommandExecutionResult,
    ModelSelection,
    SessionCommandDescriptor,
    TreeNavigationResult,
)
from loushang.coding.session.usage_payload import serialize_context_usage_payload
from loushang.coding.store import SessionManager, SessionRecord
from loushang.coding.tools import ToolRegistry
from loushang.harness.agent_transcript import AgentTranscriptContext, CommitResult
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import (
    DiagnosticRecord,
    DiagnosticsQuery,
    DiagnosticSummary,
    ErrorReport,
)
from loushang.harness.events import (
    ConversationMetadataChanged,
    OrderedEventBus,
    PackageProgressChanged,
    QueueChanged,
    RuntimeEvent,
    RuntimeEventPublisher,
    SessionRuntimeEventPayload,
    ToolPolicyAuditEvent,
    ToolPolicyAuditEventType,
    TranscriptRecordCommitted,
    session_runtime_event_kind,
)
from loushang.harness.host.runtime import HostRuntime
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
)
from loushang.harness.session import (
    AgentEventRouter,
    PromptController,
    QueueController,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.workspace.exec import (
    ExecOutputChunk,
    ExecRequest,
    ExecResult,
    ExecService,
    ExecUpdateCallback,
)

SessionEventListener = Callable[[AgentSessionEvent], Awaitable[None] | None]
RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]


class AgentSession:
    def __init__(
        self,
        *,
        agent: Agent,
        session_manager: SessionManager,
        settings_manager: SettingsManager | None = None,
        model_registry: ModelRegistry | None = None,
        auth_manager: AuthManager | None = None,
        resource_loader: DefaultResourceLoader | None = None,
        resource_bundle: ResourceBundle | None = None,
        extension_runner: ExtensionRunner | None = None,
        tool_registry: ToolRegistry | None = None,
        allowed_tool_names: list[str] | None = None,
        active_tool_names: list[str] | None = None,
        default_activate_new_tools: bool | None = None,
        show_empty_tool_prompt: bool = False,
        base_prompt: str | None = None,
        diagnostics_service: DiagnosticsService | None = None,
        package_materializer: PackageMaterializer | None = None,
        session_start_event: SessionStartEvent | None = None,
        api_provider_registry: ApiProviderRegistry | None = None,
        oauth_provider_registry: OAuthProviderRegistry | None = None,
        footer_data_provider: FooterDataProvider | None = None,
        exec_service: ExecService | None = None,
        approval_resolver: InteractiveApprovalResolver | None = None,
    ) -> None:
        self.agent = agent
        self._session_default_model = agent.model
        self.session_manager = session_manager
        self._settings_controller = SessionSettingsController(settings_manager)
        self.model_registry = model_registry
        self.api_provider_registry = (
            api_provider_registry or get_default_api_provider_registry()
        )
        self.oauth_provider_registry = (
            oauth_provider_registry or get_default_oauth_registry()
        )
        self._auth_manager = auth_manager
        self._resource_loader = resource_loader
        self.resource_bundle = resource_bundle
        self._extension_runner = extension_runner
        self._tool_registry = tool_registry
        self.diagnostics_service = diagnostics_service
        self._package_materializer = package_materializer
        self._exec_service = exec_service or ExecService()
        self.footer_data_provider = footer_data_provider or FooterDataProvider(
            self.session_manager.get_cwd()
        )
        self._base_prompt = (
            base_prompt if base_prompt is not None else self.agent.system_prompt
        )
        self._runtime_event_bus = OrderedEventBus[RuntimeEvent[object]](
            async_listener_error=(
                "Async runtime event listeners require a running event loop."
            )
        )
        session_id = self.session_manager.get_header().conversation_id
        self._runtime_event_publisher = RuntimeEventPublisher[object](
            stream_id=f"session:{session_id}",
            bus=self._runtime_event_bus,
        )
        self.session_manager.set_commit_observer(self._schedule_transcript_commit)
        self._host_runtime: HostRuntime[None] = HostRuntime(
            abort_driver=self.agent.abort,
            wait_for_idle_driver=self.agent.wait_for_idle,
            is_running_driver=lambda: self.agent.is_streaming,
        )
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
        self._diagnostics_bridge = SessionDiagnosticsBridge(
            diagnostics_service=self.diagnostics_service,
            session_manager=self.session_manager,
            get_extension_runner=lambda: self._extension_runner,
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
        )
        self._resource_refresh_controller = ResourceRefreshController(
            get_resource_loader=lambda: self._resource_loader,
            get_resource_bundle=lambda: self.resource_bundle,
            get_cwd=self.session_manager.get_cwd,
            get_extension_runner=lambda: self._extension_runner,
            get_settings_manager=self._settings_controller.get_settings_manager,
            set_resource_bundle=self._set_resource_bundle,
            rebuild_prompt_and_tools_view=self._rebuild_prompt_and_tools_view,
            record_runtime_diagnostic=self._record_extension_runtime_diagnostic,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
            prepare_resource_refresh=self._prepare_resource_refresh,
        )
        self._resource_watch_controller = ResourceChangeWatcher(
            get_paths=self._resource_watch_paths,
            on_change=self._reload_resources_from_watch,
        )
        self._tree_controller = TreeController(
            agent=self.agent,
            session_manager=self.session_manager,
            extension_runner=self._extension_runner,
            dispatch_event=self._dispatch_event,
            apply_session_context=self._apply_agent_transcript_context,
            record_runtime_exception=self._record_runtime_exception,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
        )
        self._compaction_controller = CompactionController(
            agent=self.agent,
            session_manager=self.session_manager,
            get_settings=self._get_compaction_settings,
            get_extension_runner=lambda: self._extension_runner,
            dispatch_event=self._dispatch_event,
            record_runtime_exception=self._record_runtime_exception,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
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
                clone_session=self._clone_from_builtin,
                navigate_tree=self._navigate_tree_from_extension,
                import_session=self._import_from_builtin,
                get_active_tool_names=self.get_active_tool_names,
                get_all_tools=self.getAllTools,
                set_active_tools=self.set_active_tools,
                get_default_active_tool_names=self._default_active_tool_names,
                get_extensions=self.list_extensions,
                login_provider=self._login_from_builtin,
            ),
        )
        self._extension_event_sink = ExtensionEventSink(
            get_extension_runner=lambda: self._extension_runner,
            get_cwd=self.session_manager.get_cwd,
        )
        self._queue_controller = QueueController(
            agent=self.agent,
            preflight_user_input=self._preflight_user_input,
            reject_extension_command=self._raise_if_queued_extension_command,
            emit_queue_update=self._emit_queue_update,
        )
        self._retry_controller = RetryController(
            agent=self.agent,
            get_settings=self._get_retry_settings,
            dispatch_event=self._dispatch_event,
            continue_run=lambda: self.continue_run(),
            record_runtime_exception=self._record_runtime_exception,
            sleep_for_retry=lambda delay_ms, signal: _sleep_for_retry(delay_ms, signal),
            wait_for_idle=self.wait_for_idle,
        )
        self._extension_message_controller = ExtensionMessageController(
            agent=self.agent,
            session_manager=self.session_manager,
            queue_controller=self._queue_controller,
            dispatch_event=self._dispatch_event,
            run_prompt=self._run_agent_prompt,
        )
        self._extension_provider_controller = ExtensionProviderController(
            model_registry=self.model_registry,
            api_provider_registry=self.api_provider_registry,
            oauth_provider_registry=self.oauth_provider_registry,
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
            request_resource_refresh=self._request_resource_refresh,
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
        self._extension_runtime_controller = ExtensionRuntimeController(
            extension_runner=self._extension_runner,
            build_bindings=self._extension_runtime_binding_factory.build,
            session_start_event=self._session_start_event,
            refresh_resources=self._refresh_resources_for_extension_runtime_async,
            record_runtime_diagnostic=self._record_extension_runtime_diagnostic,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
        )
        self._auth_bridge_controller = AuthBridgeController(
            agent=self.agent,
            auth_manager=self._auth_manager,
            diagnostics_service=self.diagnostics_service,
            session_manager=self.session_manager,
        )
        self._selection_controller = SelectionController(
            agent=self.agent,
            session_manager=self.session_manager,
            get_model_registry=lambda: self.model_registry,
            get_extension_runner=lambda: self._extension_runner,
            refresh_extension_runtime=lambda reason: self._refresh_extension_runtime(
                reason=reason
            ),
            is_extension_runtime_refreshing=lambda: (
                self._extension_runtime_controller.is_refreshing
            ),
            record_model_auth_resolution=self._record_model_auth_resolution,
        )
        self._view_controller = SessionViewController(
            agent=self.agent,
            session_manager=self.session_manager,
            get_active_tool_names=self.get_active_tool_names,
            is_retrying=lambda: self.is_retrying,
            is_compacting=lambda: self.is_compacting,
            get_last_diagnostics=lambda limit=50: self.get_last_diagnostics(limit),
            get_model_selection=self.get_model_selection,
            is_host_running=lambda: self._host_runtime.is_active,
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
        self._prompt_controller = PromptController(
            agent=self.agent,
            queue_controller=self._queue_controller,
            get_extension_runner=lambda: self._extension_runner,
            get_cwd=self.session_manager.get_cwd,
            extract_extension_command_invocation=self._extract_extension_command_invocation,
            execute_command_async=self.execute_command_async,
            preflight_user_input_async=self._preflight_user_input_async,
            before_agent_start_system_prompt_options=self._before_agent_start_system_prompt_options,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
            compact_before_prompt_async=self._compact_before_prompt,
            run_prompt=lambda messages: self._run_agent_prompt(messages),
        )
        self._agent_event_router = AgentEventRouter(
            append_message=self.session_manager.append_message,
            dispatch_event=self._dispatch_event,
            emit_extension_agent_event=self._emit_extension_agent_event,
            record_tool_execution_error=self._record_tool_execution_error,
            retry_controller=self._retry_controller,
            compaction_controller=self._compaction_controller,
            sync_extension_diagnostics=self._sync_extension_diagnostics,
            record_assistant_response_error=self._record_assistant_response_error,
            check_auto_compaction=self._check_auto_compaction,
            consume_user_message=self._queue_controller.mark_message_consumed,
        )
        self._unsubscribe_agent = self.agent.subscribe(self._handle_agent_event)
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
        self._configure_auth_bridge()

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

    def get_state(self) -> AgentSessionState:
        return self._view_controller.get_state(
            steering=self._queue_controller.get_steering_messages(),
            follow_up=self._queue_controller.get_follow_up_messages(),
        )

    def get_session_context(self) -> AgentTranscriptContext:
        return self.session_manager.build_session_context()

    def get_session_record(self) -> SessionRecord:
        return self.session_manager.get_session_record()

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
        return self._selection_controller.get_model_selection()

    def get_active_tool_names(self) -> list[str]:
        return self._tool_controller.get_active_tool_names()

    def getActiveToolNames(self) -> list[str]:
        return self.get_active_tool_names()

    def get_all_tools(self) -> list[ToolDefinition]:
        return self._tool_controller.get_all_tools()

    def getAllTools(self) -> list[dict[str, object]]:
        return self._tool_controller.get_all_tool_infos()

    def getToolDefinition(self, name: str) -> ToolDefinition | None:
        return self._tool_controller.get_tool_definition(name)

    def list_commands(self) -> list[SessionCommandDescriptor]:
        return self._command_controller.list_commands()

    def list_extensions(self) -> list[dict[str, object]]:
        return self._extension_runner.list_extensions()

    def listExtensions(self) -> list[dict[str, object]]:
        return self.list_extensions()

    async def execute_command_async(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        return await self._command_controller.execute_command_async(
            invocation_name, args
        )

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
        return serialize_context_usage_payload(
            self._view_controller.get_context_usage()
        )

    def get_session_stats(self) -> dict[str, object]:
        return self._view_controller.get_pi_style_stats()

    def get_session_state(self) -> dict[str, object]:
        return self._pi_style_session_state()

    def export_to_jsonl(self, output_path: str | None = None) -> str:
        return export_session_to_jsonl(self, output_path)

    def exportToJsonl(self, output_path: str | None = None) -> str:
        return self.export_to_jsonl(output_path)

    def export_to_html(self, output_path: str | None = None) -> str:
        return export_session_to_html(self, output_path)

    def exportToHtml(self, output_path: str | None = None) -> str:
        return self.export_to_html(output_path)

    def _get_builtin_session_info(self) -> dict[str, object]:
        record = self.session_manager.get_session_record()
        stats = self._view_controller.build_session_stats()
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

    def _pi_style_session_state(self) -> dict[str, object]:
        state = self.get_state()
        session_file = self.session_file
        steering = list(state.steering)
        follow_up = list(state.follow_up)
        return {
            "sessionId": self.session_id,
            "sessionFile": str(session_file) if session_file is not None else None,
            "sessionName": self.session_name,
            "runStatus": state.run.status,
            "isStreaming": state.run.status == "running",
            "queue": {
                "steering": steering,
                "followUp": follow_up,
            },
            "pendingMessageCount": len(steering) + len(follow_up),
            "isCompacting": state.is_compacting,
            "isRetrying": state.is_retrying,
            "thinkingLevel": state.thinking_level,
            "modelSelection": _model_selection_payload(state.model_selection),
            "activeToolNames": list(state.active_tool_names),
            "steeringMode": self.agent.steering_mode,
            "followUpMode": self.agent.follow_up_mode,
            "autoCompactionEnabled": self.auto_compaction_enabled,
            "messageCount": len(self.get_session_context().messages),
        }

    # Public facade: session properties and compatibility aliases.

    @property
    def is_compacting(self) -> bool:
        return (
            self._compaction_controller.is_compacting
            or self._tree_controller.is_branch_summarizing
        )

    @property
    def model(self) -> Model:
        return self.agent.model

    @property
    def thinkingLevel(self) -> ThinkingLevel:
        return self.agent.thinking_level

    @property
    def isStreaming(self) -> bool:
        return self.agent.is_streaming

    @property
    def systemPrompt(self) -> str:
        return self.agent.system_prompt

    @property
    def retryAttempt(self) -> int:
        return self._retry_controller.attempt

    @property
    def _retry_attempt(self) -> int:
        return self._retry_controller.attempt

    @_retry_attempt.setter
    def _retry_attempt(self, value: int) -> None:
        self._retry_controller.attempt = value

    @property
    def _retry_future(self) -> asyncio.Future[None] | object | None:
        return self._retry_controller.retry_future

    @_retry_future.setter
    def _retry_future(self, value: asyncio.Future[None] | object | None) -> None:
        self._retry_controller.retry_future = value

    @property
    def _retry_abort_controller(self) -> AbortController | None:
        return self._retry_controller.cancel_handle

    @_retry_abort_controller.setter
    def _retry_abort_controller(self, value: AbortController | None) -> None:
        self._retry_controller.cancel_handle = value

    @property
    def isCompacting(self) -> bool:
        return self.is_compacting

    @property
    def messages(self) -> list:
        return self.agent.state.messages

    @property
    def session_file(self):
        return self.session_manager.get_session_file()

    @property
    def sessionFile(self) -> str | None:
        session_file = self.session_file
        return str(session_file) if session_file is not None else None

    @property
    def extension_runner(self) -> ExtensionRunner | None:
        return self._extension_runner

    @property
    def session_id(self) -> str:
        return self.session_manager.get_session_record().session_id

    @property
    def sessionId(self) -> str:
        return self.session_id

    @property
    def session_name(self) -> str | None:
        return self.session_manager.get_session_record().metadata.name

    @property
    def sessionName(self) -> str | None:
        return self.session_name

    @property
    def scopedModels(self) -> list[dict[str, object]]:
        return self._selection_controller.get_scoped_models()

    def setScopedModels(self, scoped_models: list[dict[str, object]]) -> None:
        self._selection_controller.set_scoped_models(scoped_models)

    @property
    def promptTemplates(self) -> list[PromptFragmentDescriptor]:
        return self._resource_refresh_controller.get_prompt_templates()

    @property
    def settings_manager(self) -> SettingsManager | None:
        return self._settings_controller.get_settings_manager()

    @property
    def resource_loader(self) -> DefaultResourceLoader | None:
        return self._resource_loader

    @property
    def resourceLoader(self) -> DefaultResourceLoader | None:
        return self._resource_loader

    def subscribe(self, listener: SessionEventListener) -> Callable[[], None]:
        def project(event: RuntimeEvent[object]) -> Awaitable[None] | None:
            projected = project_runtime_event_to_session_event(event)
            if projected is None:
                return None
            return listener(projected)

        return self._runtime_event_bus.subscribe(project)

    def subscribe_runtime_events(
        self,
        listener: RuntimeEventListener,
    ) -> Callable[[], None]:
        return self._runtime_event_bus.subscribe(listener)

    # Run entrypoint.

    async def prompt(
        self,
        user_input: str,
        images: list[ImagePart] | None = None,
        *,
        streaming_behavior: str | None = None,
        source: str | None = None,
        preflight_result: Callable[[bool], None] | None = None,
    ) -> None:
        await self._prompt_controller.prompt(
            user_input,
            images=images,
            streaming_behavior=streaming_behavior,
            source=source,
            preflight_result=preflight_result,
        )

    # Public facade: queued steering and follow-up messages.

    def steer(self, user_input: str, images: list[ImagePart] | None = None) -> None:
        self._queue_controller.steer(user_input, images=images)

    def follow_up(self, user_input: str, images: list[ImagePart] | None = None) -> None:
        self._queue_controller.follow_up(user_input, images=images)

    @property
    def pending_message_count(self) -> int:
        return self._queue_controller.pending_message_count

    @property
    def pendingMessageCount(self) -> int:
        return self.pending_message_count

    def get_steering_messages(self) -> list[str]:
        return self._queue_controller.get_steering_messages()

    def getSteeringMessages(self) -> list[str]:
        return self.get_steering_messages()

    def get_follow_up_messages(self) -> list[str]:
        return self._queue_controller.get_follow_up_messages()

    def getFollowUpMessages(self) -> list[str]:
        return self.get_follow_up_messages()

    def clear_queue(self) -> dict[str, list[str]]:
        return self._queue_controller.clear_queue()

    def clearQueue(self) -> dict[str, list[str]]:
        return self.clear_queue()

    # Public facade: model, thinking, tools, and session metadata.

    async def _login_from_builtin(self, raw_target: str | None) -> dict[str, object]:
        if self.model_registry is None:
            raise RuntimeError("Model registry is not available.")
        from loushang.ai.auth import oauth_login, register_builtin_oauth_providers

        target = resolve_auth_login_target(
            raw_target,
            current_model=getattr(self.agent, "model", None),
            registry=self.model_registry.ai_registry,
        )
        validate_oauth_login_target(target)
        register_builtin_oauth_providers(registry=self.oauth_provider_registry)
        callbacks = SessionOAuthLoginCallbacks()
        scope_kwargs = login_scope_kwargs(target)
        credentials = await oauth_login(
            target.provider,
            callbacks,
            registry=self.oauth_provider_registry,
            endpoint_id=scope_kwargs["endpoint_id"],
            model_id=scope_kwargs["model_id"],
            persist=True,
        )
        current_model = getattr(self.agent, "model", None)
        if isinstance(current_model, Model):
            self._auth_bridge_controller.record_model_auth_resolution(current_model)
        return {
            "provider": credentials.provider,
            "scope": target.scope,
            "endpoint_id": target.endpoint_id,
            "model_id": target.model_id,
            "message": _login_success_message(target.provider, target.scope),
            "auth_url": (callbacks.auth_info or {}).get("url"),
            "progress": list(callbacks.progress),
        }

    async def set_model(self, model: Model | ModelSelection) -> None:
        await self._set_model_internal(model, emit_refresh=True, source="set")

    async def setModel(self, model: Model | ModelSelection) -> None:
        await self.set_model(model)

    async def cycle_model(self, direction: str = "forward") -> ModelSelection | None:
        return await self._selection_controller.cycle_model(direction)

    async def cycleModel(self, direction: str = "forward") -> ModelSelection | None:
        return await self.cycle_model(direction)

    async def _cycle_scoped_model(self, direction: str) -> ModelSelection | None:
        return await self._selection_controller.cycle_scoped_model(direction)

    def _model_selection_from_scoped_model(
        self, scoped: dict[str, object]
    ) -> ModelSelection | None:
        return self._selection_controller.model_selection_from_scoped_model(scoped)

    async def set_thinking_level(self, level: ThinkingLevel) -> None:
        await self._selection_controller.set_thinking_level(level)

    async def setThinkingLevel(self, level: ThinkingLevel) -> None:
        await self.set_thinking_level(level)

    async def cycle_thinking_level(self) -> ThinkingLevel | None:
        return await self._selection_controller.cycle_thinking_level()

    async def cycleThinkingLevel(self) -> ThinkingLevel | None:
        return await self.cycle_thinking_level()

    def supports_thinking(self) -> bool:
        return self._selection_controller.supports_thinking()

    def supportsThinking(self) -> bool:
        return self.supports_thinking()

    def supports_xhigh_thinking(self) -> bool:
        return self._selection_controller.supports_xhigh_thinking()

    def supportsXhighThinking(self) -> bool:
        return self.supports_xhigh_thinking()

    def get_available_thinking_levels(self) -> list[ThinkingLevel]:
        return self._selection_controller.get_available_thinking_levels()

    def getAvailableThinkingLevels(self) -> list[ThinkingLevel]:
        return self.get_available_thinking_levels()

    @property
    def steering_mode(self) -> str:
        return self.agent.steering_mode

    @property
    def steeringMode(self) -> str:
        return self.steering_mode

    def set_steering_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported steering mode: {mode}")
        self.agent.steering_mode = mode
        self._persist_queue_mode("steering", mode)

    @property
    def follow_up_mode(self) -> str:
        return self.agent.follow_up_mode

    @property
    def followUpMode(self) -> str:
        return self.follow_up_mode

    def set_follow_up_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported follow-up mode: {mode}")
        self.agent.follow_up_mode = mode
        self._persist_queue_mode("follow_up", mode)

    async def set_active_tools(self, tool_names: list[str]) -> None:
        await self._set_active_tools_internal(tool_names, emit_refresh=True)

    async def setActiveToolsByName(self, tool_names: list[str]) -> None:
        await self.set_active_tools(tool_names)

    def get_available_models(self) -> list[ModelSelection]:
        return self._selection_controller.get_available_models()

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

    async def setSessionName(self, name: str | None) -> None:
        await self.set_session_name(name)

    def getSessionName(self) -> str | None:
        return self.session_name

    def get_user_messages_for_forking(self) -> list[dict[str, str]]:
        return self._view_controller.get_user_messages_for_forking()

    def getUserMessagesForForking(self) -> list[dict[str, str]]:
        return self._view_controller.get_pi_style_user_messages_for_forking()

    def get_entry_text(self, entry_id: str) -> str | None:
        return self._view_controller.get_entry_text(entry_id)

    def get_last_assistant_text(self) -> str | None:
        return self._view_controller.get_last_assistant_text()

    def getLastAssistantText(self) -> str | None:
        return self.get_last_assistant_text()

    def get_recent_assistant_texts(self) -> tuple[str, ...]:
        return self._view_controller.get_recent_assistant_texts()

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
        return await self._bash_controller.execute_bash(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            exclude_from_context=exclude_from_context,
            on_output=on_output,
            operations=operations,
        )

    async def executeBash(
        self,
        command: str,
        on_chunk: Callable[[str], Awaitable[None] | None] | None = None,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return await self._bash_controller.execute_pi_style(
            command, on_chunk=on_chunk, options=options
        )

    async def recordBashResult(
        self,
        command: str,
        result: dict[str, object],
        options: dict[str, object] | None = None,
    ) -> None:
        await self._bash_controller.record_pi_style_result(command, result, options)

    def abortBash(self) -> None:
        self.abort_bash()

    @property
    def isBashRunning(self) -> bool:
        return self._bash_controller.is_running

    @property
    def hasPendingBashMessages(self) -> bool:
        return self._bash_controller.has_pending_messages

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

    def createReplacedSessionContext(self) -> ReplacedSessionContext:
        return self.create_replaced_session_context()

    # Internal ports shared by model and tool controllers.

    async def _set_model_internal(
        self, model: Model | ModelSelection, *, emit_refresh: bool, source: str = "set"
    ) -> None:
        await self._selection_controller.set_model(
            model, emit_refresh=emit_refresh, source=source
        )

    def _apply_active_tools(self, tool_names: list[str]) -> None:
        self._tool_controller.apply_active_tools(tool_names)

    async def _set_active_tools_internal(
        self, tool_names: list[str], *, emit_refresh: bool
    ) -> None:
        self._apply_active_tools(tool_names)
        if emit_refresh:
            await self._refresh_extension_runtime(reason="active_tools_changed")

    def _build_tool_context(self, *, tool_call_id: str) -> object:
        return self._tool_controller.build_tool_context(tool_call_id=tool_call_id)

    # Public facade: run controls, retry, compaction, and tree navigation.

    async def continue_run(self) -> None:
        await self._host_runtime.run(self.agent.continue_run)

    def abort(self) -> None:
        self._host_runtime.abort()

    def abort_bash(self) -> None:
        self._bash_controller.abort()

    async def wait_for_idle(self) -> None:
        await self._host_runtime.wait_for_idle()

    def abort_retry(self) -> None:
        self._retry_controller.abort()

    async def wait_for_retry(self) -> None:
        await self._retry_controller.wait()

    @property
    def is_retrying(self) -> bool:
        return self._retry_controller.is_retrying

    @property
    def auto_retry_enabled(self) -> bool:
        return self._settings_controller.auto_retry_enabled

    @property
    def auto_compaction_enabled(self) -> bool:
        return self._settings_controller.auto_compaction_enabled

    @property
    def autoCompactionEnabled(self) -> bool:
        return self.auto_compaction_enabled

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self._settings_controller.set_auto_retry_enabled(enabled)

    @property
    def isRetrying(self) -> bool:
        return self.is_retrying

    @property
    def autoRetryEnabled(self) -> bool:
        return self.auto_retry_enabled

    def setAutoRetryEnabled(self, enabled: bool) -> None:
        self.set_auto_retry_enabled(enabled)

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        self._settings_controller.set_auto_compaction_enabled(enabled)

    def setAutoCompactionEnabled(self, enabled: bool) -> None:
        self.set_auto_compaction_enabled(enabled)

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
            is_compacting=self._compaction_controller.is_compacting,
            is_branch_summarizing=self._tree_controller.is_branch_summarizing,
        )

    def abortCompaction(self) -> None:
        self.abort_compaction()

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
    ) -> TreeNavigationResult:
        return await self._tree_controller.navigate_tree(
            target_id,
            summarize=summarize,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
            label=label,
            generate_branch_summary_fn=generate_branch_summary,
        )

    def abort_branch_summary(self) -> None:
        self._tree_controller.abort_branch_summary()

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
                await self._host_runtime.dispose()
            finally:
                self._finalize_after_session_shutdown()

    async def _dispose_after_session_shutdown(self) -> None:
        self._close_session_approvals()
        try:
            await self._host_runtime.dispose()
        finally:
            try:
                await self.stop_resource_watcher()
            finally:
                self._finalize_after_session_shutdown()

    def _finalize_after_session_shutdown(self) -> None:
        self._close_session_approvals()
        if self._extension_runner is not None:
            self._invalidate_extension_contexts(
                "Extension context is stale after session replacement or shutdown."
            )
        self._unsubscribe_agent()
        self.session_manager.set_commit_observer(None)
        self._runtime_event_bus.clear()
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
            for selection in self._selection_controller.get_available_models()
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

    def _resolve_active_tool_definitions(
        self, tool_names: list[str]
    ) -> tuple[list[ToolDefinition], list[str]]:
        return self._tool_controller.resolve_active_tool_definitions(tool_names)

    def _is_tool_allowed(self, name: str) -> bool:
        return self._tool_controller.is_tool_allowed(name)

    def _filter_allowed_tool_names(self, tool_names: list[str]) -> list[str]:
        return self._tool_controller.filter_allowed_tool_names(tool_names)

    def _filter_allowed_tool_definitions(
        self, definitions: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return self._tool_controller.filter_allowed_tool_definitions(definitions)

    def _tool_source_info(self, name: str) -> object | None:
        return self._tool_controller.tool_source_info(name)

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
        self._resource_refresh_controller.refresh_resources_for_extension_runtime()

    async def _refresh_resources_for_extension_runtime_async(self) -> None:
        await self._resource_refresh_controller.refresh_resources_for_extension_runtime_async(
            reason="reload"
        )

    async def _reload_resources_from_watch(self) -> None:
        await self._resource_refresh_controller.refresh_resources_for_extension_runtime_async(
            reason="watch"
        )
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
        await self._selection_controller.set_model_from_extension(selection)

    async def _append_extension_entry(
        self, custom_type: str, data: object | None = None
    ) -> None:
        await self.session_manager.append_custom_entry(custom_type, data)

    async def _set_extension_label(self, target_id: str, label: str | None) -> None:
        await self.session_manager.append_label(target_id, label)

    def _request_resource_refresh(self) -> None:
        self._resource_refresh_controller.request_resource_refresh()

    # Extension API bridge.

    async def sendCustomMessage(
        self, message: object, options: object | None = None
    ) -> None:
        await self._send_message_from_extension(message, options)

    async def sendMessage(self, message: object, options: object | None = None) -> None:
        await self.sendCustomMessage(message, options)

    async def sendUserMessage(
        self, content: object, options: object | None = None
    ) -> None:
        await self._send_user_message_from_extension_async(content, options)

    async def _send_message_from_extension(
        self, message: object, options: object | None = None
    ) -> None:
        await self._extension_message_controller.send_message(message, options)

    async def _send_message_from_extension_async(self, app_message) -> None:
        await self._extension_message_controller._send_message_async(app_message)

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

    async def _clone_from_builtin(self) -> dict[str, object]:
        runtime_host = self._extension_runtime_host
        if runtime_host is None:
            return {"cancelled": True}
        clone = getattr(runtime_host, "clone", None)
        if callable(clone):
            result = clone()
            if asyncio.iscoroutine(result):
                result = await result
            return dict(result) if isinstance(result, dict) else {"cancelled": False}
        clone_session = getattr(runtime_host, "clone_session", None)
        if callable(clone_session):
            previous = getattr(runtime_host, "get_current_session", lambda: None)()
            result = clone_session()
            if asyncio.iscoroutine(result):
                result = await result
            current = getattr(runtime_host, "get_current_session", lambda: result)()
            return {"cancelled": current is previous}
        return {"cancelled": True}

    async def _import_from_builtin(
        self, input_path: str, cwd_override: str | None = None
    ) -> dict[str, object]:
        runtime_host = self._extension_runtime_host
        if runtime_host is None:
            return {"cancelled": True}
        importer = getattr(runtime_host, "import_from_jsonl", None)
        if not callable(importer):
            return {"cancelled": True}
        result = importer(input_path, cwd_override)
        if asyncio.iscoroutine(result):
            result = await result
        return dict(result) if isinstance(result, dict) else {"cancelled": False}

    async def _run_extension_replaced_session_callbacks(
        self,
        session: object | None,
        options: object | None,
        *,
        include_setup: bool = False,
    ) -> None:
        await self._extension_replacement_controller.run_replaced_session_callbacks(
            session,
            options,
            include_setup=include_setup,
        )

    def _record_extension_runtime_diagnostic(
        self, diagnostic: ResourceDiagnostic
    ) -> None:
        self._diagnostics_bridge.record_extension_runtime_diagnostic(diagnostic)

    # Run-loop hooks and event routing.

    def _wire_extension_hooks(self) -> None:
        if self._extension_runner is None:
            return
        ExtensionHooks(
            agent=self.agent,
            extension_runner=self._extension_runner,
            get_cwd=self.session_manager.get_cwd,
        ).install()

    async def _handle_agent_event(self, event: AgentEvent, signal: AbortSignal) -> None:
        await self._agent_event_router.handle(event, signal)

    async def _run_agent_prompt(
        self,
        prompt: object,
        images: list[ImagePart] | None = None,
    ) -> None:
        normalized_prompt = cast(str | AgentMessage | list[AgentMessage], prompt)

        async def operation() -> None:
            if images is None:
                await self.agent.prompt(normalized_prompt)
            else:
                await self.agent.prompt(normalized_prompt, images=images)

        await self._host_runtime.run(operation)

    async def _emit_extension_agent_event(self, event: AgentEvent) -> None:
        await self._extension_event_sink.emit_agent_event(event)

    def _emit_queue_update(self) -> None:
        event = QueueChanged(snapshot=self._queue_controller.get_queue_snapshot())
        try:
            self._schedule_event_dispatch(event)
        except RuntimeError:
            self._dispatch_event_without_loop(event)

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
            self._schedule_event_dispatch(event)
        except RuntimeError:
            self._dispatch_event_without_loop(event)

    async def _dispatch_event(
        self,
        event: AgentEvent | SessionRuntimeEventPayload | Mapping[str, object],
        *,
        source_record_id: str | None = None,
    ) -> None:
        kind, payload = _normalize_runtime_event(event)
        await self._runtime_event_publisher.publish(
            kind,
            payload,
            session_id=self.session_manager.get_header().conversation_id,
            source_record_id=source_record_id,
        )

    def _schedule_transcript_commit(self, result: CommitResult) -> None:
        receipt = result.receipt
        if result.disposition != "committed" or receipt is None:
            return
        conversation_id = self.session_manager.get_header().conversation_id
        self._runtime_event_publisher.schedule(
            "transcript.record_committed",
            TranscriptRecordCommitted(
                conversation_id=conversation_id,
                record_id=result.record_id,
                revision=receipt.revision,
                committed_at=receipt.committed_at,
            ),
            session_id=conversation_id,
            source_record_id=result.record_id,
        )

    def _schedule_event_dispatch(
        self, event: SessionRuntimeEventPayload
    ) -> asyncio.Task[None]:
        return self._runtime_event_publisher.schedule(
            _runtime_event_kind(event),
            event,
            session_id=self.session_manager.get_header().conversation_id,
        )

    def _dispatch_event_without_loop(self, event: SessionRuntimeEventPayload) -> None:
        self._runtime_event_publisher.publish_without_loop(
            _runtime_event_kind(event),
            event,
            session_id=self.session_manager.get_header().conversation_id,
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

    def _ensure_retry_future(self) -> asyncio.Future[None]:
        return self._retry_controller.ensure_future()

    async def _finish_retry(
        self,
        *,
        success: bool,
        attempt: int,
        final_error: str | None = None,
    ) -> None:
        await self._retry_controller.finish(
            success=success, attempt=attempt, final_error=final_error
        )

    def _should_prepare_retry(self, assistant_message: AssistantMessage) -> bool:
        return self._retry_controller.should_prepare_retry(assistant_message)

    def _is_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        return self._retry_controller.is_retryable_error(assistant_message)

    async def _handle_retryable_error(
        self, assistant_message: AssistantMessage
    ) -> bool:
        return await self._retry_controller.handle_retryable_error(assistant_message)

    def _apply_navigation_leaf(self, new_leaf_id: str | None) -> None:
        if new_leaf_id is None:
            self.session_manager.reset_leaf()
        else:
            self.session_manager.branch(new_leaf_id)

    async def _check_auto_compaction(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._compaction_controller.maybe_compact_after_turn(
            assistant_message,
            compact_internal_fn=self._compact_internal,
            continue_run_fn=self.continue_run,
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
        reason: str,
        will_retry: bool,
        raise_on_error: bool,
        custom_instructions: str | None = None,
    ) -> CompactionResult | None:
        return await self._compaction_controller.compact(
            reason=reason,
            will_retry=will_retry,
            raise_on_error=raise_on_error,
            custom_instructions=custom_instructions,
            compact_fn=compact,
            prepare_compaction_fn=prepare_compaction,
        )

    def _record_runtime_exception(self, *, code: str, exc: Exception | str) -> None:
        self._diagnostics_bridge.record_runtime_exception(code=code, exc=exc)

    def _configure_auth_bridge(self) -> None:
        self._auth_bridge_controller.configure_auth_bridge()

    def _get_runtime_api_key(self, provider: str) -> str | None:
        return self._auth_bridge_controller.get_runtime_api_key(provider)

    def _record_model_auth_resolution(self, model: Model) -> None:
        self._auth_bridge_controller.record_model_auth_resolution(model)

    def _record_model_auth_resolution_failure(
        self, model: Model, exc: Exception
    ) -> None:
        self._auth_bridge_controller.record_model_auth_resolution_failure(model, exc)

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

    async def _record_bash_execution(
        self,
        *,
        command: str,
        result: dict[str, object],
        exclude_from_context: bool,
    ) -> None:
        await self._bash_controller.record_result(
            command=command,
            result=result,
            exclude_from_context=exclude_from_context,
        )


async def _sleep_for_retry(delay_ms: int, signal: AbortSignal) -> None:
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


_AGENT_EVENT_TYPES = {
    "agent_start",
    "agent_end",
    "turn_start",
    "turn_end",
    "message_start",
    "message_update",
    "message_end",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
}
_TOOL_POLICY_AUDIT_EVENT_TYPES = {
    "tool_policy_evaluated",
    "tool_approval_requested",
    "tool_approval_resolved",
}


def _normalize_runtime_event(
    event: AgentEvent | SessionRuntimeEventPayload | Mapping[str, object],
) -> tuple[str, object]:
    if isinstance(event, Mapping):
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type in _AGENT_EVENT_TYPES:
            return f"agent.{event_type}", event
        if isinstance(event_type, str) and event_type in _TOOL_POLICY_AUDIT_EVENT_TYPES:
            payload = ToolPolicyAuditEvent(
                event_type=cast(ToolPolicyAuditEventType, event_type),
                details={key: value for key, value in event.items() if key != "type"},
            )
            return session_runtime_event_kind(payload), payload
        raise TypeError("Runtime event mapping has an unsupported type")
    return session_runtime_event_kind(event), event


def _runtime_event_kind(event: SessionRuntimeEventPayload) -> str:
    return session_runtime_event_kind(event)


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


def _login_success_message(provider: str, scope: str) -> str:
    return f"Login complete for {provider} ({scope} scope)."


def _model_selection_payload(selection: ModelSelection | None) -> dict[str, str] | None:
    if selection is None:
        return None
    return {"provider": selection.provider, "modelId": selection.model_id}

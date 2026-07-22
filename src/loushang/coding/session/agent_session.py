from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from loushang.agent import (
    Agent,
)
from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
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
from loushang.coding.extensions import ExtensionRunner
from loushang.coding.platform.changelog import read_changelog_for_cwd
from loushang.coding.platform.footer_data_provider import FooterDataProvider
from loushang.coding.policy import InteractiveApprovalResolver
from loushang.coding.resource_runtime import (
    CodingPackageMaterializer as PackageMaterializer,
)
from loushang.coding.resource_runtime import (
    CodingResourceLoader as DefaultResourceLoader,
)
from loushang.coding.session.command_controller import CommandController
from loushang.coding.session.package_controller import PackageController
from loushang.coding.session_manager import SessionManager
from loushang.harness.agent_transcript import (
    BranchSummaryOutput,
    CompactionHookDecision,
    CompactionHookRequest,
    CompactionResult,
)
from loushang.harness.capabilities import (
    CapabilityCompositionRuntime,
    bind_capability_composition_runtime,
)
from loushang.harness.context import serialize_context_usage_payload
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.events import (
    AgentSessionEvent,
    RuntimeEvent,
    project_session_runtime_event,
)
from loushang.harness.extensions import ExtensionProviderRuntime
from loushang.harness.extensions.agent.replacement import ExtensionReplacementRuntime
from loushang.harness.extensions.context import (
    ReplacedSessionContext,
    SessionBeforeCompactEvent,
    SessionStartEvent,
)
from loushang.harness.extensions.provider_config import provider_from_extension_config
from loushang.harness.extensions.runtime_bindings import ExtensionRuntimeBindingFactory
from loushang.harness.resources.types import (
    ResourceBundle,
)
from loushang.harness.runtime import CancellationSignal
from loushang.harness.session import (
    SessionDiagnosticsRuntime,
    SessionFacade,
    StandardSessionCommandPorts,
)
from loushang.harness.session.agent_adapter import (
    AgentSessionAdapterMixin,
    initialize_composed_session,
)
from loushang.harness.session.composition import (
    SessionCompositionPorts,
    compose_session_runtime,
)
from loushang.harness.session.operations_runtime import (
    SessionOperationsPorts,
)
from loushang.harness.session.settings import SessionSettingsBinding
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import (
    ExecService,
)

SessionEventListener = Callable[[AgentSessionEvent], Awaitable[None] | None]
# The former Coding-named projection is now implemented by Harness.
# project_runtime_event_to_session_event remains an external migration label.
RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]


def _copy_to_clipboard(text: str) -> object:
    """Bind the shared /copy command to the active terminal clipboard."""

    from loushang.tui.clipboard import copy_to_clipboard

    return copy_to_clipboard(text)


async def _execute_coding_compaction(**kwargs: object) -> object:
    """Run Coding's Product-owned summary executor for a Harness plan."""

    return await execute_coding_compaction(**kwargs)


async def _execute_coding_compaction_runtime(**kwargs: object) -> object:
    """Resolve the Coding compaction adapter at call time for Product hooks."""

    return await _execute_coding_compaction(**kwargs)


async def _execute_coding_branch_summary(
    entries: Sequence[object], **kwargs: object
) -> BranchSummaryOutput:
    """Resolve the Product summary executor at call time for test and plugin hooks."""

    return await execute_coding_branch_summary(entries, **kwargs)


class AgentSession(AgentSessionAdapterMixin, SessionFacade):
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
        self._settings_controller = SessionSettingsBinding(
            settings_manager=settings_manager,
            create_settings_manager=SettingsManager,
            default_compaction=CompactionSettings,
            default_retry=RetrySettings,
            get_steering_mode_callback=lambda: self.agent.steering_mode,
            set_steering_mode_callback=self._set_agent_steering_mode,
            get_follow_up_mode_callback=lambda: self.agent.follow_up_mode,
            set_follow_up_mode_callback=self._set_agent_follow_up_mode,
        )
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
        self._package_controller = PackageController(
            session_manager=self.session_manager,
            get_settings_manager=self._settings_controller.get_settings_manager,
            get_package_materializer=lambda: self._package_materializer,
            get_resource_loader=lambda: self._resource_loader,
            get_diagnostics_service=lambda: self.diagnostics_service,
            refresh_resources=self._refresh_resources_for_extension_runtime,
        )
        self._extension_provider_controller = ExtensionProviderRuntime(
            model_registry=self.model_registry,
            api_provider_registry=self.api_provider_registry,
            provider_factory=provider_from_extension_config,
        )
        self._extension_replacement_controller = ExtensionReplacementRuntime(
            get_runtime_host=lambda: self._extension_runtime_host,
        )
        self._extension_runtime_binding_factory = ExtensionRuntimeBindingFactory(
            get_cwd=self.session_manager.get_cwd,
            session_manager=self.session_manager,
            model_registry=self.model_registry,
            get_active_tool_names=lambda: self.get_active_tool_names(),
            get_all_tools=lambda: list(self.get_all_tools()),
            get_model_selection=lambda: self.get_model_selection(),
            set_active_tools=self._set_active_tools_from_extension,
            set_model=self._set_model_from_extension,
            register_tool=lambda tool, source_info=None: self._register_extension_runtime_tool(
                tool, source_info
            ),
            append_entry=self._append_extension_entry,
            send_message=lambda message, options=None: self._extension_message_controller.send_message(
                message, options
            ),
            send_user_message=lambda content, options=None: self._extension_message_controller.send_user_message(
                content, options
            ),
            get_signal=lambda: self.agent.signal,
            set_session_name=self.set_session_name,
            get_session_name=lambda: self.session_name,
            set_label=self._set_extension_label,
            list_commands=lambda: self.list_commands(),
            request_resource_refresh=self.request_resource_refresh,
            shutdown=self.abort,
            record_diagnostic=self._record_extension_runtime_diagnostic,
            abort=self.abort,
            is_idle=lambda: not self.agent.is_streaming,
            has_pending_messages=lambda: self._extension_message_controller.has_pending_messages(),
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

        def build_command_controller(
            diagnostics_runtime: SessionDiagnosticsRuntime,
        ) -> CommandController:
            return CommandController(
                session_manager=self.session_manager,
                get_extension_runner=lambda: self._extension_runner,
                get_resource_bundle=lambda: self.resource_bundle,
                get_diagnostics_service=lambda: self.diagnostics_service,
                diagnostics_runtime=diagnostics_runtime,
                standard_ports=StandardSessionCommandPorts(
                get_session_info=self._get_builtin_session_info,
                set_session_name=self.set_session_name,
                export_html=self.export_to_html,
                export_jsonl=self.export_to_jsonl,
                compact=self.compact,
                reload=self.reload_extension_runtime,
                get_recent_assistant_texts=self.get_recent_assistant_texts,
                get_last_assistant_text=self.get_last_assistant_text,
                copy_text=_copy_to_clipboard,
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

        composition = compose_session_runtime(
            SessionCompositionPorts(
                agent=self.agent,
                session_manager=self.session_manager,
                settings=self._settings_controller,
                model_registry=self.model_registry,
                api_provider_registry=self.api_provider_registry,
                resource_loader=self._resource_loader,
                resource_bundle=self.resource_bundle,
                get_resource_bundle=lambda: self.resource_bundle,
                extension_runner=self._extension_runner,
                tool_registry=self._tool_registry,
                allowed_tool_names=allowed_tool_names,
                active_tool_names=active_tool_names,
                default_activate_new_tools=default_activate_new_tools,
                show_empty_tool_prompt=show_empty_tool_prompt,
                base_prompt=self._base_prompt,
                diagnostics_service=self.diagnostics_service,
                package_materializer=self._package_materializer,
                session_start_event=self._session_start_event,
                footer_data_provider=self.footer_data_provider,
                exec_service=self._exec_service,
                approval_resolver=self._approval_resolver,
                capability_runtime=capability_runtime,
                apply_context=self._apply_agent_transcript_context,
                refresh_agent_transcript_context=self._refresh_agent_transcript_context,
                refresh_agent_messages=self._refresh_agent_messages,
                dispatch_event=self._dispatch_event,
                record_runtime_exception=self._record_runtime_exception,
                before_bash=self._before_bash,
                get_bash_definition=self._get_bash_definition,
                create_bash_call_id=self._create_bash_call_id,
                command_controller=build_command_controller,
                extension_provider_controller=self._extension_provider_controller,
                extension_replacement_controller=self._extension_replacement_controller,
                extension_runtime_binding_factory=self._extension_runtime_binding_factory,
                get_extension_runtime_host=lambda: self._extension_runtime_host,
                get_context_usage=lambda: self.get_context_usage(),
                package_controller=self._package_controller,
                get_resource_watch_paths=self._resource_watch_paths,
                prepare_resource_refresh=self._prepare_resource_refresh,
                rebuild_prompt_and_tools_view=self._rebuild_prompt_and_tools_view,
                set_resource_bundle=self._set_resource_bundle,
                record_extension_runtime_diagnostic=self._record_extension_runtime_diagnostic,
                refresh_resources_for_extension_runtime=self._refresh_resources_for_extension_runtime,
                refresh_resources_for_extension_runtime_async=self._refresh_resources_for_extension_runtime_async,
                get_changelog=lambda args: read_changelog_for_cwd(
                    self.session_manager.get_cwd(), args
                ),
                copy_to_clipboard=_copy_to_clipboard,
                execute_compaction=_execute_coding_compaction_runtime,
                execute_branch_summary=lambda entries, signal: self._branch_summary_runner(
                    custom_instructions=None,
                    replace_instructions=False,
                )(entries, signal),
                before_compaction=self._before_coding_compaction,
                after_compaction=self._after_coding_compaction,
                before_tree=self._apply_before_tree_hook,
                project_event=project_session_runtime_event,
                serialize_context_usage=serialize_context_usage_payload,
                before_agent_start_system_prompt_options=self._before_agent_start_system_prompt_options,
                compact_before_prompt=self._compact_before_prompt,
                refresh_extension_runtime=lambda reason: self._refresh_extension_runtime(
                    reason=reason
                ),
                set_extension_ui_context=self._set_extension_ui_context,
                set_extension_runtime_host=self._set_extension_runtime_host,
                on_shutdown=self._finalize_after_session_shutdown,
                sleep_for_retry=lambda delay, signal: _sleep_for_retry(delay, signal),
                continue_run=lambda: self._session_runtime.schedule_continue_run(),
                compact_internal=lambda **kwargs: self._compact_internal(**kwargs),
            )
        )
        initialize_composed_session(
            self,
            composition,
            operations_ports=SessionOperationsPorts(
                composition=composition,
                agent=self.agent,
                session_manager=self.session_manager,
                extension_runner=self._extension_runner,
                execute_compaction=_execute_coding_compaction_runtime,
                execute_branch_summary=_execute_coding_branch_summary,
                before_tree=self._apply_before_tree_hook,
                before_compaction=self._before_coding_compaction,
                after_compaction=self._after_coding_compaction,
                dispose_runtime_profile=self._dispose_session_runtime_profile,
                finalize_shutdown=self._finalize_after_session_shutdown,
                invalidate_extension_contexts=self._invalidate_extension_contexts,
                sync_extension_diagnostics=self._sync_extension_diagnostics,
                close_approvals=self._close_session_approvals,
                continue_run=lambda: self._session_runtime.schedule_continue_run(),
            ),
            settings=self._settings_controller,
            session_manager=self.session_manager,
            active_tool_names=active_tool_names,
            show_empty_tool_prompt=show_empty_tool_prompt,
            tool_registry=self._tool_registry,
            apply_context=self._apply_agent_transcript_context,
            sync_footer=self._sync_footer_available_provider_count,
        )

    # Public facade: state, commands, diagnostics, packages, and exports.

    def get_context_usage(self):
        return serialize_context_usage_payload(super().get_context_usage())

    # Public facade: standard session properties.

    # Public facade: model, thinking, tools, and session metadata.

    # Internal ports shared by model and tool controllers.
    def _finalize_after_session_shutdown(self) -> None:
        self._close_session_approvals()
        if self._extension_runner is not None:
            self._invalidate_extension_contexts(
                "Extension context is stale after session replacement or shutdown."
            )
        self.footer_data_provider.dispose()
        self._capability_runtime = None

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

    def _create_replaced_session_context(
        self, session: object | None
    ) -> ReplacedSessionContext:
        if not isinstance(session, AgentSession):
            raise RuntimeError(
                "Session replacement callback requires a valid AgentSession instance."
            )
        return self._extension_replacement_controller.create_context(session)

    def _branch_summary_runner(
        self,
        *,
        custom_instructions: str | None,
        replace_instructions: bool,
    ) -> Callable[[Sequence[object], CancellationSignal], Awaitable[BranchSummaryOutput]]:
        async def run(
            entries: Sequence[object], signal: CancellationSignal
        ) -> BranchSummaryOutput:
            return await execute_coding_branch_summary(
                entries,
                model=self.agent.model,
                signal=signal,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )

        return run

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

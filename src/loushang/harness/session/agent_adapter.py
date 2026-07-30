"""Reusable control surface for Product Agent session adapters.

The mixin deliberately relies on attributes assembled by ``SessionComposition``
and ``SessionOperations``.  It contains only lifecycle, resource, event, and
operation plumbing; Product subclasses retain their policies and content.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Generic, TypeVar, cast

from loushang.agent import AgentEvent
from loushang.ai.model import ModelSelection
from loushang.ai.types import AssistantMessage
from loushang.harness.approval import (
    ApprovalOutcome,
    ApprovalPermissionsSnapshot,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import DiagnosticDraft, DiagnosticPhase
from loushang.harness.events import (
    CompactionReason,
    PackageProgressChanged,
    PermissionProfileChanged,
    project_session_runtime_event,
)
from loushang.harness.extensions.agent import ExtensionAgentHookRuntime
from loushang.harness.extensions.context import (
    SessionBeforeForkEvent,
    SessionBeforeSwitchEvent,
    SessionBeforeTreeEvent,
    SessionShutdownEvent,
    SessionStartEvent,
)
from loushang.harness.permissions import (
    PermissionProfileScope,
    PermissionProfileSnapshot,
    permission_profile,
    permission_profile_snapshot,
)
from loushang.harness.resources.packages.materializer import PackageProgressEvent
from loushang.harness.runtime import copy_file_exclusive
from loushang.harness.session.capabilities import (
    UserCommandHookResult,
    UserCommandRequest,
)
from loushang.harness.session.composition import SessionComposition
from loushang.harness.session.diagnostics import (
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
)
from loushang.harness.session.event_types import AgentSessionEvent
from loushang.harness.session.export import (
    export_session_to_html,
    export_session_to_jsonl,
)
from loushang.harness.session.facade import (
    ApprovalPresentationLease,
    ApprovalRequestDismisser,
    ApprovalRequestPresenter,
    SessionFacade,
)
from loushang.harness.session.lifecycle import (
    ForkProfile,
    ForkSelection,
    MissingSessionCwdError,
    SessionLifecycleDecision,
    SessionLifecycleHooks,
    SessionLifecycleTransition,
)
from loushang.harness.session.operations_runtime import (
    SessionOperations,
    SessionOperationsPorts,
)
from loushang.harness.session.product_runtime import (
    ProductSessionRuntime,
    ProductSessionRuntimePorts,
    dispose_session_only,
    emit_session_shutdown,
    invoke_session_factory,
    resolve_agent_transcript_fork_target,
    resolve_existing_cwd,
    session_file_from_session,
    session_id_from_session,
)
from loushang.harness.session.transcript_lifecycle import (
    ProductTranscriptSessionBinding,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace.protocol import (
    normalize_bash_result_from_protocol,
)
from loushang.harness.transcript import (
    AgentTranscriptContext,
    BranchSummaryOutput,
    CompactionPreparation,
    CompactionResult,
    CompactionStatus,
    ProductTranscriptSession,
    TranscriptNavigationPlan,
    TranscriptNavigationResult,
    normalize_branch_summary_output,
)
from loushang.harness.workspace.exec import ExecRequest, ExecResult, ExecUpdateCallback

SessionT = TypeVar("SessionT")
TranscriptT = TypeVar("TranscriptT", bound=ProductTranscriptSession)


@dataclass
class _AgentApprovalPresentationLease:
    close_callback: Callable[[str], None]
    closed: bool = False

    def supersede(self) -> None:
        """Invalidate this lease without closing the shared approval channel."""

        self.closed = True

    def close(
        self,
        reason: str = "Approval presenter closed before approval was resolved",
    ) -> None:
        if self.closed:
            return
        self.closed = True
        self.close_callback(reason)


class _AgentSessionApprovalInteraction:
    """Thin Product adapter over the existing approval resolver authority."""

    def __init__(self, session: AgentSessionAdapterMixin) -> None:
        self._session = session

    def bind_presenter(
        self,
        presenter: ApprovalRequestPresenter,
        *,
        dismisser: ApprovalRequestDismisser | None = None,
    ) -> ApprovalPresentationLease:
        return self._session._bind_approval_presenter(
            presenter,
            dismisser=dismisser,
        )

    async def respond(
        self,
        action_id: str,
        *,
        outcome: ApprovalOutcome,
        reason: str | None = None,
    ) -> bool:
        return await self._session.handle_screen_approval(
            {
                "action_id": action_id,
                "outcome": outcome,
                "reason": reason,
            }
        )

    def permissions_snapshot(self) -> ApprovalPermissionsSnapshot:
        return self._session.get_approval_permissions()

    def permission_profile_snapshot(self) -> PermissionProfileSnapshot:
        return self._session.get_permission_profile_snapshot()

    async def apply_permission_action(self, action: str) -> bool:
        return await self._session.apply_approval_permission_action(action)


class AgentSessionAdapterMixin:
    """Common methods shared by Coding and other Product session adapters."""

    @property
    def resource_loader(self):
        return self._resource_loader

    def create_replaced_session_context(self, session: object | None = None):
        return self._create_replaced_session_context(
            self if session is None else session
        )

    def _get_registered_provider(self, name: str):
        return self._extension_provider_controller.get_registered_provider(name)

    async def set_active_tools(self, tool_names: list[str]) -> None:
        await self._operations.set_active_tools(tool_names, emit_refresh=True)

    def register_runtime_tools(
        self,
        tools: Iterable[object],
        *,
        activate: bool = False,
        source_info: object | None = None,
    ) -> tuple[ToolDefinition, ...]:
        """Register live-bound tools without exposing composition internals."""

        definitions = tuple(
            self._tool_controller.register_runtime_tool(
                tool,
                source_info=source_info,
            )
            for tool in tools
        )
        if activate:
            active = self._tool_controller.get_active_tool_names()
            self._tool_controller.apply_active_tools(
                [
                    *active,
                    *(
                        definition.name
                        for definition in definitions
                        if definition.name not in active
                    ),
                ]
            )
        return definitions

    def _apply_agent_transcript_context(
        self, session_context: AgentTranscriptContext
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

    def _get_bash_definition(self):
        if self._tool_registry is None:
            raise RuntimeError("Bash execution requires a tool registry")
        try:
            return self._tool_registry.get_definition("bash")
        except KeyError as exc:
            raise RuntimeError("Bash tool is not registered") from exc

    def _create_bash_call_id(self) -> str:
        return (
            f"bash-{self.session_manager.get_session_record().session_id}-"
            f"{len(self.session_manager.get_entries())}"
        )

    def _set_agent_steering_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported steering mode: {mode}")
        self.agent.steering_mode = mode

    def _set_agent_follow_up_mode(self, mode: str) -> None:
        if mode not in {"all", "one-at-a-time"}:
            raise ValueError(f"Unsupported follow-up mode: {mode}")
        self.agent.follow_up_mode = mode

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
        self._approval_resolver.set_request_presenter(presenter, dismisser=dismisser)
        self._approval_resolver.open_session()

    def _bind_approval_presenter(
        self,
        presenter: ApprovalRequestPresenter,
        *,
        dismisser: ApprovalRequestDismisser | None = None,
    ) -> ApprovalPresentationLease:
        if self._approval_resolver is None or self._approval_session_state != "active":
            raise RuntimeError("Session approval interaction is not active")
        previous = self._approval_presenter_lease
        if previous is not None:
            previous.supersede()
        self._approval_presenter_generation += 1
        generation = self._approval_presenter_generation
        self._approval_resolver.set_request_presenter(
            presenter,
            dismisser=dismisser,
        )
        self._approval_resolver.open_session()
        self._approval_resolver.represent_pending_requests()
        lease = _AgentApprovalPresentationLease(
            lambda reason: self._close_approval_presenter_generation(
                generation,
                reason,
            )
        )
        self._approval_presenter_lease = lease
        return lease

    def _close_approval_presenter_generation(
        self,
        generation: int,
        reason: str,
    ) -> None:
        if generation != self._approval_presenter_generation:
            return
        self._approval_presenter_lease = None
        self._unbind_approval_presenter_host(reason=reason)

    async def handle_screen_approval(self, event: Mapping[str, object]) -> bool:
        if self._approval_resolver is None:
            return False
        action_id = event.get("action_id")
        if not isinstance(action_id, str):
            return False
        reason = event.get("reason")
        if reason is not None and not isinstance(reason, str):
            reason = None
        outcome = event.get("outcome")
        if outcome not in {
            "allow_once",
            "allow_session",
            "allow_project",
            "allow_user",
            "deny",
            "abort",
        }:
            scope = event.get("scope", "once")
            if scope not in {"once", "session"}:
                return False
            outcome = (
                "allow_session"
                if bool(event.get("approved")) and scope == "session"
                else "allow_once"
                if bool(event.get("approved"))
                else "deny"
            )
        accepted = await self._approval_resolver.handle_result(
            action_id=action_id,
            outcome=cast(ApprovalOutcome, outcome),
            reason=reason,
        )
        if accepted and outcome == "abort":
            self.abort()
        return accepted

    def get_approval_permissions(self) -> ApprovalPermissionsSnapshot:
        if self._approval_resolver is None:
            return ApprovalPermissionsSnapshot()
        return self._approval_resolver.permissions_snapshot()

    def get_permission_profile_snapshot(self) -> PermissionProfileSnapshot:
        getter = getattr(
            self._settings_controller,
            "get_permission_profile_snapshot",
            None,
        )
        if not callable(getter):
            return permission_profile_snapshot("standard")
        snapshot = getter()
        if not isinstance(snapshot, PermissionProfileSnapshot):
            raise TypeError(
                "settings permission profile getter must return "
                "PermissionProfileSnapshot"
            )
        return snapshot

    async def apply_approval_permission_action(self, action: str) -> bool:
        kind, separator, permission_id = action.partition(":")
        if not separator or not permission_id:
            return False
        if kind == "set-profile":
            scope, scope_separator, profile_id = permission_id.partition(":")
            if (
                not scope_separator
                or scope not in {"session", "project", "user"}
                or not profile_id
            ):
                return False
            setter = getattr(
                self._settings_controller,
                "set_permission_profile",
                None,
            )
            if not callable(setter):
                return False
            requested = permission_profile(profile_id).profile_id
            before = self.get_permission_profile_snapshot().effective_profile.profile_id
            setter(
                requested,
                scope=cast(PermissionProfileScope, scope),
            )
            after = self.get_permission_profile_snapshot()
            await self._dispatch_event(
                PermissionProfileChanged(
                    previous_profile_id=before,
                    requested_profile_id=requested,
                    effective_profile_id=after.effective_profile.profile_id,
                    scope=cast(PermissionProfileScope, scope),
                )
            )
            return True
        if self._approval_resolver is None:
            return False
        if kind == "reopen":
            return await self._approval_resolver.represent_request(permission_id)
        if kind == "revoke":
            return self._approval_resolver.revoke_grant(permission_id)
        if kind == "revoke-policy":
            return self._approval_resolver.revoke_policy_rule(permission_id)
        return False

    def _stage_session_approvals(self) -> None:
        self._approval_session_state = "staged"

    def _unbind_approval_presenter_host(
        self,
        reason: str = "Approval presenter closed before approval was resolved",
    ) -> None:
        if self._approval_resolver is None:
            return
        if self._approval_session_state == "active":
            self._approval_resolver.close_session(reason)
        self._approval_resolver.set_request_presenter(None)

    def _open_session_approvals(self) -> None:
        if self._approval_resolver is None:
            return
        self._approval_resolver.open_session()
        self._approval_session_state = "active"

    def _close_session_approvals(
        self, reason: str = "Session closed before approval was resolved"
    ) -> None:
        if self._approval_resolver is None or self._approval_session_state != "active":
            return
        self._approval_session_state = "closed"
        self._approval_resolver.end_session(reason)

    async def _before_bash(
        self, request: UserCommandRequest
    ) -> UserCommandHookResult | None:
        runner = self._extension_runner
        if runner is None or not runner.has_handlers("user_bash"):
            return None
        event_result = await runner.emit_user_bash(
            {
                "type": "user_bash",
                "command": request.command,
                "exclude_from_context": request.exclude_from_context,
                "cwd": request.cwd,
            },
            cwd=request.cwd,
        )
        self._sync_extension_diagnostics(phase="runtime")
        result = _bash_result_from_extension_result(event_result)
        if result is not None:
            return UserCommandHookResult(result=result)
        return UserCommandHookResult(
            operations=_bash_operations_from_extension_result(event_result)
        )

    def _execute_resource_command(self, invocation_name: str, args: str):
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

    def get_context_usage(self):
        return super().get_context_usage()

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

    async def _reload_from_extension(self) -> None:
        await self._operations.bind_extension_runtime(reason="reload")

    def _set_extension_ui_context(self, ui_context: object | None) -> None:
        self._extension_ui_context = ui_context
        self._operations.refresh_extension_runtime_bindings()

    def _set_extension_runtime_host(self, runtime_host: object | None) -> None:
        self._extension_runtime_host = runtime_host
        self._operations.refresh_extension_runtime_bindings()

    async def _set_model_internal(
        self, model: object, *, emit_refresh: bool, source: str = "set"
    ) -> None:
        await self._operations.set_model(
            model, emit_refresh=emit_refresh, source=source
        )

    def _apply_active_tools(self, tool_names: list[str]) -> None:
        self._operations.apply_active_tools(tool_names)

    async def _set_active_tools_internal(
        self, tool_names: list[str], *, emit_refresh: bool
    ) -> None:
        await self._operations.set_active_tools(tool_names, emit_refresh=emit_refresh)

    async def _compact_manual(
        self, custom_instructions: str | None = None
    ) -> CompactionResult:
        return await self._operations.compact_manual(custom_instructions)

    async def maybe_compact_after_turn(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._operations.maybe_compact_after_turn(assistant_message)

    def get_compaction_status(self) -> CompactionStatus:
        return self._operations.get_compaction_status()

    async def navigate_tree(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
        label: str | None = None,
    ) -> TranscriptNavigationResult:
        return await self._operations.navigate_tree(
            target_id,
            summarize=summarize,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
            label=label,
        )

    def abort_branch_summary(self) -> None:
        self._operations.abort_branch_summary()

    async def _apply_before_tree_hook(
        self,
        plan: TranscriptNavigationPlan,
        *,
        summarize: bool,
        custom_instructions: str | None,
        replace_instructions: bool,
        label: str | None,
    ) -> tuple[str | None, bool, str | None, BranchSummaryOutput | None, bool]:
        runner = self._extension_runner
        if runner is None:
            return custom_instructions, replace_instructions, label, None, False
        decision = await runner.before_session_tree(
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
            return custom_instructions, replace_instructions, label, None, True
        if decision is None:
            return custom_instructions, replace_instructions, label, None, False
        return (
            decision.custom_instructions
            if decision.custom_instructions is not None
            else custom_instructions,
            decision.replace_instructions
            if decision.replace_instructions is not None
            else replace_instructions,
            decision.label if decision.label is not None else label,
            (
                normalize_branch_summary_output(decision.summary, from_hook=True)
                if decision.summary is not None
                else None
            ),
            False,
        )

    async def dispose(
        self, session_shutdown_event: SessionShutdownEvent | None = None
    ) -> None:
        await self._operations.dispose(session_shutdown_event)

    async def _dispose_after_session_shutdown(self) -> None:
        await self._operations.dispose_after_session_shutdown()

    async def _dispose_session_runtime_profile(self) -> None:
        dispose = getattr(self.session_manager, "dispose_runtime_profile", None)
        if callable(dispose):
            result = dispose()
            if hasattr(result, "__await__"):
                await result

    async def _bind_extension_runtime(self, *, reason: str) -> None:
        await self._operations.bind_extension_runtime(reason=reason)

    def _bind_extension_runtime_bindings(self) -> None:
        self._operations.bind_extension_runtime_bindings()

    async def _refresh_extension_runtime(self, *, reason: str) -> None:
        await self._operations.refresh_extension_runtime(reason=reason)

    def _refresh_extension_runtime_bindings(self) -> None:
        self._operations.refresh_extension_runtime_bindings()

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

    def _before_agent_start_system_prompt_options(self) -> dict[str, object]:
        return {
            "cwd": self.session_manager.get_cwd(),
            "selected_tools": list(self.get_active_tool_names()),
            "skills": list(self.resource_bundle.skills)
            if self.resource_bundle is not None
            else [],
            "context_files": [],
        }

    def _set_resource_bundle(self, resource_bundle: object) -> None:
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
            for descriptor in (
                *bundle.prompts,
                *bundle.skills,
                *bundle.extensions,
                *bundle.themes,
            ):
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
        await self._operations.set_active_tools(
            tool_names,
            emit_refresh=not self._extension_runtime_controller.is_refreshing,
        )

    async def _set_model_from_extension(self, selection: object) -> None:
        await self._operations.set_model(
            selection,
            emit_refresh=not self._extension_runtime_controller.is_refreshing,
            source="extension",
        )

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

    async def _send_user_message_from_extension_async(
        self, content: object, options: object | None = None
    ) -> None:
        await self._extension_message_controller.send_user_message(content, options)

    async def _compact_from_extension(
        self, custom_instructions: str | None = None
    ) -> object | None:
        return await self.compact(custom_instructions)

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
            command=_normalize_exec_command(command, args),
            cwd=_resolve_exec_cwd(self.session_manager.get_cwd(), cwd),
            env=_normalize_exec_env(env),
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

    async def _handle_agent_event(self, event: object, signal: object) -> None:
        await self._session_runtime.handle_agent_event(event, signal)

    async def _emit_extension_agent_event(self, event: object) -> None:
        await self._extension_event_sink.emit_agent_event(event)

    def _bind_package_progress_events(self) -> None:
        if self._package_materializer is not None:
            self._package_materializer.set_progress_callback(
                self._emit_package_progress
            )

    def _emit_package_progress(self, progress: PackageProgressEvent) -> None:
        event = PackageProgressChanged(
            progress_type=progress.type,
            action=progress.action,
            source=progress.source,
            message=progress.message,
            target_path=str(progress.target_path)
            if progress.target_path is not None
            else None,
        )
        try:
            self._session_runtime.schedule_event_dispatch(event)
        except RuntimeError:
            self._session_runtime.dispatch_event_without_loop(event)

    async def _dispatch_event(
        self,
        event: object,
        *,
        source_record_id: str | None = None,
    ) -> None:
        await self._operations.dispatch_event(event, source_record_id=source_record_id)

    def _get_compaction_settings(self) -> object:
        return self._settings_controller.get_compaction_settings()

    def _get_retry_settings(self) -> object:
        return self._settings_controller.get_retry_settings()

    async def _check_auto_compaction(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._operations.check_auto_compaction(assistant_message)

    async def _compact_before_prompt(self) -> CompactionResult | None:
        return await self._operations.compact_before_prompt()

    async def _compact_internal(
        self,
        *,
        reason: CompactionReason,
        will_retry: bool,
        raise_on_error: bool,
        custom_instructions: str | None = None,
    ) -> CompactionResult | None:
        return await self._operations.compact_internal(
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
        return await self._operations.execute_selected_compaction(
            preparation, custom_instructions
        )

    def _preflight_user_input(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        return self._command_controller.preflight_user_input(
            user_input, allow_extension_commands=allow_extension_commands
        )

    async def _preflight_user_input_async(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        return await self._command_controller.preflight_user_input_async(
            user_input, allow_extension_commands=allow_extension_commands
        )

    def _extract_extension_command_invocation(
        self, user_input: str
    ) -> tuple[str, str] | None:
        return self._command_controller.extract_extension_command_invocation(user_input)

    def _raise_if_queued_extension_command(self, user_input: str) -> None:
        self._command_controller.raise_if_queued_extension_command(user_input)

    def _record_preflight_diagnostics(
        self, diagnostics: tuple[DiagnosticDraft, ...]
    ) -> None:
        self._command_controller.record_preflight_diagnostics(diagnostics)

    def _sync_extension_diagnostics(self, *, phase: str) -> None:
        self._diagnostics_bridge.sync_extension_diagnostics(phase=phase)

    def _record_runtime_exception(self, *, code: str, exc: Exception | str) -> None:
        self._diagnostics_bridge.record_runtime_exception(code=code, exc=exc)

    def _record_assistant_response_error(
        self, assistant_message: AssistantMessage
    ) -> None:
        self._diagnostics_bridge.record_assistant_response_error(assistant_message)

    def _record_tool_execution_error(self, event: AgentEvent) -> None:
        self._diagnostics_bridge.record_tool_execution_error(event)

    def _record_extension_runtime_diagnostic(self, diagnostic: DiagnosticDraft) -> None:
        self._diagnostics_bridge.record_extension_runtime_diagnostic(diagnostic)

    def _wire_extension_hooks(self) -> None:
        if self._extension_runner is not None:
            ExtensionAgentHookRuntime(
                agent=self.agent,
                extension_runtime=self._extension_runner,
                get_cwd=self.session_manager.get_cwd,
            ).install()

    def subscribe(
        self, listener: Callable[[AgentSessionEvent], Awaitable[None] | None]
    ):
        return super().subscribe(listener, project=project_session_runtime_event)


def initialize_composed_session(
    session: object,
    composition: SessionComposition,
    *,
    operations_ports: SessionOperationsPorts,
    settings: object,
    session_manager: object,
    active_tool_names: list[str] | None,
    show_empty_tool_prompt: bool,
    tool_registry: object | None,
    apply_context: Callable[[object], None],
    sync_footer: Callable[[], None],
) -> None:
    """Install an assembled composition on a Product Session adapter."""

    session._capability_runtime = composition.capability_runtime
    session._diagnostics_bridge = composition.diagnostics_bridge
    session._tool_controller = composition.tool_controller
    session._resource_refresh_runtime = composition.resource_refresh_runtime
    session._resource_watch_controller = composition.resource_watch_controller
    session._navigation_runtime = composition.navigation_runtime
    session._compaction_capability = composition.compaction_capability
    session._compaction_runtime = composition.compaction_runtime
    session._bash_runtime = composition.bash_runtime
    session._package_controller = composition.package_controller
    session._command_controller = composition.command_controller
    session._extension_event_sink = composition.extension_event_sink
    session._retry_runtime = composition.retry_runtime
    session._session_runtime = composition.session_runtime
    session._extension_input_runtime = composition.extension_input_runtime
    session._extension_message_controller = composition.extension_message_controller
    session._extension_provider_controller = composition.extension_provider_controller
    session._extension_replacement_controller = (
        composition.extension_replacement_controller
    )
    session._extension_runtime_binding_factory = (
        composition.extension_runtime_binding_factory
    )
    session._extension_runtime_controller = composition.extension_runtime_controller
    session._selection_runtime = composition.selection_runtime
    session._model_binding = composition.model_binding
    session._identity_binding = composition.identity_binding
    session._maintenance_binding = composition.maintenance_binding
    session._extension_binding = composition.extension_binding
    session._session_inspector = composition.session_inspector
    session._operations = SessionOperations(operations_ports)
    SessionFacade.__init__(
        session,
        runtime=composition.session_runtime,
        transcript=session_manager,
        tools=composition.tool_controller,
        commands=composition.command_controller,
        command_execution=composition.bash_runtime,
        view=composition.session_inspector,
        retry=composition.retry_runtime,
        identity=composition.identity_binding,
        maintenance=composition.maintenance_binding,
        resources=composition.resource_refresh_runtime,
        diagnostics=composition.diagnostics_bridge,
        packages=composition.package_controller,
        model_selection=composition.model_binding,
        extensions=composition.extension_binding,
        settings=settings,
        application_input=composition.extension_message_controller,
        approval_interaction=(
            _AgentSessionApprovalInteraction(cast(AgentSessionAdapterMixin, session))
            if getattr(session, "_approval_resolver", None) is not None
            else None
        ),
    )
    apply_context(session_manager.build_session_context())
    if tool_registry is not None:
        initial_names = (
            list(active_tool_names)
            if active_tool_names is not None
            else composition.tool_controller.default_active_tool_names()
        )
        session._apply_active_tools(initial_names)
    elif show_empty_tool_prompt:
        session._rebuild_prompt_and_tools_view()
    if session._extension_runner is not None:
        session._wire_extension_hooks()
        session._bind_extension_runtime_bindings()
    sync_footer()


def build_agent_session_lifecycle_hooks(
    *,
    runtime_host: object,
    record_shutdown_failure: Callable[[object, SessionShutdownEvent, Exception], None],
) -> SessionLifecycleHooks[object, str]:
    """Bind standard Agent-session effects to the shared lifecycle runtime."""

    async def before_transition(
        current: object | None,
        transition: SessionLifecycleTransition,
    ) -> SessionLifecycleDecision | None:
        if (
            current is None
            or transition.metadata.get("emit_before_transition", True) is False
        ):
            return None
        runner = _session_extension_runner(current)
        if runner is None:
            return None
        manager = getattr(current, "session_manager")
        if transition.reason == "fork":
            entry_id = transition.fork_entry_id
            position = transition.fork_position
            if entry_id is None or position is None:
                raise ValueError("Fork transitions require entry_id and position")
            decision = await runner.before_session_fork(
                SessionBeforeForkEvent(
                    entry_id=entry_id,
                    cwd=manager.get_cwd(),
                    position=position,
                )
            )
        else:
            decision = await runner.before_session_switch(
                SessionBeforeSwitchEvent(
                    reason=transition.reason,
                    cwd=transition.cwd or manager.get_cwd(),
                    target_session_file=transition.target_session_ref,
                )
            )
        _sync_session_extension_diagnostics(current)
        return SessionLifecycleDecision(
            cancelled=decision is not None and decision.cancel
        )

    def prepare_session(
        session: object,
        _previous: object | None,
        _transition: SessionLifecycleTransition,
    ) -> None:
        stage_approvals = getattr(session, "_stage_session_approvals", None)
        if callable(stage_approvals):
            stage_approvals()
        _bind_session_runtime_host(session, runtime_host)

    async def activate_session(
        session: object,
        previous: object | None,
        transition: SessionLifecycleTransition,
    ) -> None:
        _open_session_approvals(session)
        if transition.metadata.get("activate_extensions", True) is False:
            return
        starter = getattr(session, "start_extension_runtime", None)
        if callable(starter):
            reason = (
                "startup"
                if previous is None and transition.reason == "new"
                else transition.reason
            )
            await starter(reason=reason)

    async def before_release(
        session: object,
        target_session: object | None,
        transition: SessionLifecycleTransition,
    ) -> None:
        event = SessionShutdownEvent(
            reason=transition.reason,
            target_session_file=session_file_from_session(target_session),
        )
        try:
            await emit_session_shutdown(session, event)
        except Exception as exc:
            record_shutdown_failure(session, event, exc)
        finally:
            _sync_session_extension_diagnostics(session)

    return SessionLifecycleHooks(
        before_transition=before_transition,
        prepare_session=prepare_session,
        activate_session=activate_session,
        before_release=before_release,
        dispose_session=dispose_session_only,
    )


def build_agent_product_session_runtime_ports(
    *,
    runtime_host: object,
    transcript_session_type: type[TranscriptT],
    session_dir: Path,
    session_factory: Callable[..., SessionT],
    persist: bool,
    diagnostics_runtime: Callable[[SessionT | None], SessionDiagnosticsRuntime] | None,
    record_shutdown_failure: Callable[[object, SessionShutdownEvent, Exception], None],
    copy_file: Callable[[Path, Path], None],
    before_release: Callable[
        [SessionT, SessionT | None, SessionLifecycleTransition],
        Awaitable[None] | None,
    ]
    | None = None,
    translate_missing_cwd_error: Callable[[MissingSessionCwdError], Exception]
    | None = None,
) -> ProductSessionRuntimePorts[SessionT, TranscriptT, str]:
    """Bind standard Agent session conventions to ``ProductSessionRuntime``."""

    transcript = ProductTranscriptSessionBinding(
        session_type=transcript_session_type,
        session_dir=session_dir,
        persist=persist,
        resolve_cwd_override=resolve_existing_cwd,
    )

    def build_session(
        manager: TranscriptT,
        current: SessionT | None,
        transition: SessionLifecycleTransition,
    ) -> SessionT:
        reason = (
            "startup"
            if current is None and transition.reason == "new"
            else transition.reason
        )
        return invoke_session_factory(
            session_factory,
            manager,
            session_start_event=SessionStartEvent(
                reason=reason,
                previous_session_file=session_file_from_session(current),
            ),
        )

    def fork_target(
        session: SessionT,
        entry_id: str,
        position: str,
    ) -> ForkSelection[str]:
        return resolve_agent_transcript_fork_target(
            getattr(session, "session_manager"),
            entry_id,
            position,
        )

    hooks = cast(
        SessionLifecycleHooks[SessionT, str],
        build_agent_session_lifecycle_hooks(
            runtime_host=runtime_host,
            record_shutdown_failure=record_shutdown_failure,
        ),
    )
    if before_release is not None:
        existing_before_release = hooks.before_release

        async def composed_before_release(
            session: SessionT,
            target_session: SessionT | None,
            transition: SessionLifecycleTransition,
        ) -> None:
            result = before_release(session, target_session, transition)
            if result is not None:
                await result
            if existing_before_release is not None:
                result = existing_before_release(
                    session,
                    target_session,
                    transition,
                )
                if result is not None:
                    await result

        hooks = replace(hooks, before_release=composed_before_release)

    return ProductSessionRuntimePorts(
        session_factory=session_factory,
        persist=persist,
        create_transcript=transcript.create,
        restore_transcript=transcript.restore,
        fork_transcript=transcript.fork,
        dispose_transcript=transcript.dispose,
        transcript_for_session=lambda session: cast(
            TranscriptT, getattr(session, "session_manager")
        ),
        transcript_cwd=lambda manager: getattr(manager, "get_cwd")(),
        transcript_session_ref=lambda manager: (
            str(value)
            if (value := getattr(manager, "get_session_file")()) is not None
            else None
        ),
        transcript_leaf_entry_id=lambda manager: getattr(manager, "get_leaf_id")(),
        build_session=build_session,
        validate_restored_transcript=transcript.validate_available_cwd,
        fork_profile=ForkProfile(
            default_position="before",
            supported_positions=frozenset({"at", "before"}),
        ),
        fork_target_resolver=fork_target,
        copy_file=copy_file,
        hooks=hooks,
        diagnostics_runtime=diagnostics_runtime,
        rename_transcript=transcript.rename,
        delete_transcript=transcript.delete,
        current_session_file=session_file_from_session,
        resolve_import_cwd=resolve_existing_cwd,
        translate_missing_cwd_error=translate_missing_cwd_error,
    )


class AgentProductSessionRuntime(
    ProductSessionRuntime[SessionT, TranscriptT, str],
    Generic[SessionT, TranscriptT],
):
    """Standard Agent conventions bound to the shared Product session runtime."""

    def __init__(
        self,
        *,
        transcript_session_type: type[TranscriptT],
        session_dir: Path,
        session_factory: Callable[..., SessionT],
        persist: bool = True,
        current_session: SessionT | None = None,
        diagnostics_service: DiagnosticsService | None = None,
        copy_file: Callable[[Path, Path], None] = copy_file_exclusive,
        before_release: Callable[
            [SessionT, SessionT | None, SessionLifecycleTransition],
            Awaitable[None] | None,
        ]
        | None = None,
        auto_refresh_session_index: bool = False,
        session_index_refresh_interval: float = 0.5,
        session_index_flush_delay: float = 0.25,
    ) -> None:
        self._agent_diagnostics_service = diagnostics_service
        super().__init__(
            session_dir=session_dir,
            ports=build_agent_product_session_runtime_ports(
                runtime_host=self,
                transcript_session_type=transcript_session_type,
                session_dir=session_dir,
                session_factory=session_factory,
                persist=persist,
                copy_file=copy_file,
                diagnostics_runtime=self._agent_session_diagnostics_runtime,
                record_shutdown_failure=self._record_agent_shutdown_failure,
                before_release=before_release,
            ),
            current_session=current_session,
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
        )
        if current_session is not None:
            prepare_current_agent_session(current_session, self)

    def _agent_session_diagnostics_runtime(
        self,
        session: SessionT | None = None,
    ) -> SessionDiagnosticsRuntime:
        active_session = session or self.current_session
        diagnostics_service = self._agent_diagnostics_service or getattr(
            active_session,
            "diagnostics_service",
            None,
        )
        session_id = session_id_from_session(active_session) or ""
        return SessionDiagnosticsRuntime(
            diagnostics_service=diagnostics_service,
            get_scope=lambda: SessionDiagnosticScope(session_id=session_id),
            get_extension_diagnostics=lambda: None,
        )

    def _record_agent_shutdown_failure(
        self,
        session: object,
        event: SessionShutdownEvent,
        exc: Exception,
    ) -> None:
        typed_session = cast(SessionT, session)
        self._record_failure_for_session(
            typed_session,
            code="session_shutdown_failed",
            exc=exc,
            details={
                "reason": event.reason,
                "session_file": session_file_from_session(typed_session),
                "target_session_file": event.target_session_file,
            },
        )


def prepare_current_agent_session(session: object, runtime_host: object) -> None:
    """Activate approval and runtime-host bindings for an injected session."""

    _open_session_approvals(session)
    _bind_session_runtime_host(session, runtime_host)


def _bind_session_runtime_host(session: object, runtime_host: object) -> None:
    setter = getattr(session, "set_extension_runtime_host", None)
    if callable(setter):
        setter(runtime_host)


def _open_session_approvals(session: object) -> None:
    callback = getattr(session, "_open_session_approvals", None)
    if callable(callback):
        callback()


def _session_extension_runner(session: object) -> object | None:
    return getattr(
        session,
        "extension_runner",
        getattr(session, "_extension_runner", None),
    )


def _sync_session_extension_diagnostics(
    session: object,
    *,
    phase: DiagnosticPhase = "runtime",
) -> None:
    sync = getattr(session, "_sync_extension_diagnostics", None)
    if callable(sync):
        sync(phase=phase)
        return
    diagnostics_service = getattr(session, "diagnostics_service", None)
    runner = _session_extension_runner(session)
    get_diagnostics = (
        getattr(runner, "get_diagnostics", None) if runner is not None else None
    )
    if diagnostics_service is None or not callable(get_diagnostics):
        return
    diagnostics = get_diagnostics()
    recorded_attr = "_runtime_synced_extension_diagnostics_count"
    recorded = getattr(session, recorded_attr, 0)
    if not isinstance(recorded, int) or recorded < 0:
        recorded = 0
    if recorded >= len(diagnostics):
        return
    diagnostics_service.record_many(
        diagnostics_service.normalize_diagnostic(
            diagnostic,
            phase=phase,
            source="extensions",
            session_id=session_id_from_session(session),
        )
        for diagnostic in diagnostics[recorded:]
    )
    try:
        setattr(session, recorded_attr, len(diagnostics))
    except Exception:
        return


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_exec_command(command: str, args: Sequence[str]) -> tuple[str, ...]:
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


def _normalize_exec_env(
    env: Mapping[str, str] | Sequence[tuple[str, str]] | None,
) -> tuple[tuple[str, str], ...]:
    if env is None:
        return ()
    if isinstance(env, Mapping):
        return tuple(env.items())
    return tuple(env)


def _resolve_exec_cwd(session_cwd: str, cwd: str | Path | None) -> str:
    base = Path(session_cwd)
    if cwd is None:
        return str(base)
    path = Path(cwd)
    return str(path if path.is_absolute() else base / path)


def _bash_result_from_extension_result(
    event_result: object | None,
) -> dict[str, object] | None:
    if event_result is None:
        return None
    result = (
        event_result.get("result")
        if isinstance(event_result, dict)
        else getattr(event_result, "result", None)
    )
    if not isinstance(result, dict):
        return None
    return normalize_bash_result_from_protocol(result)


def _bash_operations_from_extension_result(
    event_result: object | None,
) -> object | None:
    if event_result is None:
        return None
    if isinstance(event_result, dict):
        return event_result.get("operations")
    return getattr(event_result, "operations", None)


__all__ = [
    "AgentSessionAdapterMixin",
    "build_agent_product_session_runtime_ports",
    "build_agent_session_lifecycle_hooks",
    "prepare_current_agent_session",
]

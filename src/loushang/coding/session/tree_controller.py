from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loushang.agent import AbortController, Agent
from loushang.ai.types import TextPart, UserMessage
from loushang.coding.compaction import (
    BranchSummaryDetails,
    BranchSummaryResult,
    collect_entries_for_branch_summary,
    generate_branch_summary,
)
from loushang.coding.extensions import ExtensionRunner, SessionBeforeTreeEvent
from loushang.coding.session.types import TreeNavigationResult
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    AgentTranscriptContext,
    ApplicationMessage,
)
from loushang.harness.events import (
    BranchSummaryCompleted,
    BranchSummaryStarted,
    SessionRuntimeEventPayload,
)
from loushang.harness.runtime import (
    NavigationFailure,
    NavigationTransactionCoordinator,
)
from loushang.protocol import JSONValue, require_json_value

EventDispatcher = Callable[[SessionRuntimeEventPayload], Awaitable[None]]
RuntimeExceptionRecorder = Callable[..., None]
ExtensionDiagnosticsSync = Callable[..., None]
BranchSummaryGenerator = Callable[..., Awaitable[BranchSummaryResult]]
SessionContextApplier = Callable[[AgentTranscriptContext], None]


def _noop_record_runtime_exception(*, code: str, exc: Exception | str) -> None:
    del code, exc


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass(frozen=True)
class _SummaryNavigationPlan:
    target_id: str
    old_leaf_id: str | None
    new_leaf_id: str | None
    editor_text: str | None
    custom_instructions: str | None
    replace_instructions: bool
    label: str | None
    hook_summary: BranchSummaryResult | None
    generate: BranchSummaryGenerator


@dataclass
class TreeController:
    agent: Agent
    session_manager: SessionManager
    dispatch_event: EventDispatcher
    apply_session_context: SessionContextApplier | None = None
    extension_runner: ExtensionRunner | None = None
    record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception
    sync_extension_diagnostics: ExtensionDiagnosticsSync = (
        _noop_sync_extension_diagnostics
    )

    _summary_navigation: NavigationTransactionCoordinator[AbortController] = field(
        default_factory=lambda: NavigationTransactionCoordinator(
            create_abort_scope=AbortController,
            abort=lambda controller: controller.abort(),
        ),
        init=False,
    )
    _branch_summary_abort_controller: AbortController | None = None

    @property
    def is_branch_summarizing(self) -> bool:
        return (
            self._summary_navigation.is_active
            or self._branch_summary_abort_controller is not None
        )

    async def navigate_tree(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
        label: str | None = None,
        generate_branch_summary_fn: BranchSummaryGenerator | None = None,
    ) -> TreeNavigationResult:
        old_leaf_id = self.session_manager.get_leaf_id()
        if target_id == old_leaf_id:
            return TreeNavigationResult(cancelled=False)

        target_entry = self.session_manager.get_entry(target_id)
        if target_entry is None:
            raise ValueError(f"Entry {target_id} not found")

        editor_text: str | None = None
        if target_entry.kind == AGENT_MESSAGE_KIND and isinstance(
            target_entry.payload, UserMessage
        ):
            new_leaf_id = target_entry.parent_id
            editor_text = _extract_user_message_text(target_entry.payload)
        elif target_entry.kind == APPLICATION_MESSAGE_KIND and isinstance(
            target_entry.payload, ApplicationMessage
        ):
            new_leaf_id = target_entry.parent_id
            editor_text = _extract_custom_message_text(target_entry.payload)
        else:
            new_leaf_id = target_id

        summary_result = None
        if self.extension_runner is not None:
            decision = await self.extension_runner.before_session_tree(
                SessionBeforeTreeEvent(
                    target_id=target_id,
                    old_leaf_id=old_leaf_id,
                    new_leaf_id=new_leaf_id,
                    cwd=str(self.session_manager.get_cwd()),
                    summarize=summarize,
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                    label=label,
                )
            )
            if decision is not None and decision.cancel:
                self.sync_extension_diagnostics(phase="runtime")
                return TreeNavigationResult(cancelled=True)
            if decision is not None and decision.summary is not None:
                summary_result = decision.summary
            else:
                summary_result = None
            if decision is not None and decision.custom_instructions is not None:
                custom_instructions = decision.custom_instructions
            if decision is not None and decision.replace_instructions is not None:
                replace_instructions = decision.replace_instructions
            if decision is not None and decision.label is not None:
                label = decision.label

        if not summarize:
            self._apply_navigation_leaf(new_leaf_id)
            self._rebuild_agent_context()
            if self.extension_runner is not None:
                await self.extension_runner.emit_event(
                    {
                        "type": "session_tree",
                        "new_leaf_id": new_leaf_id,
                        "old_leaf_id": old_leaf_id,
                        "summary_entry": None,
                        "from_extension": False,
                    },
                    cwd=self.session_manager.get_cwd(),
                )
            return TreeNavigationResult(
                cancelled=False,
                editor_text=editor_text,
            )

        plan = _SummaryNavigationPlan(
            target_id=target_id,
            old_leaf_id=old_leaf_id,
            new_leaf_id=new_leaf_id,
            editor_text=editor_text,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
            label=label,
            hook_summary=summary_result,
            generate=generate_branch_summary_fn or generate_branch_summary,
        )
        return await self._summary_navigation.run(
            plan,
            before_commit=self._start_summary_navigation,
            commit=self._commit_summary_navigation,
            after_commit=self._finish_summary_navigation,
            on_failure=self._fail_summary_navigation,
        )

    def abort_branch_summary(self) -> None:
        self._summary_navigation.abort()
        if self._branch_summary_abort_controller is not None:
            self._branch_summary_abort_controller.abort()

    async def _start_summary_navigation(self, plan: _SummaryNavigationPlan) -> None:
        await self.dispatch_event(
            BranchSummaryStarted(
                target_id=plan.target_id,
                old_leaf_id=plan.old_leaf_id,
                summarize=True,
            )
        )

    async def _commit_summary_navigation(
        self,
        plan: _SummaryNavigationPlan,
        abort_controller: AbortController,
    ) -> TreeNavigationResult:
        summary_result = plan.hook_summary
        summary_entry_id: str | None = None
        if summary_result is not None:
            summary_entry_id = await self._append_branch_summary(
                plan,
                summary_result,
                from_hook=True,
            )

        entries = collect_entries_for_branch_summary(
            self.session_manager,
            plan.old_leaf_id,
            plan.target_id,
        ).entries
        if entries and summary_result is None:
            summary_result = await plan.generate(
                entries,
                model=self.agent.model,
                signal=abort_controller.signal,
                custom_instructions=plan.custom_instructions,
                replace_instructions=plan.replace_instructions,
            )
            if summary_result.aborted:
                return TreeNavigationResult(cancelled=True, aborted=True)
            if summary_result.error:
                raise RuntimeError(summary_result.error)
            if summary_result.summary:
                summary_entry_id = await self._append_branch_summary(
                    plan,
                    summary_result,
                    from_hook=False,
                )

        if summary_entry_id is None:
            self._apply_navigation_leaf(plan.new_leaf_id)
            if plan.label:
                await self.session_manager.append_label(plan.target_id, plan.label)
        self._rebuild_agent_context()
        return TreeNavigationResult(
            cancelled=False,
            editor_text=plan.editor_text,
            summary_entry_id=summary_entry_id,
        )

    async def _append_branch_summary(
        self,
        plan: _SummaryNavigationPlan,
        summary: BranchSummaryResult,
        *,
        from_hook: bool,
    ) -> str:
        if summary.summary is None:
            raise RuntimeError("Branch summary did not include summary text")
        entry_id = await self.session_manager.branch_with_summary(
            plan.new_leaf_id,
            summary.summary,
            details=_project_branch_summary_details(summary.details),
            from_hook=from_hook,
        )
        if plan.label:
            await self.session_manager.append_label(entry_id, plan.label)
        return entry_id

    async def _finish_summary_navigation(
        self,
        plan: _SummaryNavigationPlan,
        result: TreeNavigationResult,
    ) -> None:
        await self.dispatch_event(
            BranchSummaryCompleted(
                target_id=plan.target_id,
                old_leaf_id=plan.old_leaf_id,
                new_leaf_id=(
                    plan.old_leaf_id
                    if result.aborted
                    else self.session_manager.get_leaf_id()
                ),
                summary_record_id=result.summary_entry_id,
                cancelled=result.cancelled,
                aborted=result.aborted,
            )
        )

    async def _fail_summary_navigation(
        self,
        failure: NavigationFailure[_SummaryNavigationPlan],
    ) -> None:
        self.record_runtime_exception(code="branch_summary_failed", exc=failure.error)
        await self.dispatch_event(
            BranchSummaryCompleted(
                target_id=failure.plan.target_id,
                old_leaf_id=failure.plan.old_leaf_id,
                new_leaf_id=failure.plan.old_leaf_id,
                summary_record_id=None,
                cancelled=False,
                aborted=False,
                error_message=str(failure.error),
            )
        )

    def _apply_navigation_leaf(self, new_leaf_id: str | None) -> None:
        if new_leaf_id is None:
            self.session_manager.reset_leaf()
        else:
            self.session_manager.branch(new_leaf_id)

    def _rebuild_agent_context(self) -> None:
        session_context = self.session_manager.build_session_context()
        if self.apply_session_context is not None:
            self.apply_session_context(session_context)
            return
        self.agent.state.set_messages(session_context.messages)


def _extract_user_message_text(message: UserMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block.text for block in message.content if isinstance(block, TextPart)
    )


def _extract_custom_message_text(message: ApplicationMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block.text for block in message.content if isinstance(block, TextPart)
    )


def _project_branch_summary_details(details: object | None) -> JSONValue:
    if isinstance(details, BranchSummaryDetails):
        return {
            "readFiles": list(details.read_files),
            "modifiedFiles": list(details.modified_files),
        }
    return require_json_value(details, name="branch_summary.details")

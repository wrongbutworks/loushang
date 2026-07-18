from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from loushang.agent import Agent
from loushang.coding.compaction import (
    BranchSummaryDetails,
    BranchSummaryResult,
    generate_branch_summary,
)
from loushang.coding.extensions import ExtensionRunner, SessionBeforeTreeEvent
from loushang.coding.session.types import TreeNavigationResult
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    AgentTranscriptContext,
    AgentTranscriptNavigationRuntime,
    BranchSummaryOutput,
    TranscriptNavigationPlan,
)
from loushang.harness.events import SessionRuntimeEventPayload
from loushang.harness.runtime import CancellationSignal
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


@dataclass
class TreeController:
    """Coding extension/summary adapter over Harness branch navigation."""

    agent: Agent
    session_manager: SessionManager
    dispatch_event: EventDispatcher
    apply_session_context: SessionContextApplier | None = None
    extension_runner: ExtensionRunner | None = None
    record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception
    sync_extension_diagnostics: ExtensionDiagnosticsSync = (
        _noop_sync_extension_diagnostics
    )
    _branch_summary_abort_controller: object | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _runtime: AgentTranscriptNavigationRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = AgentTranscriptNavigationRuntime(
            session=self.session_manager,
            apply_context=self._rebuild_agent_context,
            dispatch_event=self.dispatch_event,
            on_failure=self._record_navigation_failure,
        )

    @property
    def is_branch_summarizing(self) -> bool:
        return (
            self._runtime.is_summarizing
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
        plan = self._runtime.prepare(target_id)
        if plan is None:
            return TreeNavigationResult(cancelled=False)

        summary_override: BranchSummaryOutput | None = None
        if self.extension_runner is not None:
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
                return TreeNavigationResult(cancelled=True)

        result = await self._runtime.navigate(
            plan,
            summarize=summarize,
            label=label,
            summary_override=summary_override,
            summary_runner=(
                self._summary_runner(
                    generate_branch_summary_fn or generate_branch_summary,
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                )
                if summarize
                else None
            ),
        )
        if not summarize and self.extension_runner is not None:
            await self.extension_runner.emit_event(
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
        self._runtime.abort()
        controller = self._branch_summary_abort_controller
        abort = getattr(controller, "abort", None)
        if callable(abort):
            abort()

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
        assert self.extension_runner is not None
        decision = await self.extension_runner.before_session_tree(
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
            self.sync_extension_diagnostics(phase="runtime")
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
                _branch_summary_output(decision.summary, from_hook=True)
                if decision.summary is not None
                else None
            ),
            False,
        )

    def _summary_runner(
        self,
        generate: BranchSummaryGenerator,
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
            result = await generate(
                entries,
                model=self.agent.model,
                signal=signal,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )
            return _branch_summary_output(result, from_hook=False)

        return run

    async def _record_navigation_failure(self, error: Exception) -> None:
        self.record_runtime_exception(code="branch_summary_failed", exc=error)

    def _rebuild_agent_context(self) -> None:
        session_context = self.session_manager.build_session_context()
        if self.apply_session_context is not None:
            self.apply_session_context(session_context)
            return
        self.agent.state.set_messages(list(session_context.messages))


def _branch_summary_output(
    result: BranchSummaryResult,
    *,
    from_hook: bool,
) -> BranchSummaryOutput:
    return BranchSummaryOutput(
        summary=result.summary,
        details=_project_branch_summary_details(result.details),
        from_hook=from_hook,
        aborted=result.aborted,
        error=result.error,
    )


def _project_branch_summary_details(details: object | None) -> JSONValue:
    if isinstance(details, BranchSummaryDetails):
        return {
            "readFiles": list(details.read_files),
            "modifiedFiles": list(details.modified_files),
        }
    return require_json_value(details, name="branch_summary.details")

"""Shared operations over an assembled Product session.

The operation object owns coordination, not Product policy.  Product code
supplies the branch-summary executor, hook decisions, and shutdown cleanup;
the common runtime owns ordering, cancellation, and resource/lifecycle
coordination.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from loushang.agent import Agent
from loushang.ai.types import AssistantMessage
from loushang.ai.utils import is_context_overflow
from loushang.harness.events import CompactionReason
from loushang.harness.extensions.context import (
    SessionShutdownEvent,
)
from loushang.harness.runtime import CancellationSignal
from loushang.harness.session.composition import (
    SessionComposition,
)
from loushang.harness.transcript import (
    BranchSummaryOutput,
    CompactionHookDecision,
    CompactionHookRequest,
    CompactionPreparation,
    CompactionResult,
    CompactionStatus,
    TranscriptNavigationPlan,
    TranscriptNavigationResult,
    normalize_branch_summary_output,
)


@dataclass(frozen=True)
class SessionOperationsPorts:
    """Product callbacks consumed by the shared operation coordinator."""

    composition: SessionComposition
    agent: Agent
    session_manager: object
    extension_runner: object | None
    execute_compaction: Callable[..., Awaitable[object]]
    execute_branch_summary: Callable[..., Awaitable[BranchSummaryOutput]]
    before_tree: Callable[..., Awaitable[object | None]]
    before_compaction: Callable[
        [CompactionHookRequest], Awaitable[CompactionHookDecision | None]
    ]
    after_compaction: Callable[[CompactionResult, str, bool], Awaitable[None]]
    dispose_runtime_profile: Callable[[], object | None]
    finalize_shutdown: Callable[[], None]
    invalidate_extension_contexts: Callable[[str], None]
    sync_extension_diagnostics: Callable[..., None]
    close_approvals: Callable[[], None]
    continue_run: Callable[[], Awaitable[None]]


class SessionOperations:
    """Coordinate standard session operations for any Product adapter."""

    def __init__(self, ports: SessionOperationsPorts) -> None:
        self.ports = ports
        self.composition = ports.composition

    async def dispatch_event(self, event: object, *, source_record_id: str | None = None) -> None:
        await self.composition.session_runtime.dispatch_event(
            event,
            source_record_id=source_record_id,
        )

    async def bind_extension_runtime(self, *, reason: str) -> None:
        await self.composition.extension_runtime_controller.bind(reason=reason)

    def bind_extension_runtime_bindings(self) -> None:
        self.composition.extension_runtime_controller.bind_bindings()

    async def refresh_extension_runtime(self, *, reason: str) -> None:
        await self.composition.extension_runtime_controller.refresh(reason=reason)

    def refresh_extension_runtime_bindings(self) -> None:
        self.composition.extension_runtime_controller.refresh_bindings()

    async def set_active_tools(self, tool_names: list[str], *, emit_refresh: bool) -> None:
        self.composition.tool_controller.apply_active_tools(tool_names)
        if emit_refresh:
            await self.refresh_extension_runtime(reason="active_tools_changed")

    def apply_active_tools(self, tool_names: list[str]) -> None:
        self.composition.tool_controller.apply_active_tools(tool_names)

    async def set_model(
        self,
        model: object,
        *,
        emit_refresh: bool,
        source: str = "set",
    ) -> None:
        resolved = self.composition.selection_runtime.resolve_model(model)
        previous = self.ports.agent.model
        endpoint_id = getattr(model, "endpoint_id", None) if _is_model_selection(model) else None
        await self.composition.selection_runtime.apply_model(
            resolved,
            endpoint_id=endpoint_id,
        )
        if emit_refresh:
            await self.refresh_extension_runtime(reason="model_selection_changed")
        if self.ports.extension_runner is not None and previous != resolved:
            emit_event = getattr(self.ports.extension_runner, "emit_event", None)
            if callable(emit_event):
                await emit_event(
                    {
                        "type": "model_select",
                        "model": resolved,
                        "previous_model": previous,
                        "source": source,
                    },
                    cwd=self.ports.session_manager.get_cwd(),
                )

    async def compact_manual(self, custom_instructions: str | None = None) -> CompactionResult:
        self.composition.session_runtime.abort()
        await self.composition.session_runtime.wait_for_idle()
        result = await self.composition.compaction_runtime.compact(
            reason="manual",
            will_retry=False,
            raise_on_error=True,
            custom_instructions=custom_instructions,
        )
        assert result is not None
        return result

    async def maybe_compact_after_turn(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._check_auto_compaction(assistant_message)

    def get_compaction_status(self) -> CompactionStatus:
        return CompactionStatus(
            is_compacting=self.composition.compaction_runtime.is_compacting,
            is_branch_summarizing=self.composition.navigation_runtime.is_summarizing,
        )

    async def navigate_tree(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
        label: str | None = None,
    ) -> TranscriptNavigationResult:
        navigation = self.composition.navigation_runtime
        plan = navigation.prepare(target_id)
        if plan is None:
            return TranscriptNavigationResult(cancelled=False)
        summary_override: BranchSummaryOutput | None = None
        if self.ports.extension_runner is not None:
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
        result = await navigation.navigate(
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
        if not summarize and self.ports.extension_runner is not None:
            await self.ports.extension_runner.emit_event(
                {
                    "type": "session_tree",
                    "new_leaf_id": self.ports.session_manager.get_leaf_id(),
                    "old_leaf_id": plan.old_leaf_id,
                    "summary_entry": None,
                    "from_extension": False,
                },
                cwd=self.ports.session_manager.get_cwd(),
            )
        return result

    def abort_branch_summary(self) -> None:
        self.composition.navigation_runtime.abort()

    async def dispose(self, session_shutdown_event: SessionShutdownEvent | None = None) -> None:
        try:
            await self.composition.resource_watch_controller.stop()
            if self.ports.extension_runner is not None:
                await self.ports.extension_runner.emit_session_shutdown(
                    session_shutdown_event or SessionShutdownEvent(reason="quit")
                )
        finally:
            self.ports.close_approvals()
            await self._dispose_runtime()

    async def dispose_after_session_shutdown(self) -> None:
        self.ports.close_approvals()
        await self._dispose_runtime()

    async def _dispose_runtime(self) -> None:
        try:
            await self.composition.session_runtime.dispose()
        finally:
            try:
                result = self.ports.dispose_runtime_profile()
                if asyncio.iscoroutine(result):
                    await result
            finally:
                self.composition.capability_runtime.dispose()
                self.ports.finalize_shutdown()

    async def check_auto_compaction(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self._check_auto_compaction(assistant_message)

    async def compact_before_prompt(self) -> CompactionResult | None:
        assistant_message = self._last_assistant_message()
        if assistant_message is None:
            return None
        return await self._check_auto_compaction(assistant_message)

    async def compact_internal(
        self,
        *,
        reason: CompactionReason,
        will_retry: bool,
        raise_on_error: bool,
        custom_instructions: str | None = None,
    ) -> CompactionResult | None:
        return await self.composition.compaction_runtime.compact(
            reason=reason,
            will_retry=will_retry,
            raise_on_error=raise_on_error,
            custom_instructions=custom_instructions,
        )

    async def execute_selected_compaction(
        self,
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> CompactionResult:
        result = await self._execute_compaction_with(
            preparation,
            custom_instructions,
        )
        assert isinstance(result, CompactionResult)
        return result

    async def _execute_compaction_with(
        self,
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> object:
        kwargs: dict[str, object] = {
            "preparation": preparation,
            "model": self.ports.agent.model,
            "headers": None,
            "signal": self.ports.agent.signal,
        }
        if custom_instructions is not None:
            kwargs["custom_instructions"] = custom_instructions
        return await self.ports.execute_compaction(**kwargs)

    async def _check_auto_compaction(
        self, assistant_message: AssistantMessage
    ) -> CompactionResult | None:
        return await self.composition.compaction_runtime.maybe_compact_after_turn(
            assistant_message,
            compact_internal_fn=self.compact_internal,
            continue_run_fn=self.ports.continue_run,
            is_context_overflow_fn=is_context_overflow,
        )

    async def _apply_before_tree_hook(
        self,
        plan: TranscriptNavigationPlan,
        *,
        summarize: bool,
        custom_instructions: str | None,
        replace_instructions: bool,
        label: str | None,
    ) -> tuple[str | None, bool, str | None, BranchSummaryOutput | None, bool]:
        decision = await self.ports.before_tree(
            plan,
            summarize=summarize,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
            label=label,
        )
        if isinstance(decision, tuple) and len(decision) == 5:
            return decision
        if decision is None:
            return custom_instructions, replace_instructions, label, None, False
        if getattr(decision, "cancel", False):
            self.ports.sync_extension_diagnostics(phase="runtime")
            return custom_instructions, replace_instructions, label, None, True
        return (
            getattr(decision, "custom_instructions", None) or custom_instructions,
            getattr(decision, "replace_instructions", None)
            if getattr(decision, "replace_instructions", None) is not None
            else replace_instructions,
            getattr(decision, "label", None) or label,
            normalize_branch_summary_output(getattr(decision, "summary", None), from_hook=True)
            if getattr(decision, "summary", None) is not None
            else None,
            False,
        )

    def _branch_summary_runner(
        self,
        *,
        custom_instructions: str | None,
        replace_instructions: bool,
    ) -> Callable[[Sequence[object], CancellationSignal], Awaitable[BranchSummaryOutput]]:
        async def run(
            entries: Sequence[object],
            signal: CancellationSignal,
        ) -> BranchSummaryOutput:
            return await self.ports.execute_branch_summary(
                entries,
                model=self.ports.agent.model,
                signal=signal,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )

        return run

    def _last_assistant_message(self) -> AssistantMessage | None:
        for message in reversed(self.ports.agent.state.messages):
            if isinstance(message, AssistantMessage):
                return message
        return None


def _is_model_selection(value: object) -> bool:
    return value.__class__.__name__ == "ModelSelection"


__all__ = ["SessionOperations", "SessionOperationsPorts"]

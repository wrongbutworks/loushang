from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolCallView,
    ToolResultView,
    ToolTranscriptBlock,
    ToolTranscriptProjector,
)

ErrorId = int | str
ToolFinishCleanup = Literal["before_projection", "after_target"]


@dataclass(frozen=True, slots=True)
class ToolFinishContext:
    """Snapshot the state needed to finish one tool without mutating it yet."""

    tool_call_id: str
    snapshot: ToolCallSnapshot | None
    started_at: float


class ConversationProjectionTarget(Protocol):
    """Receive product-neutral conversation facts for one UI surface."""

    def run_started(self, *, start_time: Callable[[], float]) -> None: ...

    def queues_updated(
        self,
        *,
        steers: tuple[str, ...],
        followups: tuple[str, ...],
    ) -> None: ...

    def user_message(self, text: str) -> None: ...

    def assistant_started(self) -> None: ...

    def assistant_delta(self, delta: str) -> None: ...

    def assistant_finished(
        self,
        final_text: str,
        *,
        error_message: str | None,
        show_error: bool,
    ) -> None: ...

    def assistant_error(self, error_message: str) -> None: ...

    def tool_started(
        self,
        tool_call_id: str,
        snapshot: ToolCallSnapshot,
    ) -> None: ...

    def tool_finished(
        self,
        block: ToolTranscriptBlock,
        *,
        elapsed_seconds: float,
    ) -> None: ...

    def tool_result_message(self, block: ToolTranscriptBlock) -> None: ...

    def retry_started(
        self,
        *,
        attempt: int | None,
        max_attempts: int | None,
        delay_ms: int | float | None,
        error_message: str | None,
    ) -> None: ...

    def compaction_started(self, *, reason: str | None) -> None: ...

    def compaction_finished(
        self,
        *,
        error_message: str | None,
        summary: str,
        tokens_before: int | None,
    ) -> None: ...


@dataclass(slots=True)
class ConversationProjector:
    """Coordinate reusable conversation projection state for a UI target."""

    target: ConversationProjectionTarget
    tool_projector: ToolTranscriptProjector = field(
        default_factory=ToolTranscriptProjector
    )
    now: Callable[[], float] = time.monotonic
    track_rendered_tool_results: bool = True
    measure_tool_elapsed: bool = True
    tool_finish_cleanup: ToolFinishCleanup = "after_target"
    tool_calls: dict[str, ToolCallSnapshot] = field(
        default_factory=dict,
        repr=False,
    )
    rendered_tool_results: set[str] = field(default_factory=set, repr=False)
    rendered_assistant_errors: set[ErrorId] = field(
        default_factory=set,
        repr=False,
    )
    last_error_message: str | None = None
    _tool_started_at: dict[str, float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def run_started(self) -> None:
        self.tool_calls.clear()
        self._tool_started_at.clear()
        self.target.run_started(start_time=self.now)

    def queues_updated(
        self,
        *,
        steers: tuple[str, ...],
        followups: tuple[str, ...],
    ) -> None:
        self.target.queues_updated(steers=steers, followups=followups)

    def user_message(self, text: str) -> None:
        self.target.user_message(text)

    def assistant_started(self) -> None:
        self.target.assistant_started()

    def assistant_delta(self, delta: str) -> None:
        self.target.assistant_delta(delta)

    def assistant_finished(
        self,
        final_text: str,
        *,
        error_message: str | None = None,
        show_error: bool = False,
        error_id: ErrorId | None = None,
    ) -> None:
        show_error = self._remember_assistant_error(
            error_message,
            show_error=show_error,
            error_id=error_id,
        )
        self.target.assistant_finished(
            final_text,
            error_message=error_message,
            show_error=show_error,
        )

    def assistant_error(
        self,
        error_message: str,
        *,
        show_error: bool,
        error_id: ErrorId | None = None,
    ) -> None:
        if self._remember_assistant_error(
            error_message,
            show_error=show_error,
            error_id=error_id,
        ):
            self.target.assistant_error(error_message)

    def tool_started(self, view: ToolCallView) -> None:
        snapshot = self.tool_projector.remember_call(view)
        self.tool_calls[view.tool_call_id] = snapshot
        if self.measure_tool_elapsed:
            self._tool_started_at[view.tool_call_id] = self.now()
        self.target.tool_started(view.tool_call_id, snapshot)

    def tool_updated(self, view: ToolCallView) -> None:
        if view.tool_call_id not in self.tool_calls:
            self.tool_started(view)

    def has_active_tool_call(self, tool_call_id: str) -> bool:
        return tool_call_id in self.tool_calls

    def tool_call_snapshot(self, tool_call_id: str) -> ToolCallSnapshot | None:
        return self.tool_calls.get(tool_call_id)

    def has_rendered_tool_result(self, tool_call_id: str) -> bool:
        return (
            self.track_rendered_tool_results
            and tool_call_id in self.rendered_tool_results
        )

    def begin_tool_finish(self, tool_call_id: str) -> ToolFinishContext:
        fallback_started_at = self.now() if self.measure_tool_elapsed else 0.0
        context = ToolFinishContext(
            tool_call_id=tool_call_id,
            snapshot=self.tool_calls.get(tool_call_id),
            started_at=self._tool_started_at.get(
                tool_call_id,
                fallback_started_at,
            ),
        )
        if self.tool_finish_cleanup == "before_projection":
            self._complete_tool_finish(context)
        return context

    def tool_finished(
        self,
        view: ToolResultView,
        *,
        context: ToolFinishContext | None = None,
    ) -> None:
        context = context or self.begin_tool_finish(view.tool_call_id)
        block = self.tool_projector.project_result(view, context.snapshot)
        finished_at = self.now() if self.measure_tool_elapsed else context.started_at
        self.target.tool_finished(
            block,
            elapsed_seconds=max(0.0, finished_at - context.started_at),
        )
        if self.tool_finish_cleanup == "after_target":
            self._complete_tool_finish(context)

    def tool_result_message(
        self,
        view: ToolResultView,
        *,
        deduplicate: bool = True,
    ) -> None:
        if deduplicate and self.has_rendered_tool_result(view.tool_call_id):
            return
        if deduplicate and self.track_rendered_tool_results:
            self.rendered_tool_results.add(view.tool_call_id)
        self.target.tool_result_message(self.tool_projector.project_result(view))

    def _complete_tool_finish(self, context: ToolFinishContext) -> None:
        self.tool_calls.pop(context.tool_call_id, None)
        self._tool_started_at.pop(context.tool_call_id, None)
        if self.track_rendered_tool_results:
            self.rendered_tool_results.add(context.tool_call_id)

    def retry_started(
        self,
        *,
        attempt: int | None,
        max_attempts: int | None,
        delay_ms: int | float | None,
        error_message: str | None,
    ) -> None:
        self.target.retry_started(
            attempt=attempt,
            max_attempts=max_attempts,
            delay_ms=delay_ms,
            error_message=error_message,
        )

    def compaction_started(self, *, reason: str | None) -> None:
        self.target.compaction_started(reason=reason)

    def compaction_finished(
        self,
        *,
        error_message: str | None,
        summary: str,
        tokens_before: int | None,
    ) -> None:
        self.target.compaction_finished(
            error_message=error_message,
            summary=summary,
            tokens_before=tokens_before,
        )

    def _remember_assistant_error(
        self,
        error_message: str | None,
        *,
        show_error: bool,
        error_id: ErrorId | None,
    ) -> bool:
        if not error_message:
            return False
        self.last_error_message = error_message
        if not show_error:
            return False
        if error_id is None:
            return True
        if error_id in self.rendered_assistant_errors:
            return False
        self.rendered_assistant_errors.add(error_id)
        return True


__all__ = [
    "ConversationProjectionTarget",
    "ConversationProjector",
    "ToolFinishContext",
]

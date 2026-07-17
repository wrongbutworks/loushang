from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from loushang.coding.ui.conversation_event_adapter import (
    CodingConversationEventAdapter,
)
from loushang.coding.ui.plain_renderer import PlainCodingUiRenderer
from loushang.coding.ui.tool_blocks import ToolTranscriptProjector
from loushang.harness.presentation import ToolDefinitionResolver
from loushang.harnesstui.conversation.projection import ConversationProjector
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
)


@dataclass(init=False)
class PlainCodingEventRenderer:
    """Coding raw-event facade for the plain conversation target."""

    renderer: PlainCodingUiRenderer
    tool_definition_resolver: ToolDefinitionResolver | None = None
    max_tool_body_lines: int = 8
    render_user_messages: bool = True
    _tool_projector: ToolTranscriptProjector = field(init=False, repr=False)
    _projection: ConversationProjector = field(init=False, repr=False)
    _adapter: CodingConversationEventAdapter = field(init=False, repr=False)

    def __init__(
        self,
        renderer: PlainCodingUiRenderer,
        tool_definition_resolver: ToolDefinitionResolver | None = None,
        max_tool_body_lines: int = 8,
        tool_calls: dict[str, ToolCallSnapshot] | None = None,
        rendered_tool_results: set[str] | None = None,
        rendered_assistant_errors: set[int] | None = None,
        last_error_message: str | None = None,
        render_user_messages: bool = True,
    ) -> None:
        self.renderer = renderer
        self.tool_definition_resolver = tool_definition_resolver
        self.max_tool_body_lines = max_tool_body_lines
        self.render_user_messages = render_user_messages
        self._tool_projector = ToolTranscriptProjector(
            tool_definition_resolver=tool_definition_resolver,
            max_body_lines=max_tool_body_lines,
        )
        self._projection = ConversationProjector(
            target=_PlainProjectionTarget(
                renderer=renderer,
                render_user_messages=render_user_messages,
            ),
            tool_projector=self._tool_projector.neutral_projector,
            measure_tool_elapsed=False,
            tool_finish_cleanup="before_projection",
            tool_calls=tool_calls if tool_calls is not None else {},
            rendered_tool_results=(
                rendered_tool_results
                if rendered_tool_results is not None
                else set()
            ),
            rendered_assistant_errors=cast(
                set[int | str],
                rendered_assistant_errors
                if rendered_assistant_errors is not None
                else set(),
            ),
            last_error_message=last_error_message,
        )
        self._adapter = CodingConversationEventAdapter(
            self._projection,
            self._tool_projector,
            recover_tool_updates=False,
            project_tool_result_messages=True,
            require_assistant_message_for_delta=False,
            project_run_starts=False,
            project_queue_updates=False,
            project_user_messages=render_user_messages,
            project_assistant_error_text=False,
            project_compaction_details=False,
        )

    @property
    def tool_calls(self) -> dict[str, ToolCallSnapshot]:
        return self._projection.tool_calls

    @tool_calls.setter
    def tool_calls(self, value: dict[str, ToolCallSnapshot]) -> None:
        self._projection.tool_calls = value

    @property
    def rendered_tool_results(self) -> set[str]:
        return self._projection.rendered_tool_results

    @rendered_tool_results.setter
    def rendered_tool_results(self, value: set[str]) -> None:
        self._projection.rendered_tool_results = value

    @property
    def rendered_assistant_errors(self) -> set[int]:
        return cast(set[int], self._projection.rendered_assistant_errors)

    @rendered_assistant_errors.setter
    def rendered_assistant_errors(self, value: set[int]) -> None:
        self._projection.rendered_assistant_errors = cast(set[int | str], value)

    @property
    def last_error_message(self) -> str | None:
        return self._projection.last_error_message

    @last_error_message.setter
    def last_error_message(self, value: str | None) -> None:
        self._projection.last_error_message = value

    def handle(self, event: dict[str, Any]) -> None:
        self._adapter.handle(event)


@dataclass(slots=True)
class _PlainProjectionTarget:
    renderer: PlainCodingUiRenderer
    render_user_messages: bool

    def run_started(self, *, start_time: Callable[[], float]) -> None:
        del start_time

    def queues_updated(
        self,
        *,
        steers: tuple[str, ...],
        followups: tuple[str, ...],
    ) -> None:
        del steers, followups

    def user_message(self, text: str) -> None:
        if self.render_user_messages:
            self.renderer.render_user(text)

    def assistant_started(self) -> None:
        self.renderer.begin_assistant()

    def assistant_delta(self, delta: str) -> None:
        self.renderer.write_assistant_delta(delta)

    def assistant_finished(
        self,
        final_text: str,
        *,
        error_message: str | None,
        show_error: bool,
    ) -> None:
        # Plain output must not commit an errored (including intentionally aborted)
        # assistant draft. The next run replaces the pending draft buffer.
        if error_message is not None:
            if show_error:
                self.renderer.render_error(error_message)
            return
        self.renderer.end_assistant(final_text)

    def assistant_error(self, error_message: str) -> None:
        self.renderer.render_error(error_message)

    def tool_started(
        self,
        tool_call_id: str,
        snapshot: ToolCallSnapshot,
    ) -> None:
        del tool_call_id, snapshot

    def tool_finished(
        self,
        block: ToolTranscriptBlock,
        *,
        elapsed_seconds: float,
    ) -> None:
        del elapsed_seconds
        self.renderer.render_tool_block(block)

    def tool_result_message(self, block: ToolTranscriptBlock) -> None:
        self.renderer.render_tool_block(block)

    def retry_started(
        self,
        *,
        attempt: int | None,
        max_attempts: int | None,
        delay_ms: int | float | None,
        error_message: str | None,
    ) -> None:
        self.renderer.render_status(
            f"[retry] attempt {attempt}/{max_attempts} in {delay_ms}ms: {error_message}"
        )

    def compaction_started(self, *, reason: str | None) -> None:
        self.renderer.render_status(f"[compact] start: {reason}")

    def compaction_finished(
        self,
        *,
        error_message: str | None,
        summary: str,
        tokens_before: int | None,
    ) -> None:
        del summary, tokens_before
        if error_message:
            self.renderer.render_status(f"[compact] error: {error_message}")
        else:
            self.renderer.render_status("[compact] done")


__all__ = ["PlainCodingEventRenderer"]

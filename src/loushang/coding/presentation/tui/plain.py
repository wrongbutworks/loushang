from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, cast

from loushang.coding.presentation.tui.events import CodingConversationEventAdapter
from loushang.coding.presentation.tui.tool_transcript import (
    CodingToolTranscriptProjection,
    build_coding_tool_transcript_projection,
    tool_block_to_record,
)
from loushang.harness.presentation import ToolDefinitionResolver
from loushang.harnesstui.conversation.plain_target import (
    PlainConversationProjectionTarget,
)
from loushang.harnesstui.conversation.projection import (
    ConversationProjectionBinding,
    ConversationProjector,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
)
from loushang.harnesstui.plain.renderer import (
    PlainConversationGlyphs,
    PlainConversationProfile,
    PlainConversationRenderer,
)
from loushang.tui.cell_width import strip_control_sequences
from loushang.tui.render import MarkdownBlock as MarkdownBlock
from loushang.tui.transcript import (
    AssistantMessageRecord,
    DisplayRecord,
    ErrorRecord,
    ToolExecutionRecord,
    UserPromptRecord,
    WorkedDividerRecord,
)

_INTERRUPTION_MESSAGE = (
    "Conversation interrupted - tell the model what to do differently. "
    "Something went wrong? Hit `/feedback` to report the issue."
)


def _coding_terminal_columns() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _coding_line(line: str, record: DisplayRecord) -> str:
    line = strip_control_sequences(line)
    if isinstance(record, UserPromptRecord) and line.startswith("> "):
        return "› " + line[2:]
    if isinstance(record, AssistantMessageRecord) and line.startswith("* "):
        return "• " + line[2:]
    if isinstance(record, ErrorRecord) and line.startswith("! Error: "):
        return "■ Error: " + line[len("! Error: ") :]
    if isinstance(record, ToolExecutionRecord):
        if line.startswith("- Ran "):
            return "• Ran " + line[len("- Ran ") :]
        if line.startswith("! Ran "):
            return "■ Ran " + line[len("! Ran ") :]
    if isinstance(record, WorkedDividerRecord) and line.startswith("- Worked for "):
        return line.replace("-", "─", 1).replace("-", "─")
    return line


_CODING_PLAIN_CONVERSATION_PROFILE = PlainConversationProfile(
    title="Loushang TUI",
    interruption_message=_INTERRUPTION_MESSAGE,
    glyphs=PlainConversationGlyphs(
        user_prompt="› ",
        assistant="• ",
        item="• ",
        error="■ Error: ",
        interruption="■ ",
        rule="─",
    ),
    line_mapper=_coding_line,
    tool_block_projector=tool_block_to_record,
    terminal_columns=_coding_terminal_columns,
)


@dataclass
class PlainCodingUiRenderer(PlainConversationRenderer):
    """Coding presentation profile over the shared plain renderer."""

    profile: PlainConversationProfile = field(
        default=_CODING_PLAIN_CONVERSATION_PROFILE,
        init=False,
        repr=False,
    )


@dataclass(init=False)
class PlainCodingEventRenderer(ConversationProjectionBinding[dict[str, Any]]):
    """Coding raw-event facade for the plain conversation target."""

    renderer: PlainCodingUiRenderer
    tool_definition_resolver: ToolDefinitionResolver | None = None
    max_tool_body_lines: int = 8
    render_user_messages: bool = True
    _tool_projector: CodingToolTranscriptProjection = field(init=False, repr=False)

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
        self._tool_projector = build_coding_tool_transcript_projection(
            tool_definition_resolver=tool_definition_resolver,
            max_body_lines=max_tool_body_lines,
        )
        projection = ConversationProjector(
            target=PlainConversationProjectionTarget(renderer=renderer),
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
        adapter = CodingConversationEventAdapter(
            projection,
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
        ConversationProjectionBinding.__init__(
            self,
            projector=projection,
            event_handler=adapter.handle,
        )


__all__ = [
    "PlainCodingEventRenderer",
    "PlainCodingUiRenderer",
]

"""Optional Agent binding over the product-neutral conversation components."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from functools import partial
from typing import Any, TypeAlias

from loushang.agent.types import AgentToolResult
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    COMMAND_EXECUTION_KIND,
    CONTEXT_BRANCH_SUMMARY_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    CONVERSATION_METADATA_PATCH_KIND,
    EXTENSION_DATA_KIND,
    MODEL_SELECTION_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    STANDARD_AGENT_TRANSCRIPT_KINDS,
    THINKING_SELECTION_KIND,
)
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime
from loushang.harness.tools.workspace.presentation import (
    render_tool_result_presentation,
)
from loushang.harnesstui.conversation.history import (
    ConversationHistoryProjector,
    HistoryRecordDisposition,
    ToolMessageProjector,
    project_agent_message_payload,
    project_command_execution_payload,
    project_context_branch_summary_payload,
    project_context_compaction_payload,
)
from loushang.harnesstui.conversation.plain_target import (
    PlainConversationProjectionPort,
    build_plain_conversation_projection,
)
from loushang.harnesstui.conversation.projection import (
    ConversationProjectionBinding,
    SessionConversationEventAdapter,
)
from loushang.harnesstui.conversation.runtime_view import StringQueueReader
from loushang.harnesstui.conversation.screen_target import (
    ScreenConversationProjectionPort,
    ScreenProjectionStatusCopy,
    StandardScreenProjectionStatusCopy,
    build_screen_conversation_projection,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
    ToolTranscriptProjectionBinding,
    build_mapping_tool_transcript_projection,
    tool_block_to_record,
)
from loushang.tui.transcript import DisplayRecord, ToolExecutionRecord

AgentToolTranscriptProjection: TypeAlias = ToolTranscriptProjectionBinding[
    Mapping[str, Any], object
]

STANDARD_AGENT_HISTORY_DISPOSITIONS: dict[str, HistoryRecordDisposition] = {
    AGENT_MESSAGE_KIND: "render",
    THINKING_SELECTION_KIND: "state-only",
    MODEL_SELECTION_KIND: "state-only",
    COMMAND_EXECUTION_KIND: "render",
    CONTEXT_COMPACTION_CHECKPOINT_KIND: "render",
    CONTEXT_BRANCH_SUMMARY_KIND: "render",
    APPLICATION_MESSAGE_KIND: "render",
    EXTENSION_DATA_KIND: "hidden",
    RECORD_ANNOTATION_PATCH_KIND: "metadata-only",
    CONVERSATION_METADATA_PATCH_KIND: "metadata-only",
}
if set(STANDARD_AGENT_HISTORY_DISPOSITIONS) != set(STANDARD_AGENT_TRANSCRIPT_KINDS):
    raise RuntimeError("Agent history dispositions must cover every standard kind")


def build_agent_tool_transcript_projection(
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    render_runtime: ToolRenderRuntime | None = None,
    max_body_lines: int = 8,
) -> AgentToolTranscriptProjection:
    """Bind standard Agent tool results to the workspace transcript policy."""

    resolved_runtime = render_runtime or ToolRenderRuntime()
    render_event = (
        None
        if tool_definition_resolver is None
        else lambda event, expanded: _render_agent_tool_event(
            event,
            expanded=expanded,
            tool_definition_resolver=tool_definition_resolver,
            render_runtime=resolved_runtime,
        )
    )
    return build_mapping_tool_transcript_projection(
        result_text=_agent_result_text,
        result_details=_agent_result_details,
        result_terminated=lambda result: (
            isinstance(result, AgentToolResult) and result.terminate
        ),
        error_summary=_agent_error_summary,
        message_event=_agent_tool_result_message_event,
        render_event_text=render_event,
        max_body_lines=max_body_lines,
    )


def agent_tool_block_to_record(
    block: ToolTranscriptBlock,
    *,
    elapsed_seconds: float = 0.0,
) -> ToolExecutionRecord:
    """Apply the standard Agent workspace command-label policy."""

    if block.command is None and block.verb in {"Ran", "Tested"}:
        block = replace(block, command=block.title)
    return tool_block_to_record(block, elapsed_seconds=elapsed_seconds)


def project_agent_conversation_history(
    items: Iterable[object],
    *,
    tool_result_projector: ToolMessageProjector,
) -> tuple[DisplayRecord, ...]:
    """Project a standard Agent transcript branch into display records."""

    message_projector = partial(
        project_agent_message_payload,
        tool_result_projector=tool_result_projector,
    )
    return ConversationHistoryProjector(
        dispositions=STANDARD_AGENT_HISTORY_DISPOSITIONS,
        payload_projectors={
            AGENT_MESSAGE_KIND: message_projector,
            COMMAND_EXECUTION_KIND: project_command_execution_payload,
            CONTEXT_COMPACTION_CHECKPOINT_KIND: project_context_compaction_payload,
            CONTEXT_BRANCH_SUMMARY_KIND: project_context_branch_summary_payload,
            APPLICATION_MESSAGE_KIND: message_projector,
        },
        fallback_projector=message_projector,
    ).project_items(items)


def build_agent_plain_conversation_projection(
    renderer: PlainConversationProjectionPort,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    max_tool_body_lines: int = 8,
    tool_calls: dict[str, ToolCallSnapshot] | None = None,
    rendered_tool_results: set[str] | None = None,
    rendered_assistant_errors: set[int | str] | None = None,
    last_error_message: str | None = None,
    render_user_messages: bool = True,
) -> ConversationProjectionBinding[dict[str, Any]]:
    """Build the standard Agent event adapter for a plain conversation."""

    tool_projection = build_agent_tool_transcript_projection(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    return build_plain_conversation_projection(
        renderer,
        tool_projector=tool_projection.neutral_projector,
        event_handler_factory=lambda projection: (
            SessionConversationEventAdapter(
                projection,
                tool_projection,
                recover_tool_updates=False,
                require_assistant_message_for_delta=False,
                project_run_starts=False,
                project_queue_updates=False,
                project_user_messages=render_user_messages,
                project_assistant_error_text=False,
                project_compaction_details=False,
            ).handle
        ),
        tool_calls=tool_calls,
        rendered_tool_results=rendered_tool_results,
        rendered_assistant_errors=rendered_assistant_errors,
        last_error_message=last_error_message,
    )


def build_agent_screen_conversation_projection(
    app: ScreenConversationProjectionPort,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    max_tool_body_lines: int = 8,
    read_pending_steers: StringQueueReader = tuple,
    read_pending_followups: StringQueueReader = tuple,
    status_copy: ScreenProjectionStatusCopy | None = None,
    now: Callable[[], float] = time.monotonic,
) -> ConversationProjectionBinding[dict[str, Any]]:
    """Build the standard Agent event adapter for a screen conversation."""

    tool_projection = build_agent_tool_transcript_projection(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    return build_screen_conversation_projection(
        app,
        tool_projector=tool_projection.neutral_projector,
        tool_title_resolver=_standard_tool_title,
        tool_record_projector=agent_tool_block_to_record,
        status_copy=status_copy or StandardScreenProjectionStatusCopy(),
        event_handler_factory=lambda projection: (
            SessionConversationEventAdapter(
                projection,
                tool_projection,
                read_pending_steers=read_pending_steers,
                read_pending_followups=read_pending_followups,
                project_tool_result_messages=False,
            ).handle
        ),
        now=now,
    )


def _agent_tool_result_message_event(message: object) -> Mapping[str, Any]:
    tool_name = str(getattr(message, "tool_name", "tool"))
    tool_call_id = getattr(message, "tool_call_id", None)
    return {
        "type": "tool_execution_end",
        "tool_call_id": (
            tool_call_id
            if isinstance(tool_call_id, str) and tool_call_id
            else tool_name
        ),
        "tool_name": tool_name,
        "result": AgentToolResult(
            content=getattr(message, "content", None) or [],
            details=getattr(message, "details", None),
            terminate=bool(getattr(message, "terminate", False)),
        ),
        "is_error": bool(getattr(message, "is_error", False)),
    }


def _agent_result_text(result: object, max_lines: int) -> str:
    if not isinstance(result, AgentToolResult):
        return ""
    return render_tool_result_presentation(
        result.content,
        _agent_result_details(result),
        max_collapsed_lines=max_lines,
    ).collapsed


def _agent_result_details(result: object) -> Mapping[str, Any]:
    if not isinstance(result, AgentToolResult):
        return {}
    try:
        details = result.transcript_details()
    except Exception:
        return {}
    return details if isinstance(details, Mapping) else {}


def _agent_error_summary(result: object) -> str | None:
    content = getattr(result, "content", None)
    if not isinstance(content, list):
        return None
    for part in content:
        text = getattr(part, "text", None)
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            summary = line.strip()
            if summary:
                return summary if len(summary) <= 160 else summary[:157] + "..."
    return None


def _render_agent_tool_event(
    event: Mapping[str, Any],
    *,
    expanded: bool,
    tool_definition_resolver: ToolDefinitionResolver,
    render_runtime: ToolRenderRuntime,
) -> str | None:
    try:
        rendered = render_runtime.render_event(
            event,
            tool_definition_resolver,
            expanded=expanded,
        )
    except Exception:
        return None
    if isinstance(rendered, str):
        return rendered
    if isinstance(rendered, Mapping):
        plain = rendered.get("plain_text")
        if isinstance(plain, str):
            return plain
        text = rendered.get("text")
        if isinstance(text, str):
            return text
    return None


def _standard_tool_title(snapshot: ToolCallSnapshot) -> str:
    if snapshot.rendered_call_text:
        return snapshot.rendered_call_text.splitlines()[0].strip()
    return snapshot.tool_name


__all__ = [
    "AgentToolTranscriptProjection",
    "STANDARD_AGENT_HISTORY_DISPOSITIONS",
    "agent_tool_block_to_record",
    "build_agent_plain_conversation_projection",
    "build_agent_screen_conversation_projection",
    "build_agent_tool_transcript_projection",
    "project_agent_conversation_history",
]

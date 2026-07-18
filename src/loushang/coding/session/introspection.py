from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from loushang.ai.types import AssistantMessage, ToolCall, ToolResultMessage, UserMessage
from loushang.coding.compaction import calculate_context_tokens, estimate_context_tokens
from loushang.coding.session.types import ContextUsage, SessionStats, TokenUsageTotals
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    AgentTranscriptRecord,
    ContextCompactionCheckpoint,
    SessionTreeNode,
)

if TYPE_CHECKING:
    from loushang.coding.session.agent_session import AgentSession


def build_context_usage(session: AgentSession) -> ContextUsage | None:
    view_controller = getattr(session, "_view_controller", None)
    view_getter = getattr(view_controller, "get_context_usage", None)
    if callable(view_getter):
        usage = view_getter()
        if isinstance(usage, ContextUsage) or usage is None:
            return usage

    get_context_usage = getattr(session, "get_context_usage", None)
    if callable(get_context_usage):
        usage = get_context_usage()
        if isinstance(usage, ContextUsage) or usage is None:
            return usage

    session_context = session.get_session_context()
    messages = list(session_context.messages)
    entries = session.session_manager.get_entries()
    branch_entries = session.session_manager.get_branch()

    assistant_message_count = 0
    user_message_count = 0
    tool_call_count = 0
    tool_result_count = 0

    for message in messages:
        if isinstance(message, AssistantMessage):
            assistant_message_count += 1
            tool_call_count += sum(
                1 for block in message.content if isinstance(block, ToolCall)
            )
        elif isinstance(message, UserMessage):
            user_message_count += 1
        elif isinstance(message, ToolResultMessage):
            tool_result_count += 1

    estimated_context_tokens = (
        estimate_context_tokens(messages).tokens if messages else 0
    )
    branch_depth = len(branch_entries)
    return ContextUsage(
        message_count=len(messages),
        assistant_message_count=assistant_message_count,
        user_message_count=user_message_count,
        tool_call_count=tool_call_count,
        tool_result_count=tool_result_count,
        custom_message_count=sum(
            1 for entry in entries if entry.kind == APPLICATION_MESSAGE_KIND
        ),
        estimated_context_tokens=estimated_context_tokens,
        has_compaction=any(
            entry.kind == CONTEXT_COMPACTION_CHECKPOINT_KIND for entry in entries
        ),
        branch_depth=branch_depth,
        leaf_entry_id=session.session_manager.get_leaf_id(),
    )


def build_session_stats(session: AgentSession) -> SessionStats:
    entries = session.session_manager.get_entries()
    context_usage = build_context_usage(session)

    return SessionStats(
        session_id=session.session_id,
        session_name=session.session_name,
        entry_count=len(entries),
        message_count=context_usage.message_count if context_usage is not None else 0,
        custom_message_count=sum(
            1 for entry in entries if entry.kind == APPLICATION_MESSAGE_KIND
        ),
        active_tool_count=len(session.get_active_tool_names()),
        is_retrying=session.is_retrying,
        is_compacting=session.is_compacting,
        has_diagnostics=bool(session.get_last_diagnostics(limit=1)),
        branch_count=_count_leaf_branches(session.session_manager.get_tree()),
        last_model_selection=session.get_model_selection(),
        context_usage=context_usage,
        tokens=_build_token_usage_totals(session.session_manager.get_branch()),
    )


def _build_token_usage_totals(
    branch_entries: Sequence[AgentTranscriptRecord],
) -> TokenUsageTotals:
    latest_compaction = _latest_compaction_with_index(branch_entries)
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_tokens = 0
    start_index = 0

    if latest_compaction is not None:
        compaction, index = latest_compaction
        input_tokens += compaction.tokens_before
        total_tokens += compaction.tokens_before
        start_index = index + 1

    for entry in branch_entries[start_index:]:
        if entry.kind != AGENT_MESSAGE_KIND:
            continue
        message = entry.payload
        if not isinstance(message, AssistantMessage):
            continue
        if message.stop_reason in {"aborted", "error"}:
            continue
        usage = message.usage
        input_tokens += int(getattr(usage, "input", 0) or 0)
        output_tokens += int(getattr(usage, "output", 0) or 0)
        cache_read_tokens += int(getattr(usage, "cache_read", 0) or 0)
        cache_write_tokens += int(getattr(usage, "cache_write", 0) or 0)
        total_tokens += calculate_context_tokens(usage)

    return TokenUsageTotals(
        input=input_tokens,
        output=output_tokens,
        cache_read=cache_read_tokens,
        cache_write=cache_write_tokens,
        total=total_tokens,
    )


def _latest_compaction_with_index(
    entries: Sequence[AgentTranscriptRecord],
) -> tuple[ContextCompactionCheckpoint, int] | None:
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        if entry.kind == CONTEXT_COMPACTION_CHECKPOINT_KIND and isinstance(
            entry.payload, ContextCompactionCheckpoint
        ):
            return entry.payload, index
    return None


def _count_leaf_branches(nodes: list[SessionTreeNode]) -> int:
    if not nodes:
        return 0

    def _count(node: SessionTreeNode) -> int:
        if not node.children:
            return 1
        return sum(_count(child) for child in node.children)

    return sum(_count(node) for node in nodes)

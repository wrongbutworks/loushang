from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, is_dataclass

from loushang.agent import AgentMessage
from loushang.ai import CallOptions, Context, complete
from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.compaction.profiles import (
    CODING_COMPACTION_SUMMARY_PROFILE,
    CODING_TURN_PREFIX_SUMMARY_PROFILE,
)
from loushang.coding.compaction.types import (
    CompactionPlan,
    CompactionPreparation,
    CompactionResult,
)
from loushang.harness.agent_transcript import (
    AgentTranscriptProfile,
    AgentTranscriptRecord,
    ContextCompactionCheckpoint,
    context_item_to_model_message,
)
from loushang.harness.context import (
    ConversationCompactionPlanner,
)
from loushang.harness.context.budget import calculate_compaction_budget
from loushang.harness.context.summary import (
    build_summary_prompt,
    compose_summary_prompt,
)
from loushang.harness.context.usage import ContextUsageEstimate

TOOL_RESULT_MAX_CHARS = 2_000

_TRANSCRIPT_PROFILE = AgentTranscriptProfile(
    context_token_estimator=lambda messages: (
        estimate_context_tokens(list(messages)).tokens
    )
)


@dataclass(frozen=True)
class _PreparedCompaction:
    plan: CompactionPlan
    previous_summary: str | None
    messages_to_summarize: list[AgentMessage]
    turn_prefix_messages: list[AgentMessage]


def calculate_context_tokens(usage: object) -> int:
    total_tokens = _usage_value(usage, "totalTokens", "total_tokens")
    if isinstance(total_tokens, int) and total_tokens > 0:
        return total_tokens
    return (
        int(_usage_value(usage, "input") or 0)
        + int(_usage_value(usage, "output") or 0)
        + int(_usage_value(usage, "cacheRead", "cache_read") or 0)
        + int(_usage_value(usage, "cacheWrite", "cache_write") or 0)
    )


def _assistant_text(message: object) -> str:
    return "".join(
        part.text
        for part in getattr(message, "content", ())
        if getattr(part, "type", None) == "text" and hasattr(part, "text")
    )


async def _complete_text(
    model: object,
    context: Context,
    options: CallOptions | None = None,
) -> str:
    return _assistant_text(await complete(model, context, options))


def estimate_context_tokens(messages: list[AgentMessage]) -> ContextUsageEstimate:
    usage_info = _last_assistant_usage_info(messages)
    if usage_info is None:
        estimated = sum(_estimate_message_tokens(message) for message in messages)
        return ContextUsageEstimate(
            tokens=estimated,
            usage_tokens=0,
            trailing_tokens=estimated,
            last_usage_index=None,
        )

    usage_tokens = calculate_context_tokens(usage_info["usage"])
    trailing_tokens = sum(
        _estimate_message_tokens(message)
        for message in messages[usage_info["index"] + 1 :]
    )
    return ContextUsageEstimate(
        tokens=usage_tokens + trailing_tokens,
        usage_tokens=usage_tokens,
        trailing_tokens=trailing_tokens,
        last_usage_index=usage_info["index"],
    )


def should_compact(
    context_tokens: int,
    context_window: int,
    *,
    enabled: bool,
    reserve_tokens: int,
    compact_percent: float = 100.0,
) -> bool:
    if not enabled:
        return False
    budget = calculate_compaction_budget(
        context_window=context_window,
        compact_percent=compact_percent,
        reserve_tokens=reserve_tokens,
    )
    return context_tokens > budget.threshold_tokens


def prepare_compaction(
    entries: list[AgentTranscriptRecord], keep_recent_tokens: int
) -> CompactionPreparation:
    prepared = _prepare_compaction(entries, keep_recent_tokens)
    return CompactionPreparation(
        first_kept_entry_id=prepared.plan.first_kept_entry_id,
        messages_to_summarize=prepared.messages_to_summarize,
        turn_prefix_messages=prepared.turn_prefix_messages,
        is_split_turn=prepared.plan.is_split_turn,
        tokens_before=prepared.plan.tokens_before,
        previous_summary=prepared.previous_summary,
        details={"compactionPlan": compaction_plan_to_payload(prepared.plan)},
        plan=prepared.plan,
    )


def plan_compaction(
    entries: list[AgentTranscriptRecord], keep_recent_tokens: int
) -> CompactionPlan:
    return _prepare_compaction(entries, keep_recent_tokens).plan


def compaction_plan_to_payload(plan: CompactionPlan) -> dict[str, object]:
    return {
        "previousCompactionId": plan.previous_compaction_id,
        "previousFirstKeptEntryId": plan.previous_first_kept_entry_id,
        "firstKeptEntryId": plan.first_kept_entry_id,
        "summarizedEntryIds": list(plan.summarized_entry_ids),
        "turnPrefixEntryIds": list(plan.turn_prefix_entry_ids),
        "keptEntryIds": list(plan.kept_entry_ids),
        "isSplitTurn": plan.is_split_turn,
        "tokensBefore": plan.tokens_before,
        "keepRecentTokens": plan.keep_recent_tokens,
    }


def _prepare_compaction(
    entries: list[AgentTranscriptRecord], keep_recent_tokens: int
) -> _PreparedCompaction:
    if not any(_entry_to_agent_message(entry) is not None for entry in entries):
        raise ValueError("Compaction requires at least one visible message entry.")
    shared_plan = _coding_compaction_planner().plan(
        entries,
        keep_recent_tokens=keep_recent_tokens,
    )
    messages_to_summarize = [
        message
        for entry in shared_plan.summarized_records
        if (message := _entry_to_agent_message(entry)) is not None
    ]
    turn_prefix_messages = [
        message
        for entry in shared_plan.turn_prefix_records
        if (message := _entry_to_agent_message(entry)) is not None
    ]
    summarized_entry_ids = list(shared_plan.summarized_record_ids)

    previous_boundary = shared_plan.previous_summary
    previous_first_kept_entry_id: str | None = None
    if previous_boundary is not None:
        previous_entry = next(
            (
                entry
                for entry in entries
                if entry.record_id == previous_boundary.record_id
                and isinstance(entry.payload, ContextCompactionCheckpoint)
            ),
            None,
        )
        if previous_entry is not None and isinstance(
            previous_entry.payload.first_kept_record_id, str
        ):
            previous_first_kept_entry_id = previous_entry.payload.first_kept_record_id
    plan = CompactionPlan(
        previous_compaction_id=(
            previous_boundary.record_id if previous_boundary is not None else None
        ),
        previous_first_kept_entry_id=previous_first_kept_entry_id,
        first_kept_entry_id=shared_plan.first_kept_record_id,
        summarized_entry_ids=tuple(summarized_entry_ids),
        turn_prefix_entry_ids=shared_plan.turn_prefix_record_ids,
        kept_entry_ids=shared_plan.kept_record_ids,
        is_split_turn=shared_plan.is_split_turn,
        tokens_before=shared_plan.tokens_before,
        keep_recent_tokens=shared_plan.keep_recent_tokens,
    )
    return _PreparedCompaction(
        plan=plan,
        messages_to_summarize=messages_to_summarize,
        turn_prefix_messages=turn_prefix_messages,
        previous_summary=(
            previous_boundary.content if previous_boundary is not None else None
        ),
    )


def _coding_compaction_planner() -> ConversationCompactionPlanner[
    AgentTranscriptRecord, str
]:
    return ConversationCompactionPlanner(
        _TRANSCRIPT_PROFILE.record_ports(),
        turn_start_roles=frozenset({"user"}),
        non_cut_roles=frozenset({"toolResult"}),
        missing_previous_summary="error",
    )


async def compact(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
) -> CompactionResult:
    summarize_kwargs = {
        "preparation": preparation,
        "model": model,
        "api_key": api_key,
        "headers": headers,
        "signal": signal,
    }
    if custom_instructions is not None:
        summarize_kwargs["custom_instructions"] = custom_instructions
    if preparation.is_split_turn and preparation.turn_prefix_messages:
        history_summary = (
            await _summarize_messages(**summarize_kwargs)
            if preparation.messages_to_summarize
            else "No prior history."
        )
        turn_prefix_summary = await _summarize_turn_prefix(
            messages=preparation.turn_prefix_messages,
            model=model,
            api_key=api_key,
            headers=headers,
            signal=signal,
        )
        summary = f"{history_summary}\n\n---\n\n**Turn Context (split turn):**\n\n{turn_prefix_summary}"
    else:
        summary = await _summarize_messages(**summarize_kwargs)

    file_details = _collect_file_operation_details(
        [*preparation.messages_to_summarize, *preparation.turn_prefix_messages]
    )
    summary = f"{summary}{_format_file_operations(file_details)}"
    details = _merge_compaction_details(preparation.details, file_details)
    return CompactionResult(
        summary=summary,
        first_kept_entry_id=preparation.first_kept_entry_id,
        tokens_before=preparation.tokens_before,
        details=details,
    )


def _usage_value(usage: object, *keys: str) -> object | None:
    if isinstance(usage, Mapping):
        for key in keys:
            value = usage.get(key)
            if value is not None:
                return value
        return None
    if is_dataclass(usage):
        for key in keys:
            if hasattr(usage, key):
                value = getattr(usage, key)
                if value is not None:
                    return value
        return None
    for key in keys:
        if hasattr(usage, key):
            value = getattr(usage, key)
            if value is not None:
                return value
    return None


def _last_assistant_usage_info(
    messages: list[AgentMessage],
) -> dict[str, object] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AssistantMessage) and message.stop_reason not in (
            "aborted",
            "error",
        ):
            return {"usage": message.usage, "index": index}
    return None


def _estimate_message_tokens(message: AgentMessage) -> int:
    chars = 0

    if isinstance(message, UserMessage):
        if isinstance(message.content, str):
            chars = len(message.content)
        else:
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    chars += len(block.text)
                elif getattr(block, "type", None) == "image":
                    chars += 4_800
        return (chars + 3) // 4

    if isinstance(message, AssistantMessage):
        for block in message.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                chars += len(block.text)
            elif block_type == "thinking":
                chars += len(block.thinking)
            elif block_type == "toolCall":
                chars += len(block.name) + len(str(block.arguments))
            elif block_type == "image":
                chars += 4_800
        return (chars + 3) // 4

    if isinstance(message, ToolResultMessage):
        for block in message.content:
            if getattr(block, "type", None) == "text":
                chars += len(block.text)
            elif getattr(block, "type", None) == "image":
                chars += 4_800
        return (chars + 3) // 4

    return 0


def _entry_to_agent_message(entry: AgentTranscriptRecord) -> AgentMessage | None:
    return _TRANSCRIPT_PROFILE.record_to_context_item(entry)


async def _summarize_messages(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
) -> str:
    mode = "update" if preparation.previous_summary else "initial"
    prompt = build_summary_prompt(
        CODING_COMPACTION_SUMMARY_PROFILE,
        _serialize_conversation(
            [
                projected
                for message in preparation.messages_to_summarize
                if (projected := context_item_to_model_message(message)) is not None
            ]
        ),
        mode=mode,
        previous_summary=preparation.previous_summary,
        custom_instructions=custom_instructions,
    )
    context = Context(
        system_prompt=prompt.system_prompt,
        messages=[
            UserMessage(
                role="user",
                content=[TextPart(type="text", text=prompt.user_prompt)],
                timestamp=0.0,
            )
        ],
    )
    return await _complete_text(
        model,
        context,
        CallOptions(
            api_key=api_key,
            headers=dict(headers or {}),
            cancellation=signal,
        ),
    )


async def _summarize_turn_prefix(
    *,
    messages: list[AgentMessage],
    model: object,
    api_key: str,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
) -> str:
    prompt = build_summary_prompt(
        CODING_TURN_PREFIX_SUMMARY_PROFILE,
        _serialize_conversation(_model_messages(messages)),
        mode="turn-prefix",
        previous_summary=None,
        custom_instructions=None,
    )
    return await _complete_text(
        model,
        Context(
            system_prompt=prompt.system_prompt,
            messages=[
                UserMessage(
                    role="user",
                    content=[TextPart(type="text", text=prompt.user_prompt)],
                    timestamp=0.0,
                )
            ],
        ),
        CallOptions(
            api_key=api_key,
            headers=dict(headers or {}),
            cancellation=signal,
        ),
    )


def _build_summarization_prompt(
    *,
    messages: list[AgentMessage],
    base_prompt: str,
    previous_summary: str | None,
    custom_instructions: str | None,
) -> str:
    conversation = _serialize_conversation(_model_messages(messages))
    return compose_summary_prompt(
        content=conversation,
        instructions=base_prompt,
        previous_summary=previous_summary,
        custom_instructions=custom_instructions,
    )


def _serialize_conversation(messages: Sequence[object]) -> str:
    parts: list[str] = []
    for message in messages:
        role = getattr(message, "role", None)
        if role == "user":
            content = getattr(message, "content", "")
            text = _content_text(content)
            if text:
                parts.append(f"[User]: {text}")
        elif role == "assistant":
            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls: list[str] = []
            for block in getattr(message, "content", ()):
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    text_parts.append(block.text)
                elif block_type == "thinking":
                    thinking_parts.append(block.thinking)
                elif block_type == "toolCall":
                    tool_calls.append(_format_tool_call(block))
            if thinking_parts:
                parts.append("[Assistant thinking]: " + "\n".join(thinking_parts))
            if text_parts:
                parts.append("[Assistant]: " + "\n".join(text_parts))
            if tool_calls:
                parts.append(f"[Assistant tool calls]: {'; '.join(tool_calls)}")
        elif role == "toolResult":
            text = _content_text(getattr(message, "content", ""))
            if text:
                parts.append(f"[Tool result]: {_truncate_for_summary(text)}")
    return "\n\n".join(parts)


def _model_messages(messages: Sequence[AgentMessage]) -> list[object]:
    return [
        projected
        for message in messages
        if (projected := context_item_to_model_message(message)) is not None
    ]


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.text)
            for block in content
            if getattr(block, "type", None) == "text"
        )
    return ""


def _format_tool_call(block: object) -> str:
    arguments = getattr(block, "arguments", {}) or {}
    if isinstance(arguments, Mapping):
        args = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    else:
        args = repr(arguments)
    return f"{getattr(block, 'name', '')}({args})"


def _truncate_for_summary(text: str) -> str:
    if len(text) <= TOOL_RESULT_MAX_CHARS:
        return text
    truncated_chars = len(text) - TOOL_RESULT_MAX_CHARS
    return f"{text[:TOOL_RESULT_MAX_CHARS]}\n\n[... {truncated_chars} more characters truncated]"


def _collect_file_operation_details(
    messages: list[AgentMessage],
) -> dict[str, list[str]]:
    read: set[str] = set()
    written: set[str] = set()
    edited: set[str] = set()
    for message in messages:
        if not isinstance(message, AssistantMessage):
            continue
        for block in message.content:
            if getattr(block, "type", None) != "toolCall":
                continue
            arguments = getattr(block, "arguments", None)
            if not isinstance(arguments, Mapping):
                continue
            path = arguments.get("path")
            if not isinstance(path, str) or not path:
                continue
            if block.name == "read":
                read.add(path)
            elif block.name == "write":
                written.add(path)
            elif block.name == "edit":
                edited.add(path)
    modified = written | edited
    return {
        "readFiles": sorted(path for path in read if path not in modified),
        "modifiedFiles": sorted(modified),
    }


def _format_file_operations(details: dict[str, list[str]]) -> str:
    sections: list[str] = []
    read_files = details["readFiles"]
    modified_files = details["modifiedFiles"]
    if read_files:
        sections.append("<read-files>\n" + "\n".join(read_files) + "\n</read-files>")
    if modified_files:
        sections.append(
            "<modified-files>\n" + "\n".join(modified_files) + "\n</modified-files>"
        )
    if not sections:
        return ""
    return "\n\n" + "\n\n".join(sections)


def _merge_compaction_details(
    existing: object | None, file_details: dict[str, list[str]]
) -> object | None:
    if not file_details["readFiles"] and not file_details["modifiedFiles"]:
        return existing
    if isinstance(existing, Mapping):
        merged = dict(existing)
        merged.update(file_details)
        return merged
    return file_details

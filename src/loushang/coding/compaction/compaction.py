from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, is_dataclass

from loushang.agent import AgentMessage
from loushang.ai import CallOptions, Context, complete
from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.compaction.types import (
    CompactionPlan,
    CompactionPreparation,
    CompactionResult,
)
from loushang.coding.message import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomMessageEntry,
    SessionEntry,
    SessionMessageEntry,
    create_branch_summary_message,
    create_custom_message,
)
from loushang.coding.message.custom_messages import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)
from loushang.coding.message.transformers import convert_to_llm
from loushang.harness.context.budget import calculate_compaction_budget
from loushang.harness.context.usage import ContextUsageEstimate

COMPACTION_SYSTEM_PROMPT = """Summarize the older conversation context for later continuation.

Preserve:
- the user's goal
- important constraints and decisions
- meaningful work already completed
- open questions and unresolved risks
"""

SUMMARIZATION_SYSTEM_PROMPT = """You are a context summarization assistant. Your task is to read a conversation between a user and an AI coding assistant, then produce a structured summary following the exact format specified.

Do NOT continue the conversation. Do NOT respond to any questions in the conversation. ONLY output the structured summary."""

SUMMARIZATION_PROMPT = """The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages."""

UPDATE_SUMMARIZATION_PROMPT = """The messages above are NEW conversation messages to incorporate into the existing summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

Use this EXACT format:

## Goal
[Preserve existing goals, add new ones if the task expanded]

## Constraints & Preferences
- [Preserve existing, add new ones discovered]

## Progress
### Done
- [x] [Include previously done items AND newly completed items]

### In Progress
- [ ] [Current work - update based on progress]

### Blocked
- [Current blockers - remove if resolved]

## Key Decisions
- **[Decision]**: [Brief rationale] (preserve all previous, add new)

## Next Steps
1. [Update based on current state]

## Critical Context
- [Preserve important context, add new if needed]

Keep each section concise. Preserve exact file paths, function names, and error messages."""

TURN_PREFIX_SUMMARIZATION_PROMPT = """This is the PREFIX of a turn that was too large to keep. The SUFFIX (recent work) is retained.

Summarize the prefix to provide context for the retained suffix:

## Original Request
[What did the user ask for in this turn?]

## Early Progress
- [Key decisions and work done in the prefix]

## Context for Suffix
- [Information needed to understand the retained recent work]

Be concise. Focus on what's needed to understand the kept suffix."""

TOOL_RESULT_MAX_CHARS = 2_000


@dataclass(frozen=True)
class _CutPointResult:
    first_kept_entry_index: int
    turn_start_index: int
    is_split_turn: bool


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
    trailing_tokens = sum(_estimate_message_tokens(message) for message in messages[usage_info["index"] + 1 :])
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


def prepare_compaction(entries: list[SessionEntry], keep_recent_tokens: int) -> CompactionPreparation:
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


def plan_compaction(entries: list[SessionEntry], keep_recent_tokens: int) -> CompactionPlan:
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


def _prepare_compaction(entries: list[SessionEntry], keep_recent_tokens: int) -> _PreparedCompaction:
    previous_summary: str | None = None
    previous_compaction_id: str | None = None
    previous_first_kept_entry_id: str | None = None
    boundary_start = 0
    previous_compaction_index = _latest_compaction_index(entries)
    if previous_compaction_index is not None:
        previous_compaction = entries[previous_compaction_index]
        if isinstance(previous_compaction, CompactionEntry):
            previous_summary = previous_compaction.summary
            previous_compaction_id = previous_compaction.id
            previous_first_kept_entry_id = previous_compaction.first_kept_entry_id
            first_kept_index = _find_entry_index(entries, previous_compaction.first_kept_entry_id)
            boundary_start = first_kept_index if first_kept_index is not None else previous_compaction_index + 1

    boundary_end = len(entries)
    context_messages = _visible_agent_messages(entries[boundary_start:boundary_end])
    if not context_messages:
        raise ValueError("Compaction requires at least one visible message entry.")

    tokens_before = estimate_context_tokens(context_messages).tokens
    cut_point = _find_cut_point(entries, boundary_start, boundary_end, keep_recent_tokens)
    first_kept_entry = entries[cut_point.first_kept_entry_index]
    first_kept_entry_id = first_kept_entry.id

    history_end = cut_point.turn_start_index if cut_point.is_split_turn else cut_point.first_kept_entry_index
    messages_to_summarize = _visible_agent_messages(entries[boundary_start:history_end])
    turn_prefix_messages = (
        _visible_agent_messages(entries[cut_point.turn_start_index : cut_point.first_kept_entry_index])
        if cut_point.is_split_turn
        else []
    )
    summarized_entry_ids = _visible_entry_ids(entries[boundary_start:history_end])
    turn_prefix_entry_ids = (
        _visible_entry_ids(entries[cut_point.turn_start_index : cut_point.first_kept_entry_index])
        if cut_point.is_split_turn
        else []
    )

    if not messages_to_summarize and not turn_prefix_messages:
        fallback_entries = [
            entry
            for index, entry in enumerate(entries[boundary_start:boundary_end], start=boundary_start)
            if index != cut_point.first_kept_entry_index
        ]
        messages_to_summarize = _visible_agent_messages(fallback_entries)
        summarized_entry_ids = _visible_entry_ids(fallback_entries)

    kept_entry_ids = _visible_entry_ids(entries[cut_point.first_kept_entry_index:boundary_end])
    plan = CompactionPlan(
        previous_compaction_id=previous_compaction_id,
        previous_first_kept_entry_id=previous_first_kept_entry_id,
        first_kept_entry_id=first_kept_entry_id,
        summarized_entry_ids=tuple(summarized_entry_ids),
        turn_prefix_entry_ids=tuple(turn_prefix_entry_ids),
        kept_entry_ids=tuple(kept_entry_ids),
        is_split_turn=cut_point.is_split_turn,
        tokens_before=tokens_before,
        keep_recent_tokens=keep_recent_tokens,
    )
    return _PreparedCompaction(
        plan=plan,
        messages_to_summarize=messages_to_summarize,
        turn_prefix_messages=turn_prefix_messages,
        previous_summary=previous_summary,
    )


def _latest_compaction_index(entries: list[SessionEntry]) -> int | None:
    for index in range(len(entries) - 1, -1, -1):
        if isinstance(entries[index], CompactionEntry):
            return index
    return None


def _find_entry_index(entries: list[SessionEntry], entry_id: str) -> int | None:
    for index, entry in enumerate(entries):
        if entry.id == entry_id:
            return index
    return None


def _visible_agent_messages(entries: Sequence[SessionEntry]) -> list[AgentMessage]:
    messages: list[AgentMessage] = []
    for entry in entries:
        message = _entry_to_agent_message(entry)
        if message is not None:
            messages.append(message)
    return messages


def _visible_entry_ids(entries: Sequence[SessionEntry]) -> list[str]:
    return [entry.id for entry in entries if _entry_to_agent_message(entry) is not None]


def _find_cut_point(
    entries: list[SessionEntry],
    start_index: int,
    end_index: int,
    keep_recent_tokens: int,
) -> _CutPointResult:
    cut_points = _find_valid_cut_points(entries, start_index, end_index)
    if not cut_points:
        return _CutPointResult(first_kept_entry_index=start_index, turn_start_index=-1, is_split_turn=False)

    accumulated_tokens = 0
    cut_index = cut_points[0]

    for index in range(end_index - 1, start_index - 1, -1):
        message = _entry_to_agent_message(entries[index])
        if message is None:
            continue
        accumulated_tokens += _estimate_message_tokens(message)
        if accumulated_tokens >= keep_recent_tokens:
            cut_index = cut_points[-1]
            for candidate in cut_points:
                if candidate >= index:
                    cut_index = candidate
                    break
            break

    while cut_index > start_index:
        previous_entry = entries[cut_index - 1]
        if isinstance(previous_entry, CompactionEntry):
            break
        if isinstance(previous_entry, SessionMessageEntry):
            break
        cut_index -= 1

    turn_start_index = -1 if _is_user_like_cut_entry(entries[cut_index]) else _find_turn_start_index(entries, cut_index, start_index)
    return _CutPointResult(
        first_kept_entry_index=cut_index,
        turn_start_index=turn_start_index,
        is_split_turn=turn_start_index != -1 and not _is_user_like_cut_entry(entries[cut_index]),
    )


def _find_valid_cut_points(entries: list[SessionEntry], start_index: int, end_index: int) -> list[int]:
    cut_points: list[int] = []
    for index in range(start_index, end_index):
        if _is_valid_cut_point(entries[index]):
            cut_points.append(index)
    return cut_points


def _is_valid_cut_point(entry: SessionEntry) -> bool:
    message = _entry_to_agent_message(entry)
    return message is not None and getattr(message, "role", None) != "toolResult"


def _is_user_like_cut_entry(entry: SessionEntry) -> bool:
    if isinstance(entry, BranchSummaryEntry | CustomMessageEntry):
        return True
    message = _entry_to_agent_message(entry)
    return getattr(message, "role", None) in {"user", "bashExecution"}


def _find_turn_start_index(entries: list[SessionEntry], entry_index: int, start_index: int) -> int:
    for index in range(entry_index, start_index - 1, -1):
        if _is_user_like_cut_entry(entries[index]):
            return index
    return -1


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


def _last_assistant_usage_info(messages: list[AgentMessage]) -> dict[str, object] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AssistantMessage) and message.stop_reason not in ("aborted", "error"):
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

    if isinstance(message, BashExecutionMessage):
        chars = len(message.command) + len(message.output)
        return (chars + 3) // 4

    if isinstance(message, CustomMessage):
        if isinstance(message.content, str):
            chars = len(message.content)
        else:
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    chars += len(block.text)
                elif getattr(block, "type", None) == "image":
                    chars += 4_800
        return (chars + 3) // 4

    if isinstance(message, BranchSummaryMessage | CompactionSummaryMessage):
        return (len(message.summary) + 3) // 4

    return 0


def _entry_to_agent_message(entry: SessionEntry) -> AgentMessage | None:
    if isinstance(entry, SessionMessageEntry):
        return entry.message
    if isinstance(entry, CustomMessageEntry):
        return create_custom_message(
            custom_type=entry.custom_type,
            content=entry.content,
            display=entry.display,
            details=entry.details,
            timestamp=entry.timestamp,
        )
    if isinstance(entry, BranchSummaryEntry):
        return create_branch_summary_message(
            summary=entry.summary,
            from_id=entry.from_id,
            timestamp=entry.timestamp,
        )
    return None


async def _summarize_messages(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
) -> str:
    prompt = _build_summarization_prompt(
        messages=preparation.messages_to_summarize,
        base_prompt=UPDATE_SUMMARIZATION_PROMPT if preparation.previous_summary else SUMMARIZATION_PROMPT,
        previous_summary=preparation.previous_summary,
        custom_instructions=custom_instructions,
    )
    context = Context(
        system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
        messages=[
            UserMessage(
                role="user",
                content=[TextPart(type="text", text=prompt)],
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
    prompt = _build_summarization_prompt(
        messages=messages,
        base_prompt=TURN_PREFIX_SUMMARIZATION_PROMPT,
        previous_summary=None,
        custom_instructions=None,
    )
    return await _complete_text(
        model,
        Context(
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
            messages=[
                UserMessage(
                    role="user",
                    content=[TextPart(type="text", text=prompt)],
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
    prompt = base_prompt
    if custom_instructions:
        prompt = f"{prompt}\n\nAdditional focus: {custom_instructions}"

    conversation = _serialize_conversation(convert_to_llm(messages))
    prompt_text = f"<conversation>\n{conversation}\n</conversation>\n\n"
    if previous_summary:
        prompt_text += f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
    return f"{prompt_text}{prompt}"


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


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.text) for block in content if getattr(block, "type", None) == "text")
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


def _collect_file_operation_details(messages: list[AgentMessage]) -> dict[str, list[str]]:
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
        sections.append("<modified-files>\n" + "\n".join(modified_files) + "\n</modified-files>")
    if not sections:
        return ""
    return "\n\n" + "\n\n".join(sections)


def _merge_compaction_details(existing: object | None, file_details: dict[str, list[str]]) -> object | None:
    if not file_details["readFiles"] and not file_details["modifiedFiles"]:
        return existing
    if isinstance(existing, Mapping):
        merged = dict(existing)
        merged.update(file_details)
        return merged
    return file_details

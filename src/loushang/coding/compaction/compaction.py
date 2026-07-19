from __future__ import annotations

from collections.abc import Mapping, Sequence

from loushang.agent import AgentMessage
from loushang.ai import ApiKeyAuth, CallOptions, Context, complete
from loushang.ai.types import AssistantMessage, TextPart, UserMessage
from loushang.coding.compaction.profiles import (
    CODING_COMPACTION_SUMMARY_PROFILE,
    CODING_TURN_PREFIX_SUMMARY_PROFILE,
)
from loushang.harness.agent_transcript import (
    CompactionPreparation,
    CompactionResult,
    context_item_to_model_message,
)
from loushang.harness.context.summary import (
    build_summary_prompt,
    compose_summary_prompt,
)

TOOL_RESULT_MAX_CHARS = 2_000


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


async def compact(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str | None = None,
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


async def _summarize_messages(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str | None,
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
            auth=ApiKeyAuth(api_key) if api_key else None,
            headers=dict(headers or {}),
            cancellation=signal,
        ),
    )


async def _summarize_turn_prefix(
    *,
    messages: list[AgentMessage],
    model: object,
    api_key: str | None,
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
            auth=ApiKeyAuth(api_key) if api_key else None,
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

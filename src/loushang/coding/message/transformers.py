from __future__ import annotations

from datetime import datetime

from loushang.agent import AgentMessage
from loushang.ai.types import AssistantMessage, Message, TextPart, ToolResultMessage, UserMessage
from loushang.coding.message.custom_messages import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    ContentBlock,
    CustomMessage,
)


COMPACTION_SUMMARY_PREFIX = """The conversation history before this point was compacted into the following summary:

<summary>
"""

COMPACTION_SUMMARY_SUFFIX = """
</summary>"""

BRANCH_SUMMARY_PREFIX = """The following is a summary of a branch that this conversation came back from:

<summary>
"""

BRANCH_SUMMARY_SUFFIX = "</summary>"


def _timestamp_from_iso(timestamp: str) -> float:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()


def _user_message(content: list[ContentBlock], timestamp: float) -> UserMessage:
    return UserMessage(role="user", content=content, timestamp=timestamp)


def bash_execution_to_text(message: BashExecutionMessage) -> str:
    text = f"Ran `{message.command}`\n"
    if message.output:
        text += f"```\n{message.output}\n```"
    else:
        text += "(no output)"
    if message.cancelled:
        text += "\n\n(command cancelled)"
    elif message.exit_code not in (None, 0):
        text += f"\n\nCommand exited with code {message.exit_code}"
    if message.truncated and message.full_output_path:
        text += f"\n\n[Output truncated. Full output: {message.full_output_path}]"
    return text


def create_branch_summary_message(summary: str, from_id: str, timestamp: str) -> BranchSummaryMessage:
    return BranchSummaryMessage(
        role="branchSummary",
        summary=summary,
        from_id=from_id,
        timestamp=_timestamp_from_iso(timestamp),
    )


def create_compaction_summary_message(summary: str, tokens_before: int, timestamp: str) -> CompactionSummaryMessage:
    return CompactionSummaryMessage(
        role="compactionSummary",
        summary=summary,
        tokens_before=tokens_before,
        timestamp=_timestamp_from_iso(timestamp),
    )


def create_custom_message(
    custom_type: str,
    content: str | list[ContentBlock],
    display: bool,
    details: object | None,
    timestamp: str,
) -> CustomMessage:
    return CustomMessage(
        role="custom",
        custom_type=custom_type,
        content=content,
        display=display,
        details=details,
        timestamp=_timestamp_from_iso(timestamp),
    )


def convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    result: list[Message] = []

    for message in messages:
        if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
            result.append(message)
            continue
        if isinstance(message, BashExecutionMessage):
            if message.exclude_from_context:
                continue
            result.append(
                _user_message(
                    [TextPart(type="text", text=bash_execution_to_text(message))],
                    message.timestamp,
                )
            )
            continue
        if isinstance(message, CustomMessage):
            content = message.content
            blocks = [TextPart(type="text", text=content)] if isinstance(content, str) else content
            result.append(_user_message(blocks, message.timestamp))
            continue
        if isinstance(message, BranchSummaryMessage):
            result.append(
                _user_message(
                    [TextPart(type="text", text=BRANCH_SUMMARY_PREFIX + message.summary + BRANCH_SUMMARY_SUFFIX)],
                    message.timestamp,
                )
            )
            continue
        if isinstance(message, CompactionSummaryMessage):
            result.append(
                _user_message(
                    [TextPart(type="text", text=COMPACTION_SUMMARY_PREFIX + message.summary + COMPACTION_SUMMARY_SUFFIX)],
                    message.timestamp,
                )
            )

    return result

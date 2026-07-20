"""Coding bindings for the standard Agent transcript summary runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from loushang.agent import AgentMessage
from loushang.ai.types import AssistantMessage
from loushang.coding.compaction.profiles import (
    CODING_BRANCH_SUMMARY_PROFILE,
    CODING_COMPACTION_SUMMARY_PROFILE,
    CODING_TURN_PREFIX_SUMMARY_PROFILE,
)
from loushang.harness.agent_transcript import (
    BranchSummaryOutput,
    CompactionPreparation,
    CompactionResult,
)
from loushang.harness.agent_transcript.summarization import (
    SummaryCompleter,
    SummaryDecoration,
    default_summary_completer,
    execute_branch_summary,
    execute_transcript_compaction,
)
from loushang.protocol import JSONValue


async def execute_coding_compaction(
    *,
    preparation: CompactionPreparation,
    model: object,
    api_key: str | None = None,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
    completer: SummaryCompleter = default_summary_completer,
) -> CompactionResult:
    """Bind Coding prompts and file-operation annotations to Harness compaction."""

    return await execute_transcript_compaction(
        preparation=preparation,
        model=model,
        compaction_profile=CODING_COMPACTION_SUMMARY_PROFILE,
        turn_prefix_profile=CODING_TURN_PREFIX_SUMMARY_PROFILE,
        api_key=api_key,
        headers=headers,
        signal=signal,
        custom_instructions=custom_instructions,
        completer=completer,
        decorate=_coding_summary_decoration,
    )


async def execute_coding_branch_summary(
    entries_or_messages: Sequence[object],
    *,
    model: object,
    api_key: str | None = None,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
    replace_instructions: bool = False,
    reserve_tokens: int = 16_384,
    completer: SummaryCompleter = default_summary_completer,
) -> BranchSummaryOutput:
    """Bind Coding prompts and file-operation annotations to branch summaries."""

    return await execute_branch_summary(
        entries_or_messages,
        model=model,
        profile=CODING_BRANCH_SUMMARY_PROFILE,
        api_key=api_key,
        headers=headers,
        signal=signal,
        custom_instructions=custom_instructions,
        replace_instructions=replace_instructions,
        reserve_tokens=reserve_tokens,
        completer=completer,
        decorate=_coding_summary_decoration,
    )


def _coding_summary_decoration(
    messages: Sequence[AgentMessage],
    existing_details: JSONValue,
) -> SummaryDecoration:
    file_details = _collect_file_operation_details(messages)
    return SummaryDecoration(
        suffix=_format_file_operations(file_details),
        details=_merge_summary_details(existing_details, file_details),
    )


def _collect_file_operation_details(
    messages: Sequence[AgentMessage],
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


def _format_file_operations(details: Mapping[str, Sequence[str]]) -> str:
    sections: list[str] = []
    read_files = details["readFiles"]
    modified_files = details["modifiedFiles"]
    if read_files:
        sections.append("<read-files>\n" + "\n".join(read_files) + "\n</read-files>")
    if modified_files:
        sections.append(
            "<modified-files>\n" + "\n".join(modified_files) + "\n</modified-files>"
        )
    return "" if not sections else "\n\n" + "\n\n".join(sections)


def _merge_summary_details(
    existing: JSONValue,
    file_details: dict[str, list[str]],
) -> JSONValue:
    if not file_details["readFiles"] and not file_details["modifiedFiles"]:
        return existing
    if isinstance(existing, Mapping):
        return {**existing, **file_details}
    return file_details


__all__ = ["execute_coding_branch_summary", "execute_coding_compaction"]

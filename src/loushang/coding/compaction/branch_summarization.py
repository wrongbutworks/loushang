from __future__ import annotations

from collections.abc import Mapping, Sequence

from loushang.agent import AgentMessage
from loushang.ai import Context, complete_simple
from loushang.ai.types import TextPart, UserMessage
from loushang.coding.compaction.compaction import (
    SUMMARIZATION_SYSTEM_PROMPT,
    _build_summarization_prompt,
    _collect_file_operation_details,
    _entry_to_agent_message,
    _estimate_message_tokens,
    _format_file_operations,
)
from loushang.coding.compaction.types import (
    BranchPreparation,
    BranchSummaryDetails,
    BranchSummaryResult,
    CollectEntriesResult,
)
from loushang.coding.store import SessionManager

BRANCH_SUMMARY_PREAMBLE = """The user explored a different conversation branch before returning here.
Summary of that exploration:

"""

BRANCH_SUMMARY_PROMPT = """Create a structured summary of this conversation branch for context when returning later.

Use this EXACT format:

## Goal
[What was the user trying to accomplish in this branch?]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Work that was started but not finished]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [What should happen next to continue this work]

Keep each section concise. Preserve exact file paths, function names, and error messages."""


def collect_entries_for_branch_summary(
    session: SessionManager,
    old_leaf_id: str | None,
    target_id: str,
) -> CollectEntriesResult:
    if old_leaf_id is None:
        return CollectEntriesResult(entries=[], common_ancestor_id=None)

    old_path_ids = {entry.id for entry in session.get_branch(old_leaf_id)}
    target_path = session.get_branch(target_id)

    common_ancestor_id: str | None = None
    for entry in reversed(target_path):
        if entry.id in old_path_ids:
            common_ancestor_id = entry.id
            break

    entries = []
    current_id = old_leaf_id
    while current_id is not None and current_id != common_ancestor_id:
        entry = session.get_entry(current_id)
        if entry is None:
            break
        entries.append(entry)
        current_id = entry.parent_id
    entries.reverse()
    return CollectEntriesResult(entries=entries, common_ancestor_id=common_ancestor_id)


def prepare_branch_entries(entries: list[object], token_budget: int = 0) -> BranchPreparation:
    prepared_messages = []
    prepared_entry_ids = []
    total_tokens = 0

    for entry in reversed(entries):
        message = _entry_to_agent_message(entry)
        if message is None:
            continue
        tokens = _estimate_message_tokens(message)
        if token_budget > 0 and prepared_messages and total_tokens + tokens > token_budget:
            break
        prepared_messages.insert(0, message)
        prepared_entry_ids.insert(0, entry.id)
        total_tokens += tokens

    if not prepared_messages and entries:
        last_entry = entries[-1]
        last_message = _entry_to_agent_message(last_entry)
        if last_message is not None:
            prepared_messages = [last_message]
            prepared_entry_ids = [last_entry.id]
            total_tokens = _estimate_message_tokens(last_message)

    return BranchPreparation(
        messages=prepared_messages,
        entry_ids=prepared_entry_ids,
        total_tokens=total_tokens,
    )


async def generate_branch_summary(
    entries_or_messages: Sequence[object],
    *,
    model: object,
    api_key: str,
    headers: Mapping[str, str] | None = None,
    signal: object | None = None,
    custom_instructions: str | None = None,
    replace_instructions: bool = False,
    reserve_tokens: int = 16_384,
) -> BranchSummaryResult:
    del api_key, headers

    if _is_aborted(signal):
        return BranchSummaryResult(aborted=True)

    try:
        messages = _normalize_branch_summary_messages(entries_or_messages, reserve_tokens)
        if not messages:
            return BranchSummaryResult(summary="No content to summarize")
        prompt = _branch_summary_prompt(
            messages=messages,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
        )
        summary = await complete_simple(
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
        )
        if _is_aborted(signal):
            return BranchSummaryResult(aborted=True)
        file_details = _collect_file_operation_details(messages)
        summary = f"{BRANCH_SUMMARY_PREAMBLE}{summary or 'No summary generated'}{_format_file_operations(file_details)}"
        return BranchSummaryResult(
            summary=summary,
            details=BranchSummaryDetails(
                read_files=file_details["readFiles"],
                modified_files=file_details["modifiedFiles"],
            ),
        )
    except Exception as exc:
        return BranchSummaryResult(error=str(exc))


def _normalize_branch_summary_messages(
    entries_or_messages: Sequence[object],
    reserve_tokens: int,
) -> list[AgentMessage]:
    if not entries_or_messages:
        return []
    if all(hasattr(item, "role") for item in entries_or_messages):
        return list(entries_or_messages)  # type: ignore[return-value]
    token_budget = max(reserve_tokens, 0)
    return prepare_branch_entries(list(entries_or_messages), token_budget=token_budget).messages


def _branch_summary_prompt(
    *,
    messages: list[AgentMessage],
    custom_instructions: str | None,
    replace_instructions: bool,
) -> str:
    if custom_instructions and replace_instructions:
        base_prompt = custom_instructions
    elif custom_instructions:
        base_prompt = f"{BRANCH_SUMMARY_PROMPT}\n\nAdditional focus: {custom_instructions}"
    else:
        base_prompt = BRANCH_SUMMARY_PROMPT
    return _build_summarization_prompt(
        messages=messages,
        base_prompt=base_prompt,
        previous_summary=None,
        custom_instructions=None,
    )


def _is_aborted(signal: object | None) -> bool:
    return bool(signal is not None and getattr(signal, "aborted", False))

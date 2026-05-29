from __future__ import annotations

from loushang.coding.message import CompactionEntry, CustomMessageEntry


def test_custom_message_entry_projects_to_runtime_custom_message() -> None:
    from loushang.coding.message import create_custom_message

    entry = CustomMessageEntry(
        type="custom_message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        custom_type="review_note",
        content="ready",
        details={"severity": "info"},
        display=True,
    )

    message = create_custom_message(
        custom_type=entry.custom_type,
        content=entry.content,
        display=entry.display,
        details=entry.details,
        timestamp=entry.timestamp,
    )

    assert message.role == "custom"
    assert message.custom_type == "review_note"


def test_compaction_entry_projects_to_summary_message() -> None:
    from loushang.coding.message import create_compaction_summary_message

    entry = CompactionEntry(
        type="compaction",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:01:00.000Z",
        summary="compact summary",
        first_kept_entry_id="e1",
        tokens_before=42,
        details=None,
        from_hook=False,
    )

    message = create_compaction_summary_message(entry.summary, entry.tokens_before, entry.timestamp)
    assert message.role == "compactionSummary"


def test_convert_to_llm_turns_branch_summary_into_user_message() -> None:
    from loushang.coding.message import BranchSummaryMessage, convert_to_llm

    result = convert_to_llm(
        [BranchSummaryMessage(role="branchSummary", summary="done", from_id="b1", timestamp=0.0)]
    )

    assert len(result) == 1
    assert result[0].role == "user"


def test_convert_to_llm_skips_bash_execution_marked_excluded() -> None:
    from loushang.coding.message import BashExecutionMessage, convert_to_llm

    result = convert_to_llm(
        [
            BashExecutionMessage(
                role="bashExecution",
                command="ls",
                output="a\nb",
                exit_code=0,
                cancelled=False,
                truncated=False,
                full_output_path=None,
                timestamp=0.0,
                exclude_from_context=True,
            )
        ]
    )

    assert result == []

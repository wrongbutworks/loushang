from __future__ import annotations

from loushang.ai.types import TextPart, UserMessage
from loushang.coding.store import SessionManager


def test_collect_entries_for_branch_summary_returns_entries_from_old_leaf(tmp_path) -> None:
    from loushang.coding.compaction import collect_entries_for_branch_summary

    session = SessionManager.new(session_dir=tmp_path, cwd=str(tmp_path), persist=False)
    root_id = session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=1.0,
        )
    )
    branch_a_id = session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="branch-a")],
            timestamp=2.0,
        )
    )

    session.branch(root_id)
    branch_b_id = session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="branch-b")],
            timestamp=3.0,
        )
    )

    result = collect_entries_for_branch_summary(session, old_leaf_id=branch_a_id, target_id=branch_b_id)

    assert [entry.record_id for entry in result.entries] == [branch_a_id]
    assert result.common_ancestor_id == root_id


def test_prepare_branch_entries_keeps_recent_messages_within_token_budget(tmp_path) -> None:
    from loushang.coding.compaction import prepare_branch_entries

    session = SessionManager.new(session_dir=tmp_path, cwd=str(tmp_path), persist=False)
    session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="older branch message that should be dropped first")],
            timestamp=1.0,
        )
    )
    latest_id = session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="latest branch message")],
            timestamp=2.0,
        )
    )

    preparation = prepare_branch_entries(session.get_branch(), token_budget=8)

    assert len(preparation.messages) == 1
    assert preparation.messages[0].role == "user"
    assert "latest branch message" in preparation.messages[0].content[0].text
    assert preparation.entry_ids == [latest_id]
    assert preparation.total_tokens > 0

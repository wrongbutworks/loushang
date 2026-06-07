from __future__ import annotations

from loushang.ai.types import TextPart, UserMessage


def test_coding_public_imports_smoke() -> None:
    from loushang.coding.event import AgentSessionEvent
    from loushang.coding.message import SessionEntry, SessionHeader
    from loushang.coding.store import SessionManager

    assert SessionHeader is not None
    assert SessionEntry is not None
    assert SessionManager is not None
    assert AgentSessionEvent is not None


def test_session_message_entry_accepts_agent_message() -> None:
    from loushang.coding.message import SessionMessageEntry

    message = UserMessage(
        role="user",
        content=[TextPart(type="text", text="hi")],
        timestamp=0.0,
    )
    entry = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        message=message,
    )

    assert entry.type == "message"
    assert entry.message is message


def test_session_entry_union_includes_compaction_and_custom_message_entries() -> None:
    from loushang.coding.message import (
        CompactionEntry,
        CustomMessageEntry,
        SessionEntry,
    )

    compaction: SessionEntry = CompactionEntry(
        type="compaction",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:01:00.000Z",
        summary="summary",
        first_kept_entry_id="e1",
        tokens_before=100,
        details=None,
        from_hook=False,
    )
    custom_message: SessionEntry = CustomMessageEntry(
        type="custom_message",
        id="e3",
        parent_id="e2",
        timestamp="2026-05-20T09:02:00.000Z",
        custom_type="review_note",
        content="ready",
        details=None,
        display=True,
    )

    assert compaction.type == "compaction"
    assert custom_message.type == "custom_message"

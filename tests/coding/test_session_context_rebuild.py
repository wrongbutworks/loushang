from __future__ import annotations

from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.coding.message import (
    CompactionEntry,
    CustomMessageEntry,
    ModelChangeEntry,
    SessionMessageEntry,
    ThinkingLevelChangeEntry,
)


def test_build_session_context_projects_custom_and_compaction_entries(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    first = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="hi")],
            timestamp=0.0,
        )
    )
    manager.append_compaction("summary", first, 100)

    context = manager.build_session_context()

    assert len(context.messages) == 2
    assert context.messages[0].role == "compactionSummary"
    assert context.messages[1].role == "user"


def test_build_session_context_uses_leaf_branch_only() -> None:
    from loushang.coding.store.session_manager import build_session_context

    e1 = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        message=UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        ),
    )
    e2 = CustomMessageEntry(
        type="custom_message",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:00:01.000Z",
        custom_type="branch_a",
        content="A",
        details=None,
        display=True,
    )
    e3 = CustomMessageEntry(
        type="custom_message",
        id="e3",
        parent_id="e1",
        timestamp="2026-05-20T09:00:02.000Z",
        custom_type="branch_b",
        content="B",
        details=None,
        display=True,
    )

    context = build_session_context([e1, e2, e3], leaf_id="e2")

    assert len(context.messages) == 2
    assert context.messages[0].role == "user"
    assert context.messages[1].role == "custom"
    assert context.messages[1].content == "A"


def test_build_session_context_recovers_thinking_level_and_model() -> None:
    from loushang.coding.store.session_manager import build_session_context

    e1 = ThinkingLevelChangeEntry(
        type="thinking_level_change",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        thinking_level="high",
    )
    e2 = ModelChangeEntry(
        type="model_change",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:00:01.000Z",
        provider="openai",
        model_id="gpt-5.4",
    )

    context = build_session_context([e1, e2], leaf_id="e2")

    assert context.thinking_level == "high"
    assert context.model == {"provider": "openai", "model_id": "gpt-5.4"}


def test_build_session_context_uses_latest_compaction_summary_only(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    first_user_id = manager.append_message(
        UserMessage(role="user", content=[TextPart(type="text", text="first")], timestamp=1.0)
    )
    manager.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="first answer")],
            api="responses",
            provider="faux",
            model="alpha",
            response_id="r1",
            usage=Usage(input=1, output=1, cache_read=0, cache_write=0, total_tokens=2, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=2.0,
        )
    )
    manager.append_compaction("old summary", first_user_id, 100)
    second_user_id = manager.append_message(
        UserMessage(role="user", content=[TextPart(type="text", text="second")], timestamp=3.0)
    )
    manager.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="second answer")],
            api="responses",
            provider="faux",
            model="alpha",
            response_id="r2",
            usage=Usage(input=2, output=1, cache_read=0, cache_write=0, total_tokens=3, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=4.0,
        )
    )
    manager.append_compaction("new summary", second_user_id, 200)
    manager.append_message(UserMessage(role="user", content=[TextPart(type="text", text="after")], timestamp=5.0))

    context = manager.build_session_context()

    assert [getattr(message, "role", None) for message in context.messages] == [
        "compactionSummary",
        "user",
        "assistant",
        "user",
    ]
    assert context.messages[0].summary == "new summary"  # type: ignore[attr-defined]
    assert all(getattr(message, "summary", None) != "old summary" for message in context.messages)
    assert "first answer" not in _context_text(context.messages)
    assert "second answer" in _context_text(context.messages)


def test_latest_compaction_skips_superseded_malformed_history() -> None:
    from loushang.coding.store.session_manager import build_session_context

    malformed_custom = CustomMessageEntry(
        type="custom_message",
        id="old-custom",
        parent_id=None,
        timestamp="not-an-iso-timestamp",
        custom_type="legacy",
        content="superseded",
        display=True,
    )
    model_change = ModelChangeEntry(
        type="model_change",
        id="model",
        parent_id="old-custom",
        timestamp="2026-05-20T09:00:00.000Z",
        provider="openai",
        model_id="gpt-5.4",
    )
    old_message = SessionMessageEntry(
        type="message",
        id="old-message",
        parent_id="model",
        timestamp="2026-05-20T09:00:01.000Z",
        message=UserMessage(role="user", content="old", timestamp=1.0),
    )
    malformed_checkpoint = CompactionEntry(
        type="compaction",
        id="old-checkpoint",
        parent_id="old-message",
        timestamp="also-not-an-iso-timestamp",
        summary="superseded summary",
        first_kept_entry_id="old-message",
        tokens_before=10,
    )
    kept_message = SessionMessageEntry(
        type="message",
        id="kept-message",
        parent_id="old-checkpoint",
        timestamp="2026-05-20T09:00:02.000Z",
        message=UserMessage(role="user", content="kept", timestamp=2.0),
    )
    latest_checkpoint = CompactionEntry(
        type="compaction",
        id="latest-checkpoint",
        parent_id="kept-message",
        timestamp="2026-05-20T09:00:03.000Z",
        summary="current summary",
        first_kept_entry_id="kept-message",
        tokens_before=20,
    )
    tail_message = SessionMessageEntry(
        type="message",
        id="tail-message",
        parent_id="latest-checkpoint",
        timestamp="2026-05-20T09:00:04.000Z",
        message=UserMessage(role="user", content="tail", timestamp=3.0),
    )

    context = build_session_context(
        [
            malformed_custom,
            model_change,
            old_message,
            malformed_checkpoint,
            kept_message,
            latest_checkpoint,
            tail_message,
        ],
        leaf_id="tail-message",
    )

    assert [message.role for message in context.messages] == [
        "compactionSummary",
        "user",
        "user",
    ]
    assert context.messages[0].summary == "current summary"  # type: ignore[attr-defined]
    assert context.messages[1].content == "kept"  # type: ignore[union-attr]
    assert context.messages[2].content == "tail"  # type: ignore[union-attr]
    assert context.model == {"provider": "openai", "model_id": "gpt-5.4"}


def test_build_session_context_preserves_state_across_compaction() -> None:
    from loushang.coding.store.session_manager import build_session_context

    e1 = ThinkingLevelChangeEntry(
        type="thinking_level_change",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        thinking_level="high",
    )
    e2 = ModelChangeEntry(
        type="model_change",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:00:01.000Z",
        provider="openai",
        model_id="gpt-5.4",
    )
    e3 = SessionMessageEntry(
        type="message",
        id="e3",
        parent_id="e2",
        timestamp="2026-05-20T09:00:02.000Z",
        message=UserMessage(role="user", content=[TextPart(type="text", text="kept")], timestamp=1.0),
    )
    e4 = CompactionEntry(
        type="compaction",
        id="e4",
        parent_id="e3",
        timestamp="2026-05-20T09:00:03.000Z",
        summary="summary",
        first_kept_entry_id="e3",
        tokens_before=50,
    )

    context = build_session_context([e1, e2, e3, e4], leaf_id="e4")

    assert context.thinking_level == "high"
    assert context.model == {"provider": "openai", "model_id": "gpt-5.4"}
    assert [getattr(message, "role", None) for message in context.messages] == ["compactionSummary", "user"]


def _context_text(messages: list[object]) -> str:
    text: list[str] = []
    for message in messages:
        for block in getattr(message, "content", []):
            if getattr(block, "type", None) == "text":
                text.append(block.text)
    return "\n".join(text)


def test_build_session_context_explicit_none_leaf_means_before_first_entry() -> None:
    from loushang.coding.store.session_manager import build_session_context

    e1 = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        message=UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        ),
    )

    context = build_session_context([e1], leaf_id=None)

    assert context.messages == []
    assert context.thinking_level == "off"
    assert context.model is None


def test_build_session_context_unknown_leaf_preserves_empty_context_compatibility() -> None:
    from loushang.coding.store.session_manager import build_session_context

    entry = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:00.000Z",
        message=UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        ),
    )

    context = build_session_context([entry], leaf_id="missing")

    assert context == type(context)()


def test_build_session_context_recovers_blank_compaction_boundary(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(tmp_path, cwd=str(tmp_path), persist=False)
    manager.append_message(UserMessage(role="user", content="old", timestamp=1.0))
    manager.append_compaction("recovered summary", "", 10)
    manager.append_message(UserMessage(role="user", content="after", timestamp=2.0))

    context = manager.build_session_context()

    assert [message.role for message in context.messages] == [
        "compactionSummary",
        "user",
    ]
    assert context.messages[0].summary == "recovered summary"  # type: ignore[attr-defined]
    assert context.messages[1].content == "after"  # type: ignore[union-attr]

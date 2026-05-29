from __future__ import annotations

import asyncio


class _Session:
    def __init__(self) -> None:
        self.steering = ["steer"]
        self.follow_up = ["follow"]

    def get_steering_messages(self):
        return list(self.steering)

    def get_follow_up_messages(self):
        return list(self.follow_up)


def test_pending_queue_view_maps_session_queues_to_generic_tui_sections() -> None:
    from loushang.coding.ui.pending_queue import pending_queue_view

    view = pending_queue_view(_Session())

    assert [(section.label, tuple(section.items), section.hint) for section in view.sections] == [
        (
            "Messages to be submitted after next tool call",
            ("steer",),
            "press esc to interrupt and send immediately",
        ),
        ("Messages to be submitted at end of turn", ("follow",), None),
    ]


def test_cleared_queue_messages_supports_follow_up_aliases_and_stringifies_values() -> None:
    from loushang.coding.ui.pending_queue import cleared_queue_messages

    assert cleared_queue_messages({"steering": [1], "follow_up": ["next"]}) == ["1", "next"]
    assert cleared_queue_messages({"steering": ["steer"], "followUp": [2]}) == ["steer", "2"]


def test_session_pending_messages_is_defensive() -> None:
    from loushang.coding.ui.pending_queue import session_pending_messages

    assert session_pending_messages(object(), "missing") == []

    class Broken:
        def messages(self):
            raise RuntimeError("boom")

    assert session_pending_messages(Broken(), "messages") == []


def test_restore_queued_messages_merges_cleared_queue_and_current_text() -> None:
    from loushang.coding.ui.pending_queue import restore_queued_messages

    class Session:
        def clear_queue(self):
            return {"steering": ["steer one"], "follow_up": ["follow one"]}

    restored = asyncio.run(restore_queued_messages(Session(), "draft"))

    assert restored == "steer one\n\nfollow one\n\ndraft"


def test_restore_queued_messages_supports_awaitable_clear_queue_and_traces() -> None:
    from loushang.coding.ui.pending_queue import restore_queued_messages

    traces: list[tuple[str, dict[str, object]]] = []

    class Session:
        async def clear_queue(self):
            return {"steering": ["steer"]}

    restored = asyncio.run(
        restore_queued_messages(
            Session(),
            "   ",
            trace=lambda name, **data: traces.append((name, data)),
        )
    )

    assert restored == "steer"
    assert traces == [("queue.dequeued", {"count": 1, "current_text_len": 3})]


def test_restore_queued_messages_returns_none_when_unavailable_or_empty() -> None:
    from loushang.coding.ui.pending_queue import restore_queued_messages

    traces: list[str] = []

    assert asyncio.run(restore_queued_messages(object(), "", trace=lambda name, **_data: traces.append(name))) is None

    class EmptySession:
        def clear_queue(self):
            return {"steering": []}

    assert asyncio.run(restore_queued_messages(EmptySession(), "", trace=lambda name, **_data: traces.append(name))) is None
    assert traces == ["queue.dequeue.unavailable", "queue.dequeue.empty"]

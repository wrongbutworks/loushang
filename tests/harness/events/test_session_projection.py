from __future__ import annotations

from loushang.harness.events.session_projection import (
    project_session_event,
    shape_stream_event,
)


def test_shared_projection_accepts_neutral_session_event_mapping() -> None:
    event = {
        "type": "queue_update",
        "steering": ["steer"],
        "follow_up": ["follow"],
    }

    assert project_session_event(event, event_view="full") == [event]


def test_shared_stream_shape_normalizes_external_keys_to_snake_case() -> None:
    shaped = shape_stream_event(
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
        },
        event_view="full",
    )

    assert shaped["tool_call_id"] == "call-1"
    assert shaped["event_type"] == "tool_execution_start"
    assert shaped["correlation_id"] == "call-1"
    assert shaped["stream"] == {
        "kind": "session_event",
        "view": "full",
        "correlation_id": "call-1",
    }

from loushang.coding.event.projection import (
    SUPPORTED_JSON_EVENT_VIEWS,
    JsonEventView,
    project_session_event,
    select_events,
    shape_stream_event,
    should_emit_projected_event,
)
from loushang.coding.event.runtime_view import (
    project_runtime_event_to_json_views,
    shape_runtime_event_view,
    should_emit_runtime_event_view,
)
from loushang.coding.event.types import AgentSessionEvent
from loushang.harness.events import project_session_runtime_event
from loushang.harness.events.session_serialization import serialize_session_event

__all__ = [
    "AgentSessionEvent",
    "JsonEventView",
    "SUPPORTED_JSON_EVENT_VIEWS",
    "project_session_event",
    "project_runtime_event_to_session_event",
    "project_runtime_event_to_json_views",
    "select_events",
    "serialize_session_event",
    "shape_stream_event",
    "shape_runtime_event_view",
    "should_emit_projected_event",
    "should_emit_runtime_event_view",
]

# Temporary source-level alias while Coding consumers move to the standard
# Harness projection name. The implementation is owned by Harness.
project_runtime_event_to_session_event = project_session_runtime_event

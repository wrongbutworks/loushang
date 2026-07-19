"""Coding's adapter from common runtime facts to its JSON event views."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from loushang.coding.event.projection import (
    JsonEventView,
    _event_correlation_id,
    _expand_patterns,
    project_session_event,
)
from loushang.coding.event.runtime_projection import (
    project_runtime_event_to_session_event,
)
from loushang.harness.events import (
    RuntimeEvent,
    RuntimeEventDeliveryHint,
    RuntimeEventView,
    matches_event_select,
    project_runtime_event,
)
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime


def project_runtime_event_to_json_views(
    event: RuntimeEvent[object],
    *,
    event_view: JsonEventView,
    tool_render_runtime: ToolRenderRuntime | None = None,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    tool_render_expanded: bool = False,
) -> tuple[RuntimeEventView, ...]:
    """Project one common runtime fact into Coding's selected JSON view.

    Coding remains responsible for Pi event names, aliases, and tool-render
    enrichment.  Harness owns the resulting transport-safe envelope.
    """

    session_event = project_runtime_event_to_session_event(event)
    if session_event is None:
        return ()
    views: list[RuntimeEventView] = []
    for payload in project_session_event(
        session_event,
        event_view=event_view,
        tool_render_runtime=tool_render_runtime,
        tool_definition_resolver=tool_definition_resolver,
        tool_render_expanded=tool_render_expanded,
    ):
        event_type = payload.get("type")
        if not isinstance(event_type, str):
            continue
        views.append(
            project_runtime_event(
                event,
                event_type=event_type,
                view=event_view,
                payload=payload,
                delivery_hint=_delivery_hint(event_type),
                correlation_id=_event_correlation_id(payload),
            )
        )
    return tuple(views)


def should_emit_runtime_event_view(
    view: RuntimeEventView,
    event_select: Sequence[str],
) -> bool:
    """Apply Coding aliases before Harness matches generic selector patterns."""

    return matches_event_select(view.event_type, _expand_patterns(event_select))


def shape_runtime_event_view(view: RuntimeEventView) -> dict[str, Any]:
    """Retain Coding's existing RPC stream shape for one projected view."""

    payload = dict(view.payload)
    payload.setdefault("type", view.event_type)
    payload.setdefault("eventType", view.event_type)
    stream: dict[str, Any] = {
        "kind": "session_event",
        "view": view.view,
    }
    if view.correlation_id is not None:
        payload["correlationId"] = view.correlation_id
        stream["correlationId"] = view.correlation_id
    payload["stream"] = stream
    return payload


def _delivery_hint(event_type: str) -> RuntimeEventDeliveryHint:
    if event_type in {"assistant_delta", "tool_execution_update"}:
        return "coalesce"
    return "immediate"


__all__ = [
    "project_runtime_event_to_json_views",
    "shape_runtime_event_view",
    "should_emit_runtime_event_view",
]

"""Coding's product binding for the shared Harness RPC host.

The JSONL loop, session operation handlers, model/state utilities, extension
UI lifecycle, and response serialization live in :mod:`loushang.harness.host`.
Coding supplies only its event projection and keeps this import surface while
callers migrate to the shared host contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TextIO

from loushang.coding.diagnostics.serialization import (
    serialize_diagnostic,
    serialize_diagnostic_summary,
    serialize_error_report,
)
from loushang.coding.event import (
    SUPPORTED_JSON_EVENT_VIEWS,
    project_runtime_event_to_json_views,
    project_session_event,
    shape_runtime_event_view,
    shape_stream_event,
    should_emit_projected_event,
    should_emit_runtime_event_view,
)
from loushang.harness.events import normalize_event_select
from loushang.harness.host.rpc import (
    RpcDiagnosticsProjection,
    RpcEventProjection,
    RpcExtensionUIContext,
    RpcHost,
    RpcModel,
    RpcModelCost,
    RpcSessionState,
)

_EVENT_PROJECTION = RpcEventProjection(
    supported_views=SUPPORTED_JSON_EVENT_VIEWS,
    normalize_select=normalize_event_select,
    project_session_event=project_session_event,
    should_emit_projected_event=should_emit_projected_event,
    shape_stream_event=shape_stream_event,
    project_runtime_event_to_json_views=project_runtime_event_to_json_views,
    should_emit_runtime_event_view=should_emit_runtime_event_view,
    shape_runtime_event_view=shape_runtime_event_view,
)

_DIAGNOSTICS_PROJECTION = RpcDiagnosticsProjection(
    serialize_diagnostic=serialize_diagnostic,
    serialize_diagnostic_summary=serialize_diagnostic_summary,
    serialize_error_report=serialize_error_report,
)


class RpcMode(RpcHost):
    """Coding Product adapter over the shared Harness RPC host."""

    def __init__(
        self,
        *,
        runtime: Any,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO | None = None,
        event_view: str = "full",
        event_select: str | Sequence[str] | None = None,
        render_tool_events: bool = False,
    ) -> None:
        super().__init__(
            runtime=runtime,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            event_view=event_view,
            event_select=event_select,
            render_tool_events=render_tool_events,
            event_projection=_EVENT_PROJECTION,
            diagnostics_projection=_DIAGNOSTICS_PROJECTION,
        )


async def run_rpc_mode(
    *,
    runtime: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    event_view: str = "full",
    event_select: str | Sequence[str] | None = None,
    render_tool_events: bool = False,
) -> int:
    """Run the Coding Product binding over the shared RPC host."""

    mode = RpcMode(
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
    )
    return await mode.run()


__all__ = [
    "RpcEventProjection",
    "RpcDiagnosticsProjection",
    "RpcExtensionUIContext",
    "RpcMode",
    "RpcModel",
    "RpcModelCost",
    "RpcSessionState",
    "run_rpc_mode",
]

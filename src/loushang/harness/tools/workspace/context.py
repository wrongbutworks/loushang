from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.workspace.exec import ExecService

ToolEventSink = Callable[[Mapping[str, object]], Awaitable[None] | None]


@dataclass(frozen=True)
class ToolContext:
    tool_call_id: str
    cwd: str | None = None
    diagnostics: DiagnosticsService | None = None
    signal: object | None = None
    model: object | None = None
    event_sink: ToolEventSink | None = None
    exec_service: ExecService | None = None


class ToolContextProvider(Protocol):
    def __call__(self, *, tool_call_id: str) -> ToolContext: ...

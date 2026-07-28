from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from loushang.harness.approval import ApprovalResolver
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
    approval_resolver: ApprovalResolver | None = None


class ToolContextProvider(Protocol):
    def __call__(self, *, tool_call_id: str) -> ToolContext: ...


def context_approval_resolver(
    context: ToolContext | None,
    fallback: ApprovalResolver | None,
) -> ApprovalResolver | None:
    """Prefer the live session binding over a reusable definition fallback."""

    if context is not None and context.approval_resolver is not None:
        return context.approval_resolver
    return fallback

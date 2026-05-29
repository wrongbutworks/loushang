from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from loushang.agent.types import AgentToolResult

from .types import ToolDefinition, ToolRenderContext, ToolRenderOutput, ToolRenderResultOptions

ToolDefinitionResolver = Callable[[str], ToolDefinition | None]


class ToolRenderRuntime:
    def __init__(
        self,
        *,
        cwd: str = "",
        theme: Mapping[str, str] | None = None,
        show_images: bool = False,
        on_invalidate: Callable[[str], None] | None = None,
    ) -> None:
        self._cwd = cwd
        self._theme = dict(theme or {})
        self._show_images = show_images
        self._on_invalidate = on_invalidate
        self._args_by_call_id: dict[str, object] = {}
        self._state_by_call_id: dict[str, dict[str, Any]] = {}
        self._last_call_rendered_by_call_id: dict[str, ToolRenderOutput] = {}
        self._last_result_rendered_by_call_id: dict[str, ToolRenderOutput] = {}

    def render_event(
        self,
        event: Mapping[str, Any],
        tool_definition_resolver: ToolDefinitionResolver,
        *,
        expanded: bool = False,
    ) -> ToolRenderOutput:
        event_type = event.get("type")
        if event_type == "tool_execution_start":
            tool_call_id, tool_name = _event_tool_identity(event)
            definition = _resolve_tool_definition(tool_definition_resolver, tool_name)
            if tool_call_id is None or definition is None:
                return None
            return self.render_call(
                definition,
                tool_call_id,
                event.get("args"),
                execution_started=True,
                args_complete=True,
                is_partial=True,
                expanded=expanded,
                is_error=False,
            )
        if event_type == "tool_execution_update":
            tool_call_id, tool_name = _event_tool_identity(event)
            definition = _resolve_tool_definition(tool_definition_resolver, tool_name)
            partial_result = event.get("partial_result")
            if tool_call_id is None or definition is None or not isinstance(partial_result, AgentToolResult):
                return None
            if "args" in event:
                self._args_by_call_id[tool_call_id] = event["args"]
            return self.render_result(
                definition,
                tool_call_id,
                partial_result,
                is_partial=True,
                expanded=expanded,
                is_error=False,
            )
        if event_type == "tool_execution_end":
            tool_call_id, tool_name = _event_tool_identity(event)
            definition = _resolve_tool_definition(tool_definition_resolver, tool_name)
            result = event.get("result")
            if tool_call_id is None or definition is None or not isinstance(result, AgentToolResult):
                return None
            return self.render_result(
                definition,
                tool_call_id,
                result,
                is_partial=False,
                expanded=expanded,
                is_error=bool(event.get("is_error", False)),
            )
        return None

    def render_call(
        self,
        definition: ToolDefinition,
        tool_call_id: str,
        args: object,
        *,
        execution_started: bool = True,
        args_complete: bool = True,
        is_partial: bool = True,
        expanded: bool = False,
        is_error: bool = False,
    ) -> ToolRenderOutput:
        if definition.render_call is None:
            return None
        self._args_by_call_id[tool_call_id] = args
        context = self._context(
            tool_call_id,
            last_rendered=self._last_call_rendered_by_call_id.get(tool_call_id),
            execution_started=execution_started,
            args_complete=args_complete,
            is_partial=is_partial,
            expanded=expanded,
            is_error=is_error,
        )
        rendered = definition.render_call(args, self._theme, context)
        self._last_call_rendered_by_call_id[tool_call_id] = rendered
        return rendered

    def render_result(
        self,
        definition: ToolDefinition,
        tool_call_id: str,
        result: AgentToolResult[Any],
        *,
        is_partial: bool = False,
        expanded: bool = False,
        is_error: bool = False,
        execution_started: bool = True,
        args_complete: bool = True,
    ) -> ToolRenderOutput:
        if definition.render_result is None:
            return None
        context = self._context(
            tool_call_id,
            last_rendered=self._last_result_rendered_by_call_id.get(tool_call_id),
            execution_started=execution_started,
            args_complete=args_complete,
            is_partial=is_partial,
            expanded=expanded,
            is_error=is_error,
        )
        options = ToolRenderResultOptions(expanded=expanded, is_partial=is_partial)
        rendered = definition.render_result(result, options, self._theme, context)
        self._last_result_rendered_by_call_id[tool_call_id] = rendered
        return rendered

    def _context(
        self,
        tool_call_id: str,
        *,
        last_rendered: object | None,
        execution_started: bool,
        args_complete: bool,
        is_partial: bool,
        expanded: bool,
        is_error: bool,
    ) -> ToolRenderContext:
        return ToolRenderContext(
            args=self._args_by_call_id.get(tool_call_id),
            tool_call_id=tool_call_id,
            invalidate=lambda: self._invalidate(tool_call_id),
            last_rendered=last_rendered,
            state=self._state_for(tool_call_id),
            cwd=self._cwd,
            execution_started=execution_started,
            args_complete=args_complete,
            is_partial=is_partial,
            expanded=expanded,
            show_images=self._show_images,
            is_error=is_error,
        )

    def _state_for(self, tool_call_id: str) -> dict[str, Any]:
        state = self._state_by_call_id.get(tool_call_id)
        if state is None:
            state = {}
            self._state_by_call_id[tool_call_id] = state
        return state

    def _invalidate(self, tool_call_id: str) -> None:
        if self._on_invalidate is not None:
            self._on_invalidate(tool_call_id)


def _event_tool_identity(event: Mapping[str, Any]) -> tuple[str | None, str]:
    tool_call_id = event.get("tool_call_id", event.get("toolCallId"))
    tool_name = event.get("tool_name", event.get("toolName"))
    return (
        tool_call_id if isinstance(tool_call_id, str) else None,
        tool_name if isinstance(tool_name, str) else "",
    )


def _resolve_tool_definition(
    resolver: ToolDefinitionResolver,
    tool_name: str,
) -> ToolDefinition | None:
    try:
        return resolver(tool_name)
    except Exception:
        return None

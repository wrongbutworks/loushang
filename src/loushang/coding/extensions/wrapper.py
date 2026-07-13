from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from loushang.agent.types import AgentToolResult
from loushang.coding.extensions.types import ExtensionContext
from loushang.harness.tools.core import ToolDefinition


def wrap_registered_tool_definition(
    definition: ToolDefinition,
    context_factory: Callable[[], ExtensionContext],
) -> ToolDefinition:
    execute = definition.execute
    expects_context = _expects_extension_context(execute)

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: object | None = None,
    ) -> AgentToolResult[Any]:
        if expects_context:
            return await execute(tool_call_id, params, signal, on_update, context_factory())  # type: ignore[misc]
        return await execute(tool_call_id, params, signal, on_update)

    return replace(definition, execute=_execute)


def wrap_registered_tool_definitions(
    definitions: list[ToolDefinition],
    context_factory: Callable[[], ExtensionContext],
) -> list[ToolDefinition]:
    return [wrap_registered_tool_definition(definition, context_factory) for definition in definitions]


def _expects_extension_context(execute: object) -> bool:
    signature = inspect.signature(execute)
    positional_count = 0
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            return True
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            positional_count += 1
    return positional_count >= 5

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from loushang.agent.types import AgentTool, AgentToolResult, ToolExecutionMode

from .context import ToolContextProvider
from .runtime import raise_if_tool_aborted
from .types import ToolDefinition, ToolRenderCall, ToolRenderResult


@dataclass
class WrappedToolDefinition:
    definition: ToolDefinition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def label(self) -> str:
        return self.definition.label

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self.definition.provider_parameters or self.definition.parameters

    @property
    def prepare_arguments(self):
        return self.definition.prepare_arguments

    @property
    def execution_mode(self) -> ToolExecutionMode:
        return self.definition.execution_mode

    @property
    def render_call(self) -> ToolRenderCall | None:
        return self.definition.render_call

    @property
    def renderCall(self) -> ToolRenderCall | None:
        return self.definition.renderCall

    @property
    def render_result(self) -> ToolRenderResult | None:
        return self.definition.render_result

    @property
    def renderResult(self) -> ToolRenderResult | None:
        return self.definition.renderResult

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: object | None = None,
    ) -> AgentToolResult[Any]:
        raise_if_tool_aborted(signal)
        return await self.definition.execute(tool_call_id, params, signal, on_update)


def wrap_tool_definition(
    definition: ToolDefinition,
    *,
    context_provider: ToolContextProvider | None = None,
) -> AgentTool[Any]:
    execute = definition.execute
    bind_context_provider = getattr(execute, "bind_context_provider", None)
    if callable(bind_context_provider):
        definition = replace(definition, execute=bind_context_provider(context_provider))
    return WrappedToolDefinition(definition=definition)


def create_tool_definition_from_tool(tool: AgentTool[Any]) -> ToolDefinition:
    definition = getattr(tool, "definition", None)
    if isinstance(definition, ToolDefinition):
        return definition
    return ToolDefinition(
        name=tool.name,
        label=tool.label,
        description=tool.description,
        parameters=tool.parameters,
        prepare_arguments=tool.prepare_arguments,
        execution_mode=tool.execution_mode,
        render_call=getattr(tool, "render_call", getattr(tool, "renderCall", None)),
        render_result=getattr(tool, "render_result", getattr(tool, "renderResult", None)),
        execute=tool.execute,
    )


def wrap_tool_definitions(
    definitions: list[ToolDefinition],
    *,
    context_provider: ToolContextProvider | None = None,
) -> list[AgentTool[Any]]:
    return [wrap_tool_definition(definition, context_provider=context_provider) for definition in definitions]


def wrapToolDefinition(
    definition: ToolDefinition,
    context_provider: ToolContextProvider | None = None,
) -> AgentTool[Any]:
    return wrap_tool_definition(definition, context_provider=context_provider)


def wrapToolDefinitions(
    definitions: list[ToolDefinition],
    context_provider: ToolContextProvider | None = None,
) -> list[AgentTool[Any]]:
    return wrap_tool_definitions(definitions, context_provider=context_provider)


createToolDefinitionFromAgentTool = create_tool_definition_from_tool

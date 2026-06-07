from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.agent.types import AgentTool, ensure_agent_tool, is_agent_tool_like

from .authoring import DecoratedTool
from .context import ToolContextProvider
from .normalize import tool_to_definition
from .types import ToolDefinition
from .wrapper import create_tool_definition_from_tool, wrap_tool_definition


@dataclass(frozen=True)
class _RegisteredTool:
    definition: ToolDefinition
    enabled: bool = True
    source_info: object | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}
        self._order: list[str] = []

    def register_tool(
        self,
        tool: ToolDefinition | DecoratedTool | AgentTool[Any],
        *,
        enabled: bool = True,
        source_info: object | None = None,
    ) -> ToolDefinition:
        if isinstance(tool, ToolDefinition):
            definition = tool
        elif is_agent_tool_like(tool):
            definition = create_tool_definition_from_tool(ensure_agent_tool(tool))
        else:
            definition = tool_to_definition(tool)
        if definition.name not in self._tools:
            self._order.append(definition.name)
        self._tools[definition.name] = _RegisteredTool(definition=definition, enabled=enabled, source_info=source_info)
        return definition

    def get_tool(self, name: str) -> AgentTool[Any]:
        return self.materialize_tool(name)

    def get_definition(self, name: str) -> ToolDefinition:
        return self._tools[name].definition

    def get_source_info(self, name: str) -> object | None:
        return self._tools[name].source_info

    def list_tools(self) -> list[AgentTool[Any]]:
        return self.materialize_definitions(self.list_definitions())

    def list_enabled_tools(self) -> list[AgentTool[Any]]:
        return self.materialize_definitions(self.list_enabled_definitions())

    def list_definitions(self) -> list[ToolDefinition]:
        return [self._tools[name].definition for name in self._order]

    def list_enabled_definitions(self) -> list[ToolDefinition]:
        return [self._tools[name].definition for name in self._order if self._tools[name].enabled]

    def enable_tool(self, name: str) -> None:
        registered = self._tools[name]
        self._tools[name] = _RegisteredTool(
            definition=registered.definition,
            enabled=True,
            source_info=registered.source_info,
        )

    def disable_tool(self, name: str) -> None:
        registered = self._tools[name]
        self._tools[name] = _RegisteredTool(
            definition=registered.definition,
            enabled=False,
            source_info=registered.source_info,
        )

    def materialize_tool(
        self,
        name: str,
        *,
        context_provider: ToolContextProvider | None = None,
    ) -> AgentTool[Any]:
        return wrap_tool_definition(self.get_definition(name), context_provider=context_provider)

    def materialize_definitions(
        self,
        definitions: list[ToolDefinition],
        *,
        context_provider: ToolContextProvider | None = None,
    ) -> list[AgentTool[Any]]:
        return [
            wrap_tool_definition(definition, context_provider=context_provider)
            for definition in definitions
        ]

from __future__ import annotations

from typing import Any

from loushang.agent.types import AgentTool, is_agent_tool_like
from loushang.harness.tools.contribution import (
    ToolContribution,
    ToolPackDefinition,
    ToolResolutionResult,
    resolve_tool_contributions,
)
from loushang.harness.tools.core import ToolRegistry as HarnessToolRegistry

from .authoring import DecoratedTool
from .context import ToolContextProvider
from .normalize import tool_to_definition
from .types import ToolDefinition
from .wrapper import wrap_tool_definition


class ToolRegistry(HarnessToolRegistry):
    def register_tool(
        self,
        tool: ToolDefinition | DecoratedTool | AgentTool[Any] | object,
        *,
        enabled: bool = True,
        source_info: object | None = None,
    ) -> ToolDefinition:
        if isinstance(tool, ToolDefinition) or is_agent_tool_like(tool):
            return super().register_tool(tool, enabled=enabled, source_info=source_info)
        return super().register_tool(
            tool_to_definition(tool),
            enabled=enabled,
            source_info=source_info,
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

    def list_contributions(self) -> tuple[ToolContribution, ...]:
        enabled_names = {definition.name for definition in self.list_enabled_definitions()}
        return tuple(
            ToolContribution(
                definition,
                enabled=definition.name in enabled_names,
                source_info=self.get_source_info(definition.name),
            )
            for definition in self.list_definitions()
        )

    def resolve_contributions(
        self,
        *,
        packs: tuple[ToolPackDefinition, ...] | list[ToolPackDefinition] = (),
        include_packs: tuple[str, ...] | list[str] = (),
        disabled_tools: tuple[str, ...] | list[str] = (),
        fail_on_errors: bool = True,
    ) -> ToolResolutionResult:
        return resolve_tool_contributions(
            self.list_contributions(),
            packs=packs,
            include_packs=include_packs,
            disabled_tools=disabled_tools,
            fail_on_errors=fail_on_errors,
        )


__all__ = [
    "ToolRegistry",
]

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from loushang.agent.types import AgentTool, ensure_agent_tool, is_agent_tool_like
from loushang.coding.prompt import assemble_prompt
from loushang.coding.store import SessionManager
from loushang.coding.tools import ToolRegistry
from loushang.harness.capabilities.tools import (
    ToolActivationChange,
    ToolActivationCoordinator,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.tools.contribution import (
    ToolContribution,
    ToolResolutionResult,
    resolve_tool_contributions,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace.context import ToolContext
from loushang.harness.tools.workspace.normalize import tool_to_definition
from loushang.harness.tools.workspace.wrapper import create_tool_definition_from_tool

_DEFAULT_ACTIVE_TOOL_NAMES: tuple[str, ...] = (
    "read",
    "ls",
    "find",
    "grep",
    "bash",
    "edit",
    "write",
)
_BUILTIN_TOOL_NAMES: frozenset[str] = frozenset(
    ("bash", "read", "ls", "find", "grep", "write", "edit")
)


class AgentPort(Protocol):
    @property
    def system_prompt(self) -> str: ...

    @system_prompt.setter
    def system_prompt(self, value: str) -> None: ...

    @property
    def tools(self) -> list[AgentTool[Any]]: ...

    @tools.setter
    def tools(self, value: list[AgentTool[Any]]) -> None: ...


@dataclass
class ToolController:
    agent: AgentPort
    session_manager: SessionManager
    tool_registry: ToolRegistry | None
    allowed_tool_names: set[str] | None
    initial_active_tool_names: list[str]
    base_prompt: str
    get_resource_bundle: Callable[[], ResourceBundle | None]
    get_diagnostics_service: Callable[[], DiagnosticsService | None]
    emit_tool_audit_event: Callable[[dict[str, object]], Awaitable[None]] | None = None
    default_activate_new_tools: bool = False
    show_empty_tool_prompt: bool = False
    _activation: ToolActivationCoordinator[ToolDefinition] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self._activation = ToolActivationCoordinator(
            available=self._available_definitions(),
            requested_names=self.initial_active_tool_names,
            allowed_names=self.allowed_tool_names,
            should_activate_new=self._should_activate_new_tool,
            rebind=self._rebind_active_tools,
        )

    def get_active_tool_names(self) -> list[str]:
        return list(self._activation.snapshot().active_names)

    def get_all_tools(self) -> list[ToolDefinition]:
        return list(self._activation.filter_items(self._available_definitions()))

    def get_all_tool_infos(self) -> list[dict[str, object]]:
        return [
            _tool_info_from_definition(
                definition,
                self.tool_source_info(definition.name),
            )
            for definition in self.get_all_tools()
        ]

    def get_tool_definition(self, name: str) -> ToolDefinition | None:
        if not self.is_tool_allowed(name):
            return None
        if self.tool_registry is not None:
            try:
                return self.tool_registry.get_definition(name)
            except KeyError:
                return None
        for definition in self.get_all_tools():
            if definition.name == name:
                return definition
        return None

    def apply_active_tools(self, tool_names: list[str]) -> None:
        if self.tool_registry is None:
            raise RuntimeError("Active tool selection requires a tool registry")
        self._sync_available(activate_new=False, rebind=False)
        self._activation.request(tool_names)

    def build_tool_context(self, *, tool_call_id: str) -> ToolContext:
        return ToolContext(
            tool_call_id=tool_call_id,
            cwd=self.session_manager.get_cwd(),
            diagnostics=self.get_diagnostics_service(),
            model=getattr(self.agent, "model", None),
            event_sink=(
                self._emit_tool_audit_event
                if self.emit_tool_audit_event is not None
                else None
            ),
        )

    def resolve_active_tool_definitions(
        self, tool_names: list[str]
    ) -> tuple[list[ToolDefinition], list[str]]:
        if self.tool_registry is None:
            raise RuntimeError("Active tool selection requires a tool registry")
        self._sync_available(activate_new=False, rebind=False)
        resolution = self._activation.resolve(tool_names)
        return list(resolution.items), list(resolution.names)

    def is_tool_allowed(self, name: str) -> bool:
        return self._activation.is_allowed(name)

    def filter_allowed_tool_names(self, tool_names: list[str]) -> list[str]:
        return list(self._activation.filter_names(tool_names))

    def filter_allowed_tool_definitions(
        self, definitions: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return list(self._activation.filter_items(definitions))

    def tool_source_info(self, name: str) -> object | None:
        if self.tool_registry is None:
            return None
        try:
            return self.tool_registry.get_source_info(name)
        except KeyError:
            return None

    def default_active_tool_names(self) -> list[str]:
        if self.tool_registry is None:
            return []
        enabled_names = [
            definition.name
            for definition in self.tool_registry.list_enabled_definitions()
        ]
        if self.allowed_tool_names is not None:
            return self.filter_allowed_tool_names(enabled_names)
        enabled_name_set = set(enabled_names)
        active_names = [
            name for name in _DEFAULT_ACTIVE_TOOL_NAMES if name in enabled_name_set
        ]
        active_names.extend(
            name
            for name in enabled_names
            if name not in _BUILTIN_TOOL_NAMES and name not in active_names
        )
        return active_names

    def ensure_tool_registry(self) -> ToolRegistry:
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
        return self.tool_registry

    def register_runtime_tool(
        self, tool: object, *, source_info: object | None = None
    ) -> ToolDefinition:
        registry = self.ensure_tool_registry()
        contribution = _runtime_tool_contribution(tool, source_info=source_info)
        resolution = resolve_tool_contributions(
            (
                *registry.list_contributions(),
                contribution,
            ),
            fail_on_errors=False,
        )
        registration_contribution = _runtime_tool_registration_contribution(
            resolution,
            fallback=contribution,
        )
        definition = registry.register_tool(
            registration_contribution.definition,
            source_info=registration_contribution.source_info,
        )
        if not self.is_tool_allowed(definition.name):
            self.rebuild_prompt_and_tools_view()
            return definition

        self._sync_available(activate_new=True, rebind=True)
        return definition

    def rebuild_prompt_and_tools_view(self) -> None:
        active_definitions: list[ToolDefinition] | None = None
        tool_prompt: str | None = None
        if self.tool_registry is not None:
            self._sync_available(activate_new=False, rebind=False)
            active_definitions = list(self._activation.active_items())
        elif self.show_empty_tool_prompt:
            active_definitions = []
        if self.show_empty_tool_prompt and active_definitions == []:
            tool_prompt = "Available tools:\n(none)"
        prompt_assembly = assemble_prompt(
            base_prompt=self.base_prompt,
            resource_bundle=self.get_resource_bundle(),
            tool_definitions=active_definitions,
            tool_prompt=tool_prompt,
        )
        self.agent.system_prompt = prompt_assembly.system_prompt

    def _available_definitions(self) -> list[ToolDefinition]:
        if self.tool_registry is not None:
            return self.tool_registry.list_definitions()
        return [
            create_tool_definition_from_tool(tool)
            if isinstance(tool, AgentTool)
            else tool_to_definition(tool)
            for tool in self.agent.tools
        ]

    def _sync_available(self, *, activate_new: bool, rebind: bool) -> None:
        self._activation.refresh(
            self._available_definitions(),
            activate_new=activate_new,
            rebind=rebind,
        )

    def _should_activate_new_tool(self, name: str, definition: ToolDefinition) -> bool:
        del definition
        return self.default_activate_new_tools and name not in _BUILTIN_TOOL_NAMES

    def _rebind_active_tools(
        self,
        change: ToolActivationChange[ToolDefinition],
    ) -> None:
        if self.tool_registry is not None:
            self.agent.tools = self.tool_registry.materialize_definitions(
                list(change.active_items),
                context_provider=self.build_tool_context,
            )
        self.rebuild_prompt_and_tools_view()

    async def _emit_tool_audit_event(
        self,
        event: Mapping[str, object],
    ) -> None:
        if self.emit_tool_audit_event is not None:
            await self.emit_tool_audit_event(dict(event))


def _tool_info_from_definition(
    definition: ToolDefinition, source_info: object | None = None
) -> dict[str, object]:
    return {
        "name": definition.name,
        "description": definition.description,
        "parameters": definition.parameters,
        "sourceInfo": _serialize_tool_source_info(source_info)
        if source_info is not None
        else _synthetic_tool_source_info(definition.name),
    }


def _runtime_tool_contribution(
    tool: object, *, source_info: object | None = None
) -> ToolContribution:
    definition = _runtime_tool_definition(tool)
    return ToolContribution(
        definition,
        source_info=source_info,
        metadata={
            "kind": "runtime_tool",
            "runtime_tool": definition.name,
        },
    )


def _runtime_tool_definition(tool: object) -> ToolDefinition:
    if isinstance(tool, ToolDefinition):
        return tool
    if is_agent_tool_like(tool):
        return create_tool_definition_from_tool(ensure_agent_tool(tool))
    return tool_to_definition(tool)


def _runtime_tool_registration_contribution(
    resolution: ToolResolutionResult,
    *,
    fallback: ToolContribution,
) -> ToolContribution:
    for contribution in resolution.contributions:
        if contribution.definition.name != fallback.definition.name:
            continue
        if contribution.metadata.get("kind") == "runtime_tool":
            return contribution
    return fallback


def _synthetic_tool_source_info(name: str) -> dict[str, object]:
    if name in _BUILTIN_TOOL_NAMES:
        return {
            "path": f"<builtin:{name}>",
            "source": "builtin",
            "scope": "temporary",
            "origin": "top-level",
            "baseDir": None,
        }
    return {
        "path": f"<sdk:{name}>",
        "source": "sdk",
        "scope": "temporary",
        "origin": "top-level",
        "baseDir": None,
    }


def _serialize_tool_source_info(source_info: object) -> dict[str, object]:
    base_dir = getattr(source_info, "base_dir", None)
    return {
        "path": _safe_source_path_text(getattr(source_info, "path", "")),
        "source": getattr(source_info, "source", "filesystem"),
        "scope": getattr(source_info, "scope", "project"),
        "origin": getattr(source_info, "origin", "top-level"),
        "baseDir": _safe_source_path_text(base_dir) if base_dir is not None else None,
    }


def _safe_source_path_text(value: object) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    return str(value)

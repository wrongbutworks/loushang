from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from loushang.agent.types import AgentTool
from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.loader import ResourceBundle
from loushang.coding.prompt import assemble_prompt
from loushang.coding.store import SessionManager
from loushang.coding.tools import (
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    create_tool_definition_from_tool,
    tool_to_definition,
)

_DEFAULT_ACTIVE_TOOL_NAMES: tuple[str, ...] = ("read", "bash", "edit", "write")
_BUILTIN_TOOL_NAMES: frozenset[str] = frozenset(("bash", "read", "ls", "find", "grep", "write", "edit"))


@dataclass
class ToolController:
    agent: object
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
    _active_tool_names: list[str] = field(init=False)
    _requested_active_tool_names: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self._requested_active_tool_names = self.filter_allowed_tool_names(list(self.initial_active_tool_names))
        self._active_tool_names = list(self._requested_active_tool_names)

    def get_active_tool_names(self) -> list[str]:
        return list(self._active_tool_names)

    def get_all_tools(self) -> list[ToolDefinition]:
        if self.tool_registry is not None:
            return self.filter_allowed_tool_definitions(self.tool_registry.list_definitions())
        return [
            definition
            for tool in self.agent.tools
            for definition in [
                create_tool_definition_from_tool(tool)
                if isinstance(tool, AgentTool)
                else tool_to_definition(tool)
            ]
            if self.is_tool_allowed(definition.name)
        ]

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

        requested_tool_names = self.filter_allowed_tool_names(tool_names)
        active_definitions, active_tool_names = self.resolve_active_tool_definitions(requested_tool_names)
        runtime_tools = self.tool_registry.materialize_definitions(
            active_definitions,
            context_provider=self.build_tool_context,
        )
        self._requested_active_tool_names = requested_tool_names
        self._active_tool_names = active_tool_names
        self.agent.tools = runtime_tools
        self.rebuild_prompt_and_tools_view()

    def build_tool_context(self, *, tool_call_id: str) -> ToolContext:
        return ToolContext(
            tool_call_id=tool_call_id,
            cwd=self.session_manager.get_cwd(),
            diagnostics=self.get_diagnostics_service(),
            model=getattr(self.agent, "model", None),
            event_sink=self.emit_tool_audit_event,
        )

    def resolve_active_tool_definitions(self, tool_names: list[str]) -> tuple[list[ToolDefinition], list[str]]:
        if self.tool_registry is None:
            raise RuntimeError("Active tool selection requires a tool registry")
        definitions_by_name = {
            definition.name: definition
            for definition in self.filter_allowed_tool_definitions(self.tool_registry.list_definitions())
        }
        active_definitions: list[ToolDefinition] = []
        active_tool_names: list[str] = []
        for tool_name in tool_names:
            definition = definitions_by_name.get(tool_name)
            if definition is None:
                continue
            active_tool_names.append(tool_name)
            active_definitions.append(definition)
        return active_definitions, active_tool_names

    def is_tool_allowed(self, name: str) -> bool:
        return self.allowed_tool_names is None or name in self.allowed_tool_names

    def filter_allowed_tool_names(self, tool_names: list[str]) -> list[str]:
        return [name for name in tool_names if self.is_tool_allowed(name)]

    def filter_allowed_tool_definitions(self, definitions: list[ToolDefinition]) -> list[ToolDefinition]:
        return [definition for definition in definitions if self.is_tool_allowed(definition.name)]

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
        enabled_names = [definition.name for definition in self.tool_registry.list_enabled_definitions()]
        if self.allowed_tool_names is not None:
            return self.filter_allowed_tool_names(enabled_names)
        enabled_name_set = set(enabled_names)
        active_names = [name for name in _DEFAULT_ACTIVE_TOOL_NAMES if name in enabled_name_set]
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

    def register_runtime_tool(self, tool: object, *, source_info: object | None = None) -> ToolDefinition:
        registry = self.ensure_tool_registry()
        definition = registry.register_tool(tool, source_info=source_info)  # type: ignore[arg-type]
        if not self.is_tool_allowed(definition.name):
            self.rebuild_prompt_and_tools_view()
            return definition

        requested_names = list(self._requested_active_tool_names)
        should_activate = (
            definition.name in requested_names
            or definition.name in self._active_tool_names
            or (self.default_activate_new_tools and definition.name not in _BUILTIN_TOOL_NAMES)
        )
        if not should_activate:
            self.rebuild_prompt_and_tools_view()
            return definition

        if definition.name not in requested_names:
            requested_names.append(definition.name)
        self.apply_active_tools(requested_names)
        return definition

    def rebuild_prompt_and_tools_view(self) -> None:
        active_definitions: list[ToolDefinition] | None = None
        tool_prompt: str | None = None
        if self.tool_registry is not None:
            active_definitions, _ = self.resolve_active_tool_definitions(self._active_tool_names)
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


def _tool_info_from_definition(definition: ToolDefinition, source_info: object | None = None) -> dict[str, object]:
    return {
        "name": definition.name,
        "description": definition.description,
        "parameters": definition.parameters,
        "sourceInfo": _serialize_tool_source_info(source_info) if source_info is not None else _synthetic_tool_source_info(definition.name),
    }


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

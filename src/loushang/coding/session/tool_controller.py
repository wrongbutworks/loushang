from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from loushang.agent.types import AgentTool
from loushang.coding.prompt import assemble_prompt
from loushang.coding.store import SessionManager
from loushang.coding.tools import ToolRegistry
from loushang.harness.capabilities.prompt import PromptSectionComposer
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.activation import ResourceActivationRuntime
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session import SessionToolRuntime
from loushang.harness.tools.contribution import resolve_tool_contributions
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace.context import ToolContext

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
    """Coding prompt and policy adapter for ``SessionToolRuntime``."""

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
    resource_activation_runtime: ResourceActivationRuntime = field(
        default_factory=ResourceActivationRuntime
    )
    prompt_section_composer: PromptSectionComposer = field(
        default_factory=PromptSectionComposer
    )
    _runtime: SessionToolRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = SessionToolRuntime(
            agent=self.agent,
            tool_registry=self.tool_registry,
            allowed_tool_names=self.allowed_tool_names,
            initial_active_tool_names=self.initial_active_tool_names,
            default_active_tool_names=self._default_active_tool_names,
            should_activate_new_tool=self._should_activate_new_tool,
            build_tool_context=self.build_tool_context,
            rebuild_prompt=self._rebuild_prompt,
            resolve_contributions=resolve_tool_contributions,
        )

    def get_active_tool_names(self) -> list[str]:
        return self._runtime.get_active_tool_names()

    def get_all_tools(self) -> list[ToolDefinition]:
        return self._runtime.get_all_tools()

    def get_all_tool_infos(self) -> list[dict[str, object]]:
        return [
            _tool_info_from_definition(
                definition,
                self.tool_source_info(definition.name),
            )
            for definition in self.get_all_tools()
        ]

    def get_tool_definition(self, name: str) -> ToolDefinition | None:
        return self._runtime.get_tool_definition(name)

    def apply_active_tools(self, tool_names: list[str]) -> None:
        self._runtime.apply_active_tools(tool_names)

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
        return self._runtime.resolve_active_tool_definitions(tool_names)

    def is_tool_allowed(self, name: str) -> bool:
        return self._runtime.is_tool_allowed(name)

    def filter_allowed_tool_names(self, tool_names: list[str]) -> list[str]:
        return self._runtime.filter_allowed_tool_names(tool_names)

    def filter_allowed_tool_definitions(
        self, definitions: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return self._runtime.filter_allowed_tool_definitions(definitions)

    def tool_source_info(self, name: str) -> object | None:
        return self._runtime.tool_source_info(name)

    def default_active_tool_names(self) -> list[str]:
        return self._runtime.default_active_names()

    def ensure_tool_registry(self) -> ToolRegistry:
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
            self._runtime.set_tool_registry(self.tool_registry)
        return self.tool_registry

    def register_runtime_tool(
        self, tool: object, *, source_info: object | None = None
    ) -> ToolDefinition:
        self.ensure_tool_registry()
        return self._runtime.register_runtime_tool(tool, source_info=source_info)

    def rebuild_prompt_and_tools_view(self) -> None:
        self._runtime.rebuild_prompt_and_tools_view()

    def _default_active_tool_names(self) -> list[str]:
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

    def _should_activate_new_tool(self, name: str, definition: ToolDefinition) -> bool:
        del definition
        return self.default_activate_new_tools and name not in _BUILTIN_TOOL_NAMES

    def _rebuild_prompt(
        self, active_definitions: list[ToolDefinition] | None
    ) -> None:
        if self.show_empty_tool_prompt and active_definitions is None:
            active_definitions = []
        tool_prompt = (
            "Available tools:\n(none)"
            if self.show_empty_tool_prompt and active_definitions == []
            else None
        )
        prompt_assembly = assemble_prompt(
            base_prompt=self.base_prompt,
            resource_bundle=self.get_resource_bundle(),
            tool_definitions=active_definitions,
            tool_prompt=tool_prompt,
            resource_activation=self.resource_activation_runtime.activate(
                self.get_resource_bundle()
            ),
            prompt_section_composer=self.prompt_section_composer,
        )
        self.agent.system_prompt = prompt_assembly.system_prompt

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

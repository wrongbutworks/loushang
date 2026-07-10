from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from loushang.agent.types import (
    AgentTool,
    ThinkingLevel,
    ensure_agent_tool,
    is_agent_tool_like,
)
from loushang.coding.extensions.types import (
    VALID_EXTENSION_EVENTS,
    ExtensionCommandContext,
    ExtensionContext,
    ExtensionHandler,
    LoadedExtension,
    RegisteredCommand,
    RegisteredFlag,
    RegisteredShortcut,
)
from loushang.coding.loader import ResourceDiagnostic
from loushang.coding.tools import (
    DecoratedTool,
    ToolDefinition,
    create_tool_definition_from_tool,
    tool_to_definition,
)
from loushang.harness.resources.source import SourceInfo
from loushang.harness.workspace.exec import ExecResult, ExecUpdateCallback


class ExtensionAPI:
    def __init__(
        self,
        *,
        name: str,
        source_path: Path,
        entry_path: Path | None = None,
    ) -> None:
        self._name = name
        self._source_path = source_path
        self._entry_path = entry_path
        self._hooks: dict[str, list[object]] = {}
        self._tool_definitions: list[ToolDefinition] = []
        self._commands: dict[str, RegisteredCommand] = {}
        self._flags: dict[str, RegisteredFlag] = {}
        self._shortcuts: dict[str, RegisteredShortcut] = {}
        self._message_renderers: dict[str, Callable[[object, object, object], object | None]] = {}
        self._diagnostics: list[ResourceDiagnostic] = []
        self._runtime_state: object | None = None
        self._pending_provider_actions: list[tuple[str, str, object | None]] = []

    def on(self, event_name: str, handler: object) -> None:
        if event_name not in VALID_EXTENSION_EVENTS:
            raise ValueError(f"Unsupported extension event: {event_name}")
        self._hooks.setdefault(event_name, []).append(handler)

    def register_tool(
        self,
        tool_definition: ToolDefinition | DecoratedTool | AgentTool[object],
    ) -> None:
        definition = (
            tool_definition
            if isinstance(tool_definition, ToolDefinition)
            else create_tool_definition_from_tool(ensure_agent_tool(tool_definition))
            if is_agent_tool_like(tool_definition)
            else tool_to_definition(tool_definition)
        )
        self._tool_definitions.append(definition)
        self._register_runtime_tool(definition)

    def registerTool(
        self,
        tool_definition: ToolDefinition | DecoratedTool | AgentTool[object],
    ) -> None:
        self.register_tool(tool_definition)

    def register_command(
        self,
        name: str,
        *,
        description: str | None = None,
        handler: Callable[[str, ExtensionCommandContext], Awaitable[None]],
        get_argument_completions: Callable[[str], list[object] | Awaitable[list[object] | None] | None] | None = None,
    ) -> None:
        self._commands[name] = RegisteredCommand(
            name=name,
            handler=handler,
            description=description,
            get_argument_completions=get_argument_completions,
        )

    def register_flag(
        self,
        name: str,
        *,
        type: Literal["boolean", "string"],
        description: str | None = None,
        default: bool | str | None = None,
    ) -> None:
        if type not in {"boolean", "string"}:
            raise ValueError(f"Unsupported flag type: {type}")
        if type == "boolean" and default is not None and not isinstance(default, bool):
            raise ValueError("Boolean flags must use a boolean default.")
        if type == "string" and default is not None and not isinstance(default, str):
            raise ValueError("String flags must use a string default.")
        self._flags[name] = RegisteredFlag(
            name=name,
            type=type,
            description=description,
            default=default,
        )

    def register_shortcut(
        self,
        shortcut: str,
        *,
        description: str | None = None,
        handler: Callable[[ExtensionContext], object | None],
    ) -> None:
        self._shortcuts[shortcut] = RegisteredShortcut(
            shortcut=shortcut,
            handler=handler,
            description=description,
        )

    def register_message_renderer(
        self,
        custom_type: str,
        renderer: Callable[[object, object, object], object | None],
    ) -> None:
        self._message_renderers[custom_type] = renderer

    def registerMessageRenderer(
        self,
        custom_type: str,
        renderer: Callable[[object, object, object], object | None],
    ) -> None:
        self.register_message_renderer(custom_type, renderer)

    def bind_runtime_state(self, runtime_state: object) -> None:
        self._runtime_state = runtime_state
        self._flush_pending_provider_actions()

    def get_active_tools(self) -> list[str]:
        bindings = self._runtime_bindings()
        if bindings is None:
            return []
        getter = getattr(bindings, "get_active_tool_names", None)
        return list(getter()) if callable(getter) else []

    def get_all_tools(self) -> list[object]:
        bindings = self._runtime_bindings()
        if bindings is None:
            return []
        getter = getattr(bindings, "get_all_tools", None)
        return list(getter()) if callable(getter) else []

    def get_commands(self) -> list[object]:
        bindings = self._runtime_bindings()
        if bindings is None:
            return []
        getter = getattr(bindings, "list_commands", None)
        return list(getter()) if callable(getter) else []

    def get_flag(self, name: str) -> bool | str | None:
        state = self._runtime_state
        values = getattr(state, "flag_values", None) if state is not None else None
        if isinstance(values, dict):
            return values.get(name)
        return None

    def append_entry(self, custom_type: str, data: object | None = None) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "append_entry", None)
        if callable(callback):
            callback(custom_type, data)
        return None

    async def send_message(self, message: object, options: object | None = None) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "send_message", None)
        if callable(callback):
            await callback(message, options)
        return None

    async def send_user_message(self, content: object, options: object | None = None) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "send_user_message", None)
        if callable(callback):
            await callback(content, options)
        return None

    async def set_active_tools(self, tool_names: list[str]) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "set_active_tools", None)
        if callable(callback):
            await callback(list(tool_names))
        return None

    async def set_model(self, selection: object) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "set_model", None)
        if callable(callback):
            await callback(selection)
        return None

    async def exec_command(
        self,
        command: str,
        args: Sequence[str] = (),
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
        preview_max_lines: int = 2000,
        preview_max_bytes: int = 50 * 1024,
        artifact_dir: str | None = None,
        capture_full_output: bool = True,
        rolling_max_bytes: int = 100 * 1024,
    ) -> ExecResult:
        bindings = self._runtime_bindings()
        if bindings is None:
            raise RuntimeError("Extension runtime is not bound.")
        callback = getattr(bindings, "exec_command", None)
        if not callable(callback):
            raise RuntimeError("Extension runtime does not provide exec_command.")
        if isinstance(args, str):
            raise TypeError("exec_command args must be a sequence of strings, not a string")
        result = callback(
            command,
            list(args),
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            signal=signal,
            on_update=on_update,
            preview_max_lines=preview_max_lines,
            preview_max_bytes=preview_max_bytes,
            artifact_dir=artifact_dir,
            capture_full_output=capture_full_output,
            rolling_max_bytes=rolling_max_bytes,
        )
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ExecResult):
            raise TypeError("exec_command runtime binding must return ExecResult")
        return result

    def get_thinking_level(self) -> ThinkingLevel:
        bindings = self._runtime_bindings()
        if bindings is None:
            return "off"
        callback = getattr(bindings, "get_thinking_level", None)
        value = callback() if callable(callback) else None
        return value if value in {"off", "minimal", "low", "medium", "high", "xhigh"} else "off"

    def set_thinking_level(self, level: ThinkingLevel) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "set_thinking_level", None)
        if callable(callback):
            callback(level)
        return None

    def set_session_name(self, name: str | None) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "set_session_name", None)
        if callable(callback):
            callback(name)
        return None

    def get_session_name(self) -> str | None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "get_session_name", None)
        value = callback() if callable(callback) else None
        return value if isinstance(value, str) else None

    def set_label(self, entry_id: str, label: str | None) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return None
        callback = getattr(bindings, "set_label", None)
        if callable(callback):
            callback(entry_id, label)
        return None

    def register_provider(self, name: str, config: object) -> None:
        if not self._apply_provider_action("register", name, config):
            self._pending_provider_actions.append(("register", name, config))

    def unregister_provider(self, name: str) -> None:
        if not self._apply_provider_action("unregister", name, None):
            self._pending_provider_actions.append(("unregister", name, None))

    def _runtime_bindings(self) -> object | None:
        state = self._runtime_state
        bindings = getattr(state, "bindings", None) if state is not None else None
        return bindings

    def _register_runtime_tool(self, definition: ToolDefinition) -> None:
        bindings = self._runtime_bindings()
        if bindings is None:
            return
        callback = getattr(bindings, "register_tool", None)
        if callable(callback):
            callback(definition, SourceInfo(path=self._entry_path or self._source_path))

    def _flush_pending_provider_actions(self) -> None:
        if self._runtime_bindings() is None or not self._pending_provider_actions:
            return
        pending = list(self._pending_provider_actions)
        self._pending_provider_actions.clear()
        for action, name, config in pending:
            if not self._apply_provider_action(action, name, config):
                self._pending_provider_actions.append((action, name, config))

    def _apply_provider_action(self, action: str, name: str, config: object | None) -> bool:
        bindings = self._runtime_bindings()
        if bindings is None:
            return False
        if action == "register":
            callback = getattr(bindings, "register_provider", None)
            if not callable(callback):
                return False
            callback(name, config)
            return True
        callback = getattr(bindings, "unregister_provider", None)
        if not callable(callback):
            return False
        callback(name)
        return True

    def build_loaded_extension(self) -> LoadedExtension:
        return LoadedExtension(
            name=self._name,
            source_path=self._source_path,
            entry_path=self._entry_path,
            hooks={name: cast(list[ExtensionHandler], list(handlers)) for name, handlers in self._hooks.items()},
            tool_definitions=list(self._tool_definitions),
            commands=dict(self._commands),
            flags=dict(self._flags),
            shortcuts=dict(self._shortcuts),
            message_renderers=dict(self._message_renderers),
            diagnostics=list(self._diagnostics),
            api=self,
        )

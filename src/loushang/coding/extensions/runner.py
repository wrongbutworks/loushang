from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from loushang.agent.types import (
    AfterToolCallResult,
    AgentMessage,
    AgentToolResult,
    BeforeToolCallResult,
)
from loushang.ai.types import ToolCall
from loushang.coding.exec import ExecResult, ExecUpdateCallback
from loushang.coding.extensions.loader import ExtensionLoader
from loushang.coding.extensions.types import (
    BeforeAgentStartResult,
    ContextResult,
    ExtensionCommandContext,
    ExtensionContext,
    ExtensionResourceContribution,
    ExtensionRuntimeBindings,
    InputEvent,
    InputEventResult,
    LoadedExtension,
    ResolvedCommand,
    ResolvedFlag,
    ResolvedShortcut,
    SessionActionDecision,
    SessionBeforeCompactResult,
    SessionBeforeForkResult,
    SessionBeforeTreeResult,
    SessionRefreshEvent,
    SourceInfo,
    ToolCallDecision,
    ToolResultDecision,
)
from loushang.coding.extensions.wrapper import wrap_registered_tool_definition
from loushang.coding.loader import (
    ExtensionDescriptor,
    PromptFragmentDescriptor,
    ResourceBundle,
    ResourceDiagnostic,
    SkillDescriptor,
    ThemeDescriptor,
)
from loushang.coding.tools import ToolDefinition


def _normalize_exec_args(args: Sequence[str]) -> list[str]:
    if isinstance(args, str):
        raise TypeError("exec_command args must be a sequence of strings, not a string")
    return list(args)


@dataclass(frozen=True)
class _RunnerContext:
    cwd: str

    @property
    def ui(self) -> "_RunnerContext":
        return self

    @property
    def hasUI(self) -> bool:
        return False

    @property
    def has_ui(self) -> bool:
        return self.hasUI

    @property
    def sessionManager(self) -> object | None:
        return None

    @property
    def session_manager(self) -> object | None:
        return self.sessionManager

    @property
    def modelRegistry(self) -> object | None:
        return None

    @property
    def model_registry(self) -> object | None:
        return self.modelRegistry

    @property
    def model(self) -> object | None:
        return None

    @property
    def signal(self) -> object | None:
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
        del command, args, cwd, env, timeout_seconds, stdin, signal, on_update
        del preview_max_lines, preview_max_bytes, artifact_dir, capture_full_output, rolling_max_bytes
        raise RuntimeError("Extension runtime is not bound.")

    def get_active_tool_names(self) -> list[str]:
        return []

    def getActiveTools(self) -> list[str]:
        return self.get_active_tool_names()

    def getAllTools(self) -> list[object]:
        return []

    def get_all_tools(self) -> list[object]:
        return self.getAllTools()

    def register_tool(self, tool: object) -> None:
        del tool

    def registerTool(self, tool: object) -> None:
        self.register_tool(tool)

    def getFlag(self, name: str) -> bool | str | None:
        del name
        return None

    def get_flag(self, name: str) -> bool | str | None:
        return self.getFlag(name)

    def get_model_selection(self):
        return None

    async def set_active_tools(self, tool_names: list[str]) -> None:
        del tool_names

    async def setActiveTools(self, tool_names: list[str]) -> None:
        await self.set_active_tools(tool_names)

    async def set_model(self, selection) -> None:
        del selection

    async def setModel(self, selection) -> None:
        await self.set_model(selection)

    def getThinkingLevel(self) -> str:
        return "off"

    def get_thinking_level(self) -> str:
        return self.getThinkingLevel()

    def setThinkingLevel(self, level: str) -> None:
        del level

    def set_thinking_level(self, level: str) -> None:
        self.setThinkingLevel(level)

    def appendEntry(self, custom_type: str, data: object | None = None) -> None:
        del custom_type, data

    def append_entry(self, custom_type: str, data: object | None = None) -> None:
        self.appendEntry(custom_type, data)

    async def sendMessage(self, message: object, options: object | None = None) -> None:
        del message, options

    async def send_message(self, message: object, options: object | None = None) -> None:
        await self.sendMessage(message, options)

    async def sendUserMessage(self, content: object, options: object | None = None) -> None:
        del content, options

    async def send_user_message(self, content: object, options: object | None = None) -> None:
        await self.sendUserMessage(content, options)

    def setSessionName(self, name: str | None) -> None:
        del name

    def set_session_name(self, name: str | None) -> None:
        self.setSessionName(name)

    def getSessionName(self) -> str | None:
        return None

    def get_session_name(self) -> str | None:
        return self.getSessionName()

    def setLabel(self, entry_id: str, label: str | None) -> None:
        del entry_id, label

    def set_label(self, entry_id: str, label: str | None) -> None:
        self.setLabel(entry_id, label)

    def listCommands(self):
        return []

    def list_commands(self):
        return self.listCommands()

    def request_resource_refresh(self) -> None:
        return None

    def abort(self) -> None:
        return None

    def isIdle(self) -> bool:
        return True

    def is_idle(self) -> bool:
        return self.isIdle()

    def hasPendingMessages(self) -> bool:
        return False

    def has_pending_messages(self) -> bool:
        return self.hasPendingMessages()

    def get_context_usage(self) -> object | None:
        return None

    async def compact(self, options: object | None = None) -> object | None:
        del options
        return None

    def getSystemPrompt(self) -> str:
        return ""

    def get_system_prompt(self) -> str:
        return self.getSystemPrompt()

    async def waitForIdle(self) -> None:
        return None

    async def wait_for_idle(self) -> None:
        await self.waitForIdle()

    async def reload(self) -> None:
        return None

    async def navigateTree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        del target_id, options
        return {"cancelled": False}

    async def navigate_tree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        return await self.navigateTree(target_id, options)

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]:
        del entry_id, options
        return {"cancelled": True}

    async def newSession(self, options: object | None = None) -> dict[str, object]:
        del options
        return {"cancelled": True}

    async def new_session(self, options: object | None = None) -> dict[str, object]:
        return await self.newSession(options)

    async def switchSession(self, session_path: str, options: object | None = None) -> dict[str, object]:
        del session_path, options
        return {"cancelled": True}

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]:
        return await self.switchSession(session_path, options)

    def shutdown(self) -> None:
        return None

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None:
        del diagnostic

    def notify(self, message: str, notify_type: str | None = None) -> None:
        del message, notify_type

    def set_status(self, key: str, text: str | None) -> None:
        del key, text

    def setStatus(self, key: str, text: str | None) -> None:
        self.set_status(key, text)

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        del key, lines, placement

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        self.set_widget(key, lines, placement=placement)

    def set_title(self, title: str) -> None:
        del title

    def setTitle(self, title: str) -> None:
        self.set_title(title)

    def set_editor_text(self, text: str) -> None:
        del text

    def setEditorText(self, text: str) -> None:
        self.set_editor_text(text)

    def pasteToEditor(self, text: str) -> None:
        self.set_editor_text(text)

    def getEditorText(self) -> str:
        return ""

    def onTerminalInput(self, handler: Callable[[str], None]) -> Callable[[], None]:
        del handler
        return lambda: None

    def setWorkingMessage(self, message: str | None = None) -> None:
        del message

    def setWorkingVisible(self, visible: bool) -> None:
        del visible

    def setWorkingIndicator(self, options: object | None = None) -> None:
        del options

    def setHiddenThinkingLabel(self, label: str | None = None) -> None:
        del label

    def setFooter(self, factory: object | None) -> None:
        del factory

    def setHeader(self, factory: object | None) -> None:
        del factory

    def addAutocompleteProvider(self, factory: object) -> None:
        del factory

    def setEditorComponent(self, factory: object | None) -> None:
        del factory

    def getAllThemes(self) -> list[object]:
        return []

    def getTheme(self, name: str) -> object | None:
        del name
        return None

    def setTheme(self, theme: object) -> dict[str, object]:
        del theme
        return {"success": False, "error": "Theme switching not supported in RPC mode"}

    def getToolsExpanded(self) -> bool:
        return False

    def setToolsExpanded(self, expanded: bool) -> None:
        del expanded

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None:
        del title, options, timeout
        return None

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool:
        del title, message, timeout
        return False

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None:
        del title, placeholder, timeout
        return None

    async def editor(self, title: str, prefill: str | None = None) -> str | None:
        del title, prefill
        return None


@dataclass
class _RunnerRuntimeState:
    bindings: object | None = None
    flag_values: dict[str, bool | str] = field(default_factory=dict)
    generation: int = 0
    stale_message: str = "Extension context is stale after session replacement or reload."


@dataclass(frozen=True)
class _StaticExtensionContext:
    cwd: str

    @property
    def ui(self) -> "_StaticExtensionContext":
        return self

    @property
    def hasUI(self) -> bool:
        return False

    @property
    def has_ui(self) -> bool:
        return self.hasUI

    @property
    def sessionManager(self) -> object | None:
        return None

    @property
    def session_manager(self) -> object | None:
        return self.sessionManager

    @property
    def modelRegistry(self) -> object | None:
        return None

    @property
    def model_registry(self) -> object | None:
        return self.modelRegistry

    @property
    def model(self) -> object | None:
        return None

    @property
    def signal(self) -> object | None:
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
        del command, args, cwd, env, timeout_seconds, stdin, signal, on_update
        del preview_max_lines, preview_max_bytes, artifact_dir, capture_full_output, rolling_max_bytes
        raise RuntimeError("Extension runtime is not bound.")

    def get_active_tool_names(self) -> list[str]:
        return []

    def getActiveTools(self) -> list[str]:
        return self.get_active_tool_names()

    def getAllTools(self) -> list[object]:
        return []

    def get_all_tools(self) -> list[object]:
        return self.getAllTools()

    def register_tool(self, tool: object) -> None:
        del tool

    def registerTool(self, tool: object) -> None:
        self.register_tool(tool)

    def getFlag(self, name: str) -> bool | str | None:
        return self._runtime_state.flag_values.get(name)

    def get_flag(self, name: str) -> bool | str | None:
        return self.getFlag(name)

    def get_model_selection(self):
        return None

    async def set_active_tools(self, tool_names: list[str]) -> None:
        del tool_names

    async def setActiveTools(self, tool_names: list[str]) -> None:
        await self.set_active_tools(tool_names)

    async def set_model(self, selection) -> None:
        del selection

    def appendEntry(self, custom_type: str, data: object | None = None) -> None:
        del custom_type, data

    def append_entry(self, custom_type: str, data: object | None = None) -> None:
        self.appendEntry(custom_type, data)

    async def sendMessage(self, message: object, options: object | None = None) -> None:
        del message, options

    async def send_message(self, message: object, options: object | None = None) -> None:
        await self.sendMessage(message, options)

    async def sendUserMessage(self, content: object, options: object | None = None) -> None:
        del content, options

    async def send_user_message(self, content: object, options: object | None = None) -> None:
        await self.sendUserMessage(content, options)

    def setSessionName(self, name: str | None) -> None:
        del name

    def set_session_name(self, name: str | None) -> None:
        self.setSessionName(name)

    def getSessionName(self) -> str | None:
        return None

    def get_session_name(self) -> str | None:
        return self.getSessionName()

    def setLabel(self, entry_id: str, label: str | None) -> None:
        del entry_id, label

    def set_label(self, entry_id: str, label: str | None) -> None:
        self.setLabel(entry_id, label)

    def listCommands(self):
        return []

    def list_commands(self):
        return self.listCommands()

    def request_resource_refresh(self) -> None:
        return None

    def abort(self) -> None:
        return None

    def isIdle(self) -> bool:
        return True

    def is_idle(self) -> bool:
        return self.isIdle()

    def hasPendingMessages(self) -> bool:
        return False

    def has_pending_messages(self) -> bool:
        return self.hasPendingMessages()

    def get_context_usage(self) -> object | None:
        return None

    async def compact(self, options: object | None = None) -> object | None:
        del options
        return None

    def getSystemPrompt(self) -> str:
        return ""

    def get_system_prompt(self) -> str:
        return self.getSystemPrompt()

    async def waitForIdle(self) -> None:
        return None

    async def wait_for_idle(self) -> None:
        await self.waitForIdle()

    async def reload(self) -> None:
        return None

    async def navigateTree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        del target_id, options
        return {"cancelled": False}

    async def navigate_tree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        return await self.navigateTree(target_id, options)

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]:
        del entry_id, options
        return {"cancelled": True}

    async def newSession(self, options: object | None = None) -> dict[str, object]:
        del options
        return {"cancelled": True}

    async def new_session(self, options: object | None = None) -> dict[str, object]:
        return await self.newSession(options)

    async def switchSession(self, session_path: str, options: object | None = None) -> dict[str, object]:
        del session_path, options
        return {"cancelled": True}

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]:
        return await self.switchSession(session_path, options)

    def shutdown(self) -> None:
        return None

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None:
        del diagnostic

    def notify(self, message: str, notify_type: str | None = None) -> None:
        del message, notify_type

    def set_status(self, key: str, text: str | None) -> None:
        del key, text

    def setStatus(self, key: str, text: str | None) -> None:
        self.set_status(key, text)

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        del key, lines, placement

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        self.set_widget(key, lines, placement=placement)

    def set_title(self, title: str) -> None:
        del title

    def setTitle(self, title: str) -> None:
        self.set_title(title)

    def set_editor_text(self, text: str) -> None:
        del text

    def setEditorText(self, text: str) -> None:
        self.set_editor_text(text)

    def pasteToEditor(self, text: str) -> None:
        self.set_editor_text(text)

    def getEditorText(self) -> str:
        return ""

    def onTerminalInput(self, handler: Callable[[str], None]) -> Callable[[], None]:
        del handler
        return lambda: None

    def setWorkingMessage(self, message: str | None = None) -> None:
        del message

    def setWorkingVisible(self, visible: bool) -> None:
        del visible

    def setWorkingIndicator(self, options: object | None = None) -> None:
        del options

    def setHiddenThinkingLabel(self, label: str | None = None) -> None:
        del label

    def setFooter(self, factory: object | None) -> None:
        del factory

    def setHeader(self, factory: object | None) -> None:
        del factory

    def addAutocompleteProvider(self, factory: object) -> None:
        del factory

    def setEditorComponent(self, factory: object | None) -> None:
        del factory

    def getAllThemes(self) -> list[object]:
        return []

    def getTheme(self, name: str) -> object | None:
        del name
        return None

    def setTheme(self, theme: object) -> dict[str, object]:
        del theme
        return {"success": False, "error": "Theme switching not supported in RPC mode"}

    def getToolsExpanded(self) -> bool:
        return False

    def setToolsExpanded(self, expanded: bool) -> None:
        del expanded

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None:
        del title, options, timeout
        return None

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool:
        del title, message, timeout
        return False

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None:
        del title, placeholder, timeout
        return None

    async def editor(self, title: str, prefill: str | None = None) -> str | None:
        del title, prefill
        return None


class _BoundExtensionContext:
    def __init__(
        self,
        runtime_state: _RunnerRuntimeState,
        generation: int,
        tool_source_info: SourceInfo | None = None,
    ) -> None:
        self._runtime_state = runtime_state
        self._generation = generation
        self._tool_source_info = tool_source_info

    @property
    def ui(self) -> "_BoundExtensionContext":
        return self

    @property
    def hasUI(self) -> bool:
        return self._ui_context() is not None

    @property
    def has_ui(self) -> bool:
        return self.hasUI

    @property
    def cwd(self) -> str:
        return str(self._require_bindings().cwd)

    @property
    def sessionManager(self) -> object | None:
        return self._require_bindings().session_manager

    @property
    def session_manager(self) -> object | None:
        return self.sessionManager

    @property
    def modelRegistry(self) -> object | None:
        return self._require_bindings().model_registry

    @property
    def model_registry(self) -> object | None:
        return self.modelRegistry

    @property
    def model(self) -> object | None:
        return self.get_model_selection()

    @property
    def signal(self) -> object | None:
        return self._require_bindings().get_signal()

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
        callback = self._require_bindings().exec_command
        if callback is None:
            raise RuntimeError("Extension runtime does not provide exec_command.")
        return await callback(
            command,
            _normalize_exec_args(args),
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

    def get_active_tool_names(self) -> list[str]:
        return list(self._require_bindings().get_active_tool_names())

    def getActiveTools(self) -> list[str]:
        return self.get_active_tool_names()

    def getAllTools(self) -> list[object]:
        return list(self._require_bindings().get_all_tools())

    def get_all_tools(self) -> list[object]:
        return self.getAllTools()

    def register_tool(self, tool: object) -> None:
        self._require_bindings().register_tool(tool, self._tool_source_info)

    def registerTool(self, tool: object) -> None:
        self.register_tool(tool)

    def get_model_selection(self):
        return self._require_bindings().get_model_selection()

    async def set_active_tools(self, tool_names: list[str]) -> None:
        await self._require_bindings().set_active_tools(list(tool_names))

    async def setActiveTools(self, tool_names: list[str]) -> None:
        await self.set_active_tools(tool_names)

    async def set_model(self, selection) -> None:
        await self._require_bindings().set_model(selection)

    async def setModel(self, selection) -> None:
        await self.set_model(selection)

    def getThinkingLevel(self) -> str:
        return str(self._require_bindings().get_thinking_level())

    def get_thinking_level(self) -> str:
        return self.getThinkingLevel()

    def setThinkingLevel(self, level: str) -> None:
        self._require_bindings().set_thinking_level(level)

    def set_thinking_level(self, level: str) -> None:
        self.setThinkingLevel(level)

    def appendEntry(self, custom_type: str, data: object | None = None) -> None:
        self._require_bindings().append_entry(custom_type, data)

    def append_entry(self, custom_type: str, data: object | None = None) -> None:
        self.appendEntry(custom_type, data)

    async def sendMessage(self, message: object, options: object | None = None) -> None:
        callback = self._require_bindings().send_message
        if callback is None:
            return None
        await callback(message, options)
        return None

    async def send_message(self, message: object, options: object | None = None) -> None:
        await self.sendMessage(message, options)

    async def sendUserMessage(self, content: object, options: object | None = None) -> None:
        callback = self._require_bindings().send_user_message
        if callback is None:
            return None
        await callback(content, options)
        return None

    async def send_user_message(self, content: object, options: object | None = None) -> None:
        await self.sendUserMessage(content, options)

    def setSessionName(self, name: str | None) -> None:
        self._require_bindings().set_session_name(name)

    def set_session_name(self, name: str | None) -> None:
        self.setSessionName(name)

    def getSessionName(self) -> str | None:
        return self._require_bindings().get_session_name()

    def get_session_name(self) -> str | None:
        return self.getSessionName()

    def setLabel(self, entry_id: str, label: str | None) -> None:
        self._require_bindings().set_label(entry_id, label)

    def set_label(self, entry_id: str, label: str | None) -> None:
        self.setLabel(entry_id, label)

    def listCommands(self):
        return list(self._require_bindings().list_commands())

    def list_commands(self):
        return self.listCommands()

    def request_resource_refresh(self) -> None:
        self._require_bindings().request_resource_refresh()

    def abort(self) -> None:
        self._require_bindings().abort()

    def isIdle(self) -> bool:
        return bool(self._require_bindings().is_idle())

    def is_idle(self) -> bool:
        return self.isIdle()

    def hasPendingMessages(self) -> bool:
        return bool(self._require_bindings().has_pending_messages())

    def has_pending_messages(self) -> bool:
        return self.hasPendingMessages()

    def get_context_usage(self) -> object | None:
        return self._require_bindings().get_context_usage()

    async def compact(self, options: object | None = None) -> object | None:
        callback = self._require_bindings().compact
        if callback is None:
            return None
        return await callback(_compact_custom_instructions(options))

    def getSystemPrompt(self) -> str:
        return str(self._require_bindings().get_system_prompt())

    def get_system_prompt(self) -> str:
        return self.getSystemPrompt()

    async def waitForIdle(self) -> None:
        callback = self._require_bindings().wait_for_idle
        if callback is None:
            return None
        await callback()
        return None

    async def wait_for_idle(self) -> None:
        await self.waitForIdle()

    async def reload(self) -> None:
        callback = self._require_bindings().reload
        if callback is None:
            return None
        await callback()
        return None

    async def navigateTree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        callback = self._require_bindings().navigate_tree
        if callback is None:
            return {"cancelled": False}
        result = await callback(target_id, options)
        return result if isinstance(result, dict) else {"cancelled": False}

    async def navigate_tree(self, target_id: str, options: object | None = None) -> dict[str, object]:
        return await self.navigateTree(target_id, options)

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]:
        callback = self._require_bindings().fork
        if callback is None:
            return {"cancelled": True}
        result = await callback(entry_id, options)
        return result if isinstance(result, dict) else {"cancelled": False}

    async def newSession(self, options: object | None = None) -> dict[str, object]:
        callback = self._require_bindings().new_session
        if callback is None:
            return {"cancelled": True}
        result = await callback(options)
        return result if isinstance(result, dict) else {"cancelled": False}

    async def new_session(self, options: object | None = None) -> dict[str, object]:
        return await self.newSession(options)

    async def switchSession(self, session_path: str, options: object | None = None) -> dict[str, object]:
        callback = self._require_bindings().switch_session
        if callback is None:
            return {"cancelled": True}
        result = await callback(session_path, options)
        return result if isinstance(result, dict) else {"cancelled": False}

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]:
        return await self.switchSession(session_path, options)

    def shutdown(self) -> None:
        self._require_bindings().shutdown()

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None:
        self._require_bindings().record_diagnostic(diagnostic)

    def notify(self, message: str, notify_type: str | None = None) -> None:
        ui = self._ui_context()
        if ui is not None:
            ui.notify(message, notify_type)

    def set_status(self, key: str, text: str | None) -> None:
        setter = getattr(self._require_bindings(), "set_extension_status", None)
        if callable(setter):
            setter(key, text)
        ui = self._ui_context()
        if ui is not None:
            ui.set_status(key, text)

    def setStatus(self, key: str, text: str | None) -> None:
        self.set_status(key, text)

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        ui = self._ui_context()
        if ui is not None:
            ui.set_widget(key, lines, placement=placement)

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        self.set_widget(key, lines, placement=placement)

    def set_title(self, title: str) -> None:
        ui = self._ui_context()
        if ui is not None:
            ui.set_title(title)

    def setTitle(self, title: str) -> None:
        self.set_title(title)

    def set_editor_text(self, text: str) -> None:
        ui = self._ui_context()
        if ui is not None:
            ui.set_editor_text(text)

    def setEditorText(self, text: str) -> None:
        self.set_editor_text(text)

    def pasteToEditor(self, text: str) -> None:
        self.set_editor_text(text)

    def getEditorText(self) -> str:
        ui = self._ui_context()
        getter = getattr(ui, "getEditorText", None) if ui is not None else None
        return getter() if callable(getter) else ""

    def onTerminalInput(self, handler: Callable[[str], None]) -> Callable[[], None]:
        ui = self._ui_context()
        listener = getattr(ui, "onTerminalInput", None) if ui is not None else None
        return listener(handler) if callable(listener) else (lambda: None)

    def setWorkingMessage(self, message: str | None = None) -> None:
        self._call_ui_noop("setWorkingMessage", message)

    def setWorkingVisible(self, visible: bool) -> None:
        self._call_ui_noop("setWorkingVisible", visible)

    def setWorkingIndicator(self, options: object | None = None) -> None:
        self._call_ui_noop("setWorkingIndicator", options)

    def setHiddenThinkingLabel(self, label: str | None = None) -> None:
        self._call_ui_noop("setHiddenThinkingLabel", label)

    def setFooter(self, factory: object | None) -> None:
        self._call_ui_noop("setFooter", factory)

    def setHeader(self, factory: object | None) -> None:
        self._call_ui_noop("setHeader", factory)

    def addAutocompleteProvider(self, factory: object) -> None:
        self._call_ui_noop("addAutocompleteProvider", factory)

    def setEditorComponent(self, factory: object | None) -> None:
        self._call_ui_noop("setEditorComponent", factory)

    def getAllThemes(self) -> list[object]:
        ui = self._ui_context()
        getter = getattr(ui, "getAllThemes", None) if ui is not None else None
        value = getter() if callable(getter) else []
        return list(value) if isinstance(value, list) else []

    def getTheme(self, name: str) -> object | None:
        ui = self._ui_context()
        getter = getattr(ui, "getTheme", None) if ui is not None else None
        return getter(name) if callable(getter) else None

    def setTheme(self, theme: object) -> dict[str, object]:
        ui = self._ui_context()
        setter = getattr(ui, "setTheme", None) if ui is not None else None
        value = setter(theme) if callable(setter) else None
        if isinstance(value, dict):
            return value
        return {"success": False, "error": "Theme switching not supported in RPC mode"}

    def getToolsExpanded(self) -> bool:
        ui = self._ui_context()
        getter = getattr(ui, "getToolsExpanded", None) if ui is not None else None
        return bool(getter()) if callable(getter) else False

    def setToolsExpanded(self, expanded: bool) -> None:
        self._call_ui_noop("setToolsExpanded", expanded)

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None:
        ui = self._ui_context()
        return await ui.select(title, options, timeout=timeout) if ui is not None else None

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool:
        ui = self._ui_context()
        return await ui.confirm(title, message, timeout=timeout) if ui is not None else False

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None:
        ui = self._ui_context()
        return await ui.input(title, placeholder, timeout=timeout) if ui is not None else None

    async def editor(self, title: str, prefill: str | None = None) -> str | None:
        ui = self._ui_context()
        return await ui.editor(title, prefill) if ui is not None else None

    def _require_bindings(self):
        if self._generation != self._runtime_state.generation:
            raise RuntimeError(self._runtime_state.stale_message)
        bindings = self._runtime_state.bindings
        if bindings is None:
            raise RuntimeError("Extension runner runtime bindings have not been set.")
        return bindings

    def _ui_context(self):
        return getattr(self._require_bindings(), "ui_context", None)

    def _call_ui_noop(self, method_name: str, *args: object) -> None:
        ui = self._ui_context()
        method = getattr(ui, method_name, None) if ui is not None else None
        if callable(method):
            method(*args)


@dataclass(frozen=True)
class _BeforeAgentStartContext:
    base: ExtensionContext
    get_system_prompt: Callable[[], str]

    def __getattr__(self, name: str):
        return getattr(self.base, name)

    @property
    def ui(self):
        return self.base.ui

    @property
    def hasUI(self) -> bool:
        return self.base.hasUI

    @property
    def has_ui(self) -> bool:
        return self.base.has_ui

    @property
    def cwd(self) -> str:
        return self.base.cwd

    def getSystemPrompt(self) -> str:
        return self.get_system_prompt()


@dataclass
class _ContextEvent:
    messages: list[AgentMessage]


class ExtensionRunner:
    def __init__(self, extensions: list[LoadedExtension | ExtensionDescriptor] | None = None) -> None:
        self._diagnostics: list[ResourceDiagnostic] = []
        self._extensions: list[LoadedExtension] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_source_info_by_name: dict[str, SourceInfo] = {}
        self._tool_names: set[str] = set()
        self._command_diagnostics: list[ResourceDiagnostic] = []
        self._flag_diagnostics: list[ResourceDiagnostic] = []
        self._shortcut_diagnostics: list[ResourceDiagnostic] = []
        self._registered_commands: list[ResolvedCommand] = []
        self._registered_commands_by_invocation_name: dict[str, ResolvedCommand] = {}
        self._resolved_flags: list[ResolvedFlag] = []
        self._resolved_shortcuts: list[ResolvedShortcut] = []
        self._runtime_state = _RunnerRuntimeState()
        loader = ExtensionLoader()

        for extension in extensions or []:
            if isinstance(extension, ExtensionDescriptor):
                loaded_extension = loader.load_extension(extension)
                self._diagnostics.extend(loader.get_diagnostics())
                loader = ExtensionLoader()
                if loaded_extension is None:
                    continue
            else:
                loaded_extension = extension
            self._extensions.append(loaded_extension)
            self._bind_extension_api(loaded_extension)
            self._diagnostics.extend(loaded_extension.diagnostics)
            self._collect_tools(loaded_extension)

        self._build_registry_views()

    def get_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._diagnostics)

    def get_command_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._command_diagnostics)

    def get_flag_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._flag_diagnostics)

    def get_shortcut_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._shortcut_diagnostics)

    def get_registered_commands(self) -> list[ResolvedCommand]:
        return list(self._registered_commands)

    def get_command(self, invocation_name: str) -> ResolvedCommand | None:
        return self._registered_commands_by_invocation_name.get(invocation_name)

    def _extension_by_name(self, name: str) -> LoadedExtension:
        for extension in self._extensions:
            if extension.name == name:
                return extension
        return LoadedExtension(name=name, source_path=Path("<unknown>"))

    async def get_command_argument_completions(self, invocation_name: str, prefix: str) -> list[object] | None:
        command = self.get_command(invocation_name)
        if command is None or command.get_argument_completions is None:
            return None
        try:
            result = command.get_argument_completions(prefix)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="extension_command_argument_completions_failed",
                    message=f"Extension command argument completions failed: {exc}",
                    source_path=command.source_info.path,
                )
            )
            self._emit_runtime_error(
                extension=self._extension_by_name(command.extension_name),
                event="command_argument_completions",
                error=exc,
            )
            return None
        if result is None:
            return None
        if not isinstance(result, list):
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="invalid_extension_command_argument_completions",
                    message="Command argument completions must return a list or None.",
                    source_path=command.source_info.path,
                )
            )
            return None
        return result

    def get_flags(self) -> list[ResolvedFlag]:
        return list(self._resolved_flags)

    def get_shortcuts(self) -> list[ResolvedShortcut]:
        return list(self._resolved_shortcuts)

    def set_flag_value(self, name: str, value: bool | str) -> None:
        self._runtime_state.flag_values[name] = value

    def get_flag_values(self) -> dict[str, bool | str]:
        return dict(self._runtime_state.flag_values)

    def create_command_context(self, *, fallback_cwd: str = "") -> ExtensionCommandContext:
        return self._context_from_runtime(fallback_cwd=fallback_cwd)

    def has_handlers(self, hook_name: str) -> bool:
        return any(extension.hooks.get(hook_name) for extension in self._extensions)

    async def emit_before_provider_request(self, payload: object, *, cwd: str = "") -> object:
        context = self._context_from_runtime(fallback_cwd=cwd)
        current_payload = payload
        for extension in self._extensions:
            for handler in extension.hooks.get("before_provider_request", []):
                try:
                    event = _ExtensionEvent(type="before_provider_request", payload=current_payload)
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                    if result is not None:
                        current_payload = result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_before_provider_request_failed",
                            message=f"Extension hook 'before_provider_request' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="before_provider_request", error=exc)
        return current_payload

    async def emit_after_provider_response(self, response: object, *, cwd: str = "") -> None:
        context = self._context_from_runtime(fallback_cwd=cwd)
        status = _safe_get_value(response, "status")
        headers = _normalize_provider_response_headers(_safe_get_value(response, "headers"))
        event = _ExtensionEvent(type="after_provider_response", response=response, status=status, headers=headers)
        for extension in self._extensions:
            for handler in extension.hooks.get("after_provider_response", []):
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_after_provider_response_failed",
                            message=f"Extension hook 'after_provider_response' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="after_provider_response", error=exc)

    async def emit_user_bash(self, event: object, *, cwd: str = "") -> object | None:
        context = self._context_from_runtime(fallback_cwd=cwd)
        event_object = _event_object(event)
        for extension in self._extensions:
            for handler in extension.hooks.get("user_bash", []):
                try:
                    result = handler(event_object, context)
                    if inspect.isawaitable(result):
                        result = await result
                    if result:
                        return result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_user_bash_failed",
                            message=f"Extension hook 'user_bash' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="user_bash", error=exc)
        return None

    async def emit_event(self, event: object, *, cwd: str = "") -> None:
        event_type = _event_type(event)
        if event_type is None:
            return
        context = self._context_from_runtime(fallback_cwd=cwd)
        event_object = _event_object(event)
        for extension in self._extensions:
            for handler in extension.hooks.get(event_type, []):
                try:
                    result = handler(event_object, context)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code=f"extension_{event_type}_failed",
                            message=f"Extension hook '{event_type}' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event=event_type, error=exc)

    async def emit_input(
        self,
        text: str,
        images: list[object] | None = None,
        *,
        source: str = "interactive",
        cwd: str = "",
    ) -> InputEventResult:
        context = self._context_from_runtime(fallback_cwd=cwd)
        current_text = text
        current_images = images
        transformed = False
        for extension in self._extensions:
            for handler in extension.hooks.get("input", []):
                event = InputEvent(text=current_text, images=current_images, source=_normalize_input_source(source))
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._diagnostics.append(
                        _extension_hook_failure_diagnostic(
                            extension=extension,
                            hook_name="input",
                            exc=exc,
                            code="extension_input_failed",
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="input", error=exc)
                    continue
                action, result_text, result_images = _coerce_input_result(result)
                if action in {None, "continue"}:
                    continue
                if action == "handled":
                    return InputEventResult(action="handled", text=current_text, images=current_images)
                if action == "transform":
                    if result_text is None:
                        self._diagnostics.append(
                            ResourceDiagnostic(
                                code="invalid_extension_input_result",
                                message="input transform results must include string text.",
                                source_path=extension.source_path,
                            )
                        )
                        continue
                    current_text = result_text
                    if result_images is not None:
                        current_images = result_images
                    transformed = True
                    continue
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_input_result",
                        message="input hooks must return action 'continue', 'transform', 'handled', or None.",
                        source_path=extension.source_path,
                    )
                )
        if transformed or current_text != text or current_images is not images:
            return InputEventResult(action="transform", text=current_text, images=current_images)
        return InputEventResult(action="continue", text=current_text, images=current_images)

    def list_tool_definitions(self) -> list[ToolDefinition]:
        return list(self._tool_definitions)

    def get_tool_source_info(self, name: str) -> SourceInfo | None:
        return self._tool_source_info_by_name.get(name)

    def get_message_renderer(self, custom_type: str):
        for extension in self._extensions:
            renderer = extension.message_renderers.get(custom_type)
            if renderer is not None:
                return renderer
        return None

    def getMessageRenderer(self, custom_type: str):
        return self.get_message_renderer(custom_type)

    def list_message_renderers(self) -> list[dict[str, object]]:
        renderers: list[dict[str, object]] = []
        for extension in self._extensions:
            source_info = _source_info_from_extension(extension)
            for custom_type in extension.message_renderers:
                renderers.append(
                    {
                        "custom_type": custom_type,
                        "customType": custom_type,
                        "extension_name": extension.name,
                        "extensionName": extension.name,
                        "source_info": _serialize_source_info(source_info),
                        "sourceInfo": _serialize_source_info(source_info),
                    }
                )
        return renderers

    def listMessageRenderers(self) -> list[dict[str, object]]:
        return self.list_message_renderers()

    def get_diagnostic_snapshot(self) -> dict[str, object]:
        return {
            "total": len(self._diagnostics),
            "commands": len(self._command_diagnostics),
            "flags": len(self._flag_diagnostics),
            "shortcuts": len(self._shortcut_diagnostics),
            "diagnostics": [
                {
                    "code": diagnostic.code,
                    "message": diagnostic.message,
                    "sourcePath": diagnostic.source_path.as_posix() if diagnostic.source_path is not None else None,
                    "resourceId": diagnostic.resource_id,
                    "resourceType": diagnostic.resource_type,
                    "sourceKind": diagnostic.source_kind,
                    "metadata": dict(diagnostic.metadata),
                }
                for diagnostic in self._diagnostics
            ],
        }

    def list_extensions(self) -> list[dict[str, object]]:
        return [
            _extension_visibility_snapshot(extension, diagnostics=self._diagnostics)
            for extension in self._extensions
        ]

    def listExtensions(self) -> list[dict[str, object]]:
        return self.list_extensions()

    def discover_resources(self, bundle: ResourceBundle, *, reason: str = "refresh") -> ResourceBundle:
        del reason
        merged = bundle
        diagnostics: list[ResourceDiagnostic] = []
        context = _RunnerContext(cwd=str(bundle.cwd))
        for extension in self._extensions:
            handlers = extension.hooks.get("resources_discover", [])
            try:
                merged = self._apply_resource_handlers(
                    extension=extension,
                    handlers=handlers,
                    bundle=merged,
                    context=context,
                    diagnostics=diagnostics,
                )
            except Exception as exc:  # defensive fallback
                diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_resources_discover_failed",
                        message=f"Extension resource discovery failed: {exc}",
                        source_path=extension.source_path,
                    )
                )

        if diagnostics:
            self._diagnostics.extend(diagnostics)
            merged = merged.merge(diagnostics=diagnostics)
        return merged

    async def discover_resources_async(self, bundle: ResourceBundle, *, reason: str = "refresh") -> ResourceBundle:
        del reason
        merged = bundle
        diagnostics: list[ResourceDiagnostic] = []
        context = _RunnerContext(cwd=str(bundle.cwd))
        for extension in self._extensions:
            handlers = extension.hooks.get("resources_discover", [])
            try:
                merged = await self._apply_resource_handlers_async(
                    extension=extension,
                    handlers=handlers,
                    bundle=merged,
                    context=context,
                    diagnostics=diagnostics,
                )
            except Exception as exc:  # defensive fallback
                diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_resources_discover_failed",
                        message=f"Extension resource discovery failed: {exc}",
                        source_path=extension.source_path,
                    )
                )

        if diagnostics:
            self._diagnostics.extend(diagnostics)
            merged = merged.merge(diagnostics=diagnostics)
        return merged

    def bind_runtime(self, bindings: ExtensionRuntimeBindings) -> None:
        self._runtime_state.bindings = bindings
        self._bind_extension_apis()

    def refresh_runtime(self, bindings: ExtensionRuntimeBindings) -> None:
        self._runtime_state.bindings = bindings
        self._bind_extension_apis()

    def _bind_extension_apis(self) -> None:
        for extension in self._extensions:
            self._bind_extension_api(extension)

    def _bind_extension_api(self, extension: LoadedExtension) -> None:
        binder = getattr(extension.api, "bind_runtime_state", None)
        if callable(binder):
            binder(self._runtime_state)

    def invalidate_contexts(
        self,
        message: str = "Extension context is stale after session replacement or reload.",
    ) -> None:
        self._runtime_state.generation += 1
        self._runtime_state.stale_message = message

    async def emit_session_start(self, session: object) -> None:
        await self._emit_session_hook("session_start", session)

    async def emit_session_refresh(self, event: SessionRefreshEvent) -> None:
        await self._emit_session_hook("session_refresh", event)

    async def emit_before_agent_start(
        self,
        *,
        prompt: str,
        images: list[object] | None = None,
        system_prompt: str | None = None,
        system_prompt_options: object | None = None,
        cwd: str = "",
    ) -> BeforeAgentStartResult | None:
        context = self._context_from_runtime(fallback_cwd=cwd)
        current_system_prompt = system_prompt or ""
        extra_messages: list[object] = []
        diagnostics: list[ResourceDiagnostic] = []
        system_prompt_changed = False

        context = _BeforeAgentStartContext(base=context, get_system_prompt=lambda: current_system_prompt)

        for extension in self._extensions:
            for handler in extension.hooks.get("before_agent_start", []):
                event = _ExtensionEvent(
                    type="before_agent_start",
                    prompt=prompt,
                    images=images,
                    system_prompt=current_system_prompt,
                    systemPrompt=current_system_prompt,
                    system_prompt_options=system_prompt_options,
                    systemPromptOptions=system_prompt_options,
                )
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_before_agent_start_failed",
                            message=f"Extension hook 'before_agent_start' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="before_agent_start", error=exc)
                    continue
                coerced = _coerce_before_agent_start_result(result)
                if coerced is None:
                    continue
                if coerced.diagnostics:
                    diagnostics.extend(coerced.diagnostics)
                if coerced.extra_messages:
                    extra_messages.extend(coerced.extra_messages)
                next_system_prompt = coerced.system_prompt
                if next_system_prompt is None and coerced.system_prompt_append:
                    next_system_prompt = f"{current_system_prompt}\n\n{coerced.system_prompt_append}"
                if next_system_prompt is not None:
                    current_system_prompt = next_system_prompt
                    system_prompt_changed = True

        if diagnostics:
            self._diagnostics.extend(diagnostics)
        if not extra_messages and not system_prompt_changed and not diagnostics:
            return None
        return BeforeAgentStartResult(
            system_prompt=current_system_prompt if system_prompt_changed else None,
            extra_messages=extra_messages,
            diagnostics=diagnostics,
        )

    async def emit_session_shutdown(self, session: object) -> None:
        await self._emit_session_hook("session_shutdown", session)

    async def before_session_switch(self, event: object) -> SessionActionDecision | None:
        return await self._emit_decision_hook("session_before_switch", event, fallback_cwd=getattr(event, "cwd", ""))

    async def before_session_fork(self, event: object) -> SessionBeforeForkResult | None:
        result = await self._emit_decision_hook(
            "session_before_fork",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeForkResult):
            return result
        return SessionBeforeForkResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def before_session_compact(self, event: object) -> SessionBeforeCompactResult | None:
        result = await self._emit_decision_hook(
            "session_before_compact",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeCompactResult):
            return result
        return SessionBeforeCompactResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def before_session_tree(self, event: object) -> SessionBeforeTreeResult | None:
        result = await self._emit_decision_hook(
            "session_before_tree",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeTreeResult):
            return result
        return SessionBeforeTreeResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def emit_context(
        self,
        messages: list[AgentMessage],
        signal: object | None = None,
        *,
        cwd: str = "",
    ) -> list[AgentMessage]:
        del signal

        current_messages = deepcopy(messages)
        context = self._context_from_runtime(fallback_cwd=cwd)
        for extension in self._extensions:
            for handler in extension.hooks.get("context", []):
                event = _ContextEvent(messages=current_messages)
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_context_failed",
                            message=f"Extension hook 'context' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="context", error=exc)
                    continue
                if result is None:
                    continue
                if not isinstance(result, ContextResult):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_context_result",
                            message="context hooks must return ContextResult or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if result.diagnostics:
                    self._diagnostics.extend(result.diagnostics)
                if result.messages is not None:
                    current_messages = result.messages
        return current_messages

    async def before_tool_call(self, event, signal: object | None = None) -> BeforeToolCallResult | None:
        current_event = event
        changed = False
        context = self._context_from_runtime(fallback_cwd=_context_from_agent_event(event).cwd)
        for extension in self._extensions:
            for handler in extension.hooks.get("tool_call", []):
                try:
                    decision = handler(current_event, context)
                    if inspect.isawaitable(decision):
                        decision = await decision
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_tool_call_failed",
                            message=f"Extension hook 'tool_call' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="tool_call", error=exc)
                    continue
                if decision is None:
                    continue
                if not isinstance(decision, ToolCallDecision):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_call_decision",
                            message="tool_call hooks must return ToolCallDecision or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if decision.diagnostics:
                    self._diagnostics.extend(decision.diagnostics)
                rewritten_tool_name = decision.tool_name or current_event.tool_call.name
                rewritten_arguments = decision.arguments if decision.arguments is not None else current_event.args
                if rewritten_tool_name != current_event.tool_call.name or rewritten_arguments != current_event.args:
                    changed = True
                    current_event = replace(
                        current_event,
                        tool_call=ToolCall(
                            type="toolCall",
                            id=current_event.tool_call.id,
                            name=rewritten_tool_name,
                            arguments=rewritten_arguments,
                            thought_signature=current_event.tool_call.thought_signature,
                        ),
                        args=rewritten_arguments,
                    )
                if decision.block:
                    return BeforeToolCallResult(
                        block=True,
                        reason=decision.reason,
                        tool_name=current_event.tool_call.name if changed else None,
                        arguments=current_event.args if changed else None,
                    )
        if not changed:
            return None
        return BeforeToolCallResult(
            tool_name=current_event.tool_call.name,
            arguments=current_event.args,
        )

    async def after_tool_call(self, event, signal: object | None = None) -> AfterToolCallResult | None:
        current_event = event
        changed = False
        context = self._context_from_runtime(fallback_cwd=_context_from_agent_event(event).cwd)
        for extension in self._extensions:
            for handler in extension.hooks.get("tool_result", []):
                try:
                    decision = handler(current_event, context)
                    if inspect.isawaitable(decision):
                        decision = await decision
                except Exception as exc:
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="extension_tool_result_failed",
                            message=f"Extension hook 'tool_result' failed: {exc}",
                            source_path=extension.source_path,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event="tool_result", error=exc)
                    continue
                if decision is None:
                    continue
                if not isinstance(decision, ToolResultDecision):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_result_decision",
                            message="tool_result hooks must return ToolResultDecision or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if decision.diagnostics:
                    self._diagnostics.extend(decision.diagnostics)
                if decision.result is None:
                    continue
                if not isinstance(decision.result, AgentToolResult):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_result_decision",
                            message="tool_result decisions must return AgentToolResult instances when overriding results.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                changed = True
                current_event = replace(current_event, result=decision.result)
        if not changed:
            return None
        return AfterToolCallResult(
            content=current_event.result.content,
            details=current_event.result.details,
            terminate=current_event.result.terminate,
        )

    def _apply_resource_handlers(
        self,
        *,
        extension: LoadedExtension,
        handlers: Sequence[object],
        bundle: ResourceBundle,
        context: _RunnerContext,
        diagnostics: list[ResourceDiagnostic],
    ) -> ResourceBundle:
        merged = bundle
        for handler in handlers:
            try:
                callback = cast(Callable[[ResourceBundle, _RunnerContext], object | None], handler)
                contribution = callback(merged, context)
            except Exception as exc:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_resources_discover_failed",
                        message=f"Extension resource discovery failed: {exc}",
                        source_path=extension.source_path,
                    )
                )
                continue
            if inspect.isawaitable(contribution):
                self._record_unsupported_async_hook(
                    awaitable=contribution,
                    source_path=extension.source_path,
                    message="Async extension hooks are not supported in P0/v1.",
                    diagnostics=diagnostics,
                )
                continue
            if contribution is None:
                continue
            contribution = _coerce_resource_contribution(contribution, extension=extension)
            if not isinstance(contribution, ExtensionResourceContribution):
                diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_resource_contribution",
                        message="resources_discover hooks must return ExtensionResourceContribution or None.",
                        source_path=extension.source_path,
                    )
                )
                continue
            diagnostics.extend(contribution.diagnostics)
            merged = merged.merge(
                prompt_descriptors=list(contribution.prompt_descriptors),
                skills=list(contribution.skills),
                extensions=list(contribution.extensions),
                prompts=list(contribution.prompts),
                themes=list(contribution.themes),
            )
        return merged

    async def _apply_resource_handlers_async(
        self,
        *,
        extension: LoadedExtension,
        handlers: Sequence[object],
        bundle: ResourceBundle,
        context: _RunnerContext,
        diagnostics: list[ResourceDiagnostic],
    ) -> ResourceBundle:
        merged = bundle
        for handler in handlers:
            try:
                callback = cast(Callable[[ResourceBundle, _RunnerContext], object | None], handler)
                contribution = callback(merged, context)
                if inspect.isawaitable(contribution):
                    contribution = await contribution
            except Exception as exc:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_resources_discover_failed",
                        message=f"Extension resource discovery failed: {exc}",
                        source_path=extension.source_path,
                    )
                )
                continue
            if contribution is None:
                continue
            contribution = _coerce_resource_contribution(contribution, extension=extension)
            if not isinstance(contribution, ExtensionResourceContribution):
                diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_resource_contribution",
                        message="resources_discover hooks must return ExtensionResourceContribution or None.",
                        source_path=extension.source_path,
                    )
                )
                continue
            diagnostics.extend(contribution.diagnostics)
            merged = merged.merge(
                prompt_descriptors=list(contribution.prompt_descriptors),
                skills=list(contribution.skills),
                extensions=list(contribution.extensions),
                prompts=list(contribution.prompts),
                themes=list(contribution.themes),
            )
        return merged

    def _collect_tools(self, extension: LoadedExtension) -> None:
        for tool in extension.tool_definitions:
            if tool.name in self._tool_names:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="duplicate_extension_tool",
                        message=f"Duplicate extension tool '{tool.name}' was rejected.",
                        source_path=extension.source_path,
                    )
            )
                continue
            self._tool_names.add(tool.name)
            self._tool_source_info_by_name[tool.name] = _source_info_from_extension(extension)
            self._tool_definitions.append(
                wrap_registered_tool_definition(
                    tool,
                    lambda: self._context_from_runtime(fallback_cwd=str(extension.source_path.parent)),
                )
            )

    def _build_registry_views(self) -> None:
        literal_command_names: set[str] = set()
        command_counts: dict[str, int] = {}
        for extension in self._extensions:
            for name in extension.commands:
                literal_command_names.add(name)
                command_counts[name] = command_counts.get(name, 0) + 1

        command_occurrences: dict[str, int] = {}
        next_command_suffixes: dict[str, int] = {}
        taken_command_names: set[str] = set()

        for extension in self._extensions:
            for name, command in extension.commands.items():
                command_occurrences[name] = command_occurrences.get(name, 0) + 1
                invocation_name = name
                if command_counts.get(name, 0) > 1:
                    suffix = next_command_suffixes.get(name, 1)
                    invocation_name = f"{name}:{suffix}"
                    while invocation_name in taken_command_names or invocation_name in literal_command_names:
                        suffix += 1
                        invocation_name = f"{name}:{suffix}"
                    next_command_suffixes[name] = suffix + 1
                source_info = _source_info_from_extension(extension)
                resolved_command = ResolvedCommand(
                    name=command.name,
                    handler=command.handler,
                    description=command.description,
                    get_argument_completions=command.get_argument_completions,
                    invocation_name=invocation_name,
                    source_info=source_info,
                    extension_name=extension.name,
                )
                self._registered_commands.append(resolved_command)
                self._registered_commands_by_invocation_name[invocation_name] = resolved_command
                taken_command_names.add(invocation_name)

        seen_flags: set[str] = set()
        seen_shortcuts: set[str] = set()
        for extension in self._extensions:
            for name, flag in extension.flags.items():
                if name in seen_flags:
                    diagnostic = ResourceDiagnostic(
                        code="duplicate_extension_flag",
                        message=f"Duplicate extension flag '{name}' was rejected.",
                        source_path=extension.source_path,
                    )
                    self._flag_diagnostics.append(diagnostic)
                    self._diagnostics.append(diagnostic)
                    continue
                seen_flags.add(name)
                source_info = _source_info_from_extension(extension)
                self._resolved_flags.append(
                    ResolvedFlag(
                        name=flag.name,
                        type=flag.type,
                        description=flag.description,
                        default=flag.default,
                        source_info=source_info,
                        extension_name=extension.name,
                    )
                )
                if flag.default is not None and name not in self._runtime_state.flag_values:
                    self._runtime_state.flag_values[name] = flag.default
            for shortcut, shortcut_definition in extension.shortcuts.items():
                if shortcut in seen_shortcuts:
                    diagnostic = ResourceDiagnostic(
                        code="duplicate_extension_shortcut",
                        message=f"Duplicate extension shortcut '{shortcut}' was rejected.",
                        source_path=extension.source_path,
                    )
                    self._shortcut_diagnostics.append(diagnostic)
                    self._diagnostics.append(diagnostic)
                    continue
                seen_shortcuts.add(shortcut)
                source_info = _source_info_from_extension(extension)
                self._resolved_shortcuts.append(
                    ResolvedShortcut(
                        shortcut=shortcut_definition.shortcut,
                        handler=shortcut_definition.handler,
                        description=shortcut_definition.description,
                        source_info=source_info,
                        extension_name=extension.name,
                    )
                )

    async def _emit_session_hook(self, hook_name: str, session: object) -> None:
        for extension in self._extensions:
            context = self._context_from_runtime(
                fallback_cwd=_context_from_session(session).cwd,
                extension=extension,
            )
            for handler in extension.hooks.get(hook_name, []):
                try:
                    result = handler(session, context)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    self._diagnostics.append(
                        _extension_hook_failure_diagnostic(
                            extension=extension,
                            hook_name=hook_name,
                            exc=exc,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event=hook_name, error=exc)
                    continue

    async def _emit_decision_hook(
        self,
        hook_name: str,
        event: object,
        *,
        fallback_cwd: str,
        result_type: type[SessionActionDecision] = SessionActionDecision,
    ) -> SessionActionDecision | None:
        context = self._context_from_runtime(fallback_cwd=fallback_cwd)
        latest_result: SessionActionDecision | None = None
        for extension in self._extensions:
            for handler in extension.hooks.get(hook_name, []):
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._diagnostics.append(
                        _extension_hook_failure_diagnostic(
                            extension=extension,
                            hook_name=hook_name,
                            exc=exc,
                        )
                    )
                    self._emit_runtime_error(extension=extension, event=hook_name, error=exc)
                    continue
                if result is None:
                    continue
                if not isinstance(result, result_type):
                    expected_name = result_type.__name__
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code=f"invalid_extension_{hook_name}_decision",
                            message=f"{hook_name} hooks must return {expected_name} or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if result.diagnostics:
                    self._diagnostics.extend(result.diagnostics)
                latest_result = result
        return latest_result

    def _context_from_runtime(
        self,
        *,
        fallback_cwd: str = "",
        extension: LoadedExtension | None = None,
    ) -> ExtensionContext:
        if self._runtime_state.bindings is None:
            return _StaticExtensionContext(cwd=fallback_cwd)
        return _BoundExtensionContext(
            self._runtime_state,
            self._runtime_state.generation,
            _source_info_from_extension(extension) if extension is not None else None,
        )

    def _emit_runtime_error(self, *, extension: LoadedExtension, event: str, error: Exception) -> None:
        bindings = self._runtime_state.bindings
        callback = getattr(bindings, "on_error", None) if bindings is not None else None
        if not callable(callback):
            return
        callback(
            {
                "extensionPath": str(extension.source_path),
                "event": event,
                "error": str(error),
            }
        )

    def _record_unsupported_async_hook(
        self,
        *,
        awaitable: object,
        source_path: Path,
        message: str,
        diagnostics: list[ResourceDiagnostic] | None = None,
    ) -> None:
        if inspect.iscoroutine(awaitable):
            awaitable.close()
        target = self._diagnostics if diagnostics is None else diagnostics
        target.append(
            ResourceDiagnostic(
                code="unsupported_async_extension_hook",
                message=message,
                source_path=source_path,
            )
        )


def _context_from_session(session: object) -> _RunnerContext:
    session_manager = getattr(session, "session_manager", None)
    get_cwd = getattr(session_manager, "get_cwd", None)
    if callable(get_cwd):
        return _RunnerContext(cwd=str(get_cwd()))
    return _RunnerContext(cwd="")


def _context_from_agent_event(event: object) -> _RunnerContext:
    agent_context = getattr(event, "context", None)
    messages = getattr(agent_context, "messages", None)
    if isinstance(messages, list):
        return _RunnerContext(cwd="")
    return _RunnerContext(cwd="")


def _event_type(event: object) -> str | None:
    if isinstance(event, dict):
        value = event.get("type")
        return value if isinstance(value, str) else None
    value = getattr(event, "type", None)
    return value if isinstance(value, str) else None


def _event_object(event: object) -> object:
    if not isinstance(event, dict):
        return event
    values = dict(event)
    values.update(_event_aliases(values))
    return _ExtensionEvent(**values)


def _event_aliases(values: dict[str, object]) -> dict[str, object]:
    aliases: dict[str, object] = {}
    alias_names = {
        "assistant_message_event": "assistantMessageEvent",
        "tool_call_id": "toolCallId",
        "tool_name": "toolName",
        "tool_results": "toolResults",
        "turn_index": "turnIndex",
        "is_error": "isError",
        "partial_result": "partialResult",
        "new_leaf_id": "newLeafId",
        "old_leaf_id": "oldLeafId",
        "summary_entry": "summaryEntry",
        "compaction_entry": "compactionEntry",
        "from_extension": "fromExtension",
        "exclude_from_context": "excludeFromContext",
        "previous_model": "previousModel",
    }
    for source_name, alias_name in alias_names.items():
        if source_name in values:
            aliases[alias_name] = values[source_name]
    return aliases


@dataclass
class _ExtensionEvent:
    def __init__(self, **values: object) -> None:
        for key, value in values.items():
            setattr(self, key, value)


def _normalize_input_source(source: str) -> str:
    return source if source in {"interactive", "rpc", "extension"} else "interactive"


def _coerce_input_result(result: object) -> tuple[str | None, str | None, list[object] | None]:
    if result is None:
        return None, None, None
    if isinstance(result, InputEventResult):
        return result.action, result.text, result.images
    if isinstance(result, dict):
        action = result.get("action")
        text = result.get("text")
        images = result.get("images")
        return (
            action if isinstance(action, str) else None,
            text if isinstance(text, str) else None,
            images if isinstance(images, list) else None,
        )
    return None, None, None


def _coerce_before_agent_start_result(result: object) -> BeforeAgentStartResult | None:
    if result is None:
        return None
    if isinstance(result, BeforeAgentStartResult):
        return result
    if isinstance(result, dict):
        system_prompt = result.get("systemPrompt", result.get("system_prompt"))
        system_prompt_append = result.get("systemPromptAppend", result.get("system_prompt_append", ""))
        extra_messages = result.get("messages", result.get("extraMessages", result.get("extra_messages", [])))
        diagnostics = result.get("diagnostics", [])
        return BeforeAgentStartResult(
            system_prompt=system_prompt if isinstance(system_prompt, str) else None,
            system_prompt_append=system_prompt_append if isinstance(system_prompt_append, str) else "",
            extra_messages=extra_messages if isinstance(extra_messages, list) else [],
            diagnostics=diagnostics if isinstance(diagnostics, list) else [],
        )
    return None


def _safe_get_value(target: object, name: str) -> object | None:
    if isinstance(target, dict):
        return target.get(name)
    try:
        return getattr(target, name)
    except Exception:
        return None


def _normalize_provider_response_headers(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    items = None
    if isinstance(headers, dict):
        items = headers.items()
    else:
        getter = getattr(headers, "items", None)
        if callable(getter):
            try:
                items = getter()
            except Exception:
                items = None
    if items is None:
        return {}
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized[str(key)] = str(value)
    return normalized


def _extension_visibility_snapshot(
    extension: LoadedExtension,
    *,
    diagnostics: list[ResourceDiagnostic],
) -> dict[str, object]:
    manifest = extension.manifest
    policy = extension.policy
    source_info = _source_info_from_extension(extension)
    extension_id = manifest.id if manifest is not None else extension.name
    extension_name = manifest.name if manifest is not None else extension.name
    manifest_path = _extension_manifest_path(extension)
    return {
        "id": extension_id,
        "name": extension_name,
        "runtimeName": extension.name,
        "version": manifest.version if manifest is not None else None,
        "description": manifest.description if manifest is not None else None,
        "sourcePath": source_info.path.as_posix(),
        "manifestPath": manifest_path.as_posix() if manifest_path is not None else None,
        "enabled": policy.enabled if policy is not None else True,
        "permissionLevel": (
            policy.permission_level
            if policy is not None
            else manifest.permissions.level
            if manifest is not None
            else "safe"
        ),
        "capabilities": list(
            policy.capabilities
            if policy is not None
            else manifest.permissions.capabilities
            if manifest is not None
            else ()
        ),
        "contributions": [
            _serialize_contribution(contribution)
            for contribution in extension.contributions
        ],
        "diagnostics": [
            _serialize_diagnostic(diagnostic)
            for diagnostic in _extension_visibility_diagnostics(
                extension,
                diagnostics=diagnostics,
                manifest_path=manifest_path,
            )
        ],
    }


def _serialize_contribution(contribution: object) -> dict[str, object]:
    metadata = getattr(contribution, "metadata", {})
    source = metadata.get("source") if isinstance(metadata, dict) else None
    return {
        "type": str(getattr(contribution, "type", "")),
        "name": str(getattr(contribution, "name", "")),
        "active": bool(getattr(contribution, "active", True)),
        "priority": int(getattr(contribution, "priority", 0)),
        "source": source if isinstance(source, str) else "",
        "sourcePath": _path_text(getattr(contribution, "source_path", None)),
        "diagnostics": [
            _serialize_diagnostic(diagnostic)
            for diagnostic in getattr(contribution, "diagnostics", ())
            if isinstance(diagnostic, ResourceDiagnostic)
        ],
    }


def _extension_visibility_diagnostics(
    extension: LoadedExtension,
    *,
    diagnostics: list[ResourceDiagnostic],
    manifest_path: Path | None,
) -> list[ResourceDiagnostic]:
    source_paths = {
        path
        for path in (
            extension.source_path,
            extension.entry_path,
            manifest_path,
            *_extension_manifest_candidate_paths(extension),
        )
        if path is not None
    }
    result: list[ResourceDiagnostic] = []
    seen: set[tuple[str, str, str | None]] = set()
    for diagnostic in extension.diagnostics:
        result, seen = _append_extension_diagnostic(result, seen, diagnostic)
    for diagnostic in diagnostics:
        if diagnostic.source_path is None or diagnostic.source_path not in source_paths:
            continue
        result, seen = _append_extension_diagnostic(result, seen, diagnostic)
    return result


def _append_extension_diagnostic(
    result: list[ResourceDiagnostic],
    seen: set[tuple[str, str, str | None]],
    diagnostic: ResourceDiagnostic,
) -> tuple[list[ResourceDiagnostic], set[tuple[str, str, str | None]]]:
    key = (
        diagnostic.code,
        diagnostic.message,
        diagnostic.source_path.as_posix() if diagnostic.source_path is not None else None,
    )
    if key not in seen:
        seen.add(key)
        result.append(diagnostic)
    return result, seen


def _serialize_diagnostic(diagnostic: ResourceDiagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "sourcePath": diagnostic.source_path.as_posix() if diagnostic.source_path is not None else None,
        "resourceId": diagnostic.resource_id,
        "resourceType": diagnostic.resource_type,
        "sourceKind": diagnostic.source_kind,
        "metadata": dict(diagnostic.metadata),
    }


def _extension_manifest_path(extension: LoadedExtension) -> Path | None:
    for candidate in _extension_manifest_candidate_paths(extension):
        if candidate.is_file():
            return candidate
    return None


def _extension_manifest_candidate_paths(extension: LoadedExtension) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if extension.source_path.suffix:
        candidates.append(extension.source_path.with_name("loushang-extension.toml"))
    else:
        candidates.append(extension.source_path / "loushang-extension.toml")
    if extension.entry_path is not None:
        candidates.append(extension.entry_path.parent / "loushang-extension.toml")
    return tuple(dict.fromkeys(candidates))


def _path_text(value: object) -> str:
    return value.as_posix() if isinstance(value, Path) else str(value or "")


def _source_info_from_extension(extension: LoadedExtension) -> SourceInfo:
    return SourceInfo(
        path=extension.entry_path or extension.source_path,
        source=extension.source,
        scope=_scope_from_extension(extension),
        origin=_origin_from_extension(extension),
        base_dir=extension.source_root,
    )


def _extension_hook_failure_diagnostic(
    *,
    extension: LoadedExtension,
    hook_name: str,
    exc: BaseException,
    code: str | None = None,
) -> ResourceDiagnostic:
    source_info = _source_info_from_extension(extension)
    return ResourceDiagnostic(
        code=code or f"extension_{hook_name}_failed",
        message=f"Extension hook '{hook_name}' failed: {exc}",
        source_path=extension.source_path,
        metadata={
            "extension_name": extension.name,
            "hook": hook_name,
            "source": source_info.source,
            "scope": source_info.scope,
            "origin": source_info.origin,
            "base_dir": (
                source_info.base_dir.as_posix()
                if source_info.base_dir is not None
                else extension.source_path.parent.as_posix()
            ),
        },
    )


def _serialize_source_info(source_info: SourceInfo) -> dict[str, object]:
    return {
        "path": source_info.path.as_posix(),
        "source": source_info.source,
        "scope": source_info.scope,
        "origin": source_info.origin,
        "baseDir": source_info.base_dir.as_posix() if source_info.base_dir is not None else None,
        "base_dir": source_info.base_dir.as_posix() if source_info.base_dir is not None else None,
    }


def _origin_from_extension(extension: LoadedExtension):
    if extension.source_scope in {"package", "builtin"} or extension.source_kind in {"external_package", "built_in"}:
        return "package"
    return "top-level"


def _scope_from_extension(extension: LoadedExtension):
    if extension.source in {"inline", "sdk"}:
        return "temporary"
    if extension.source_scope == "user":
        return "user"
    return "project"


def _coerce_resource_contribution(
    contribution: object,
    *,
    extension: LoadedExtension,
) -> object:
    if not isinstance(contribution, dict):
        return contribution
    diagnostics: list[ResourceDiagnostic] = []
    return ExtensionResourceContribution(
        prompts=_prompt_descriptors_from_paths(
            _as_path_list(contribution.get("promptPaths")),
            extension=extension,
            diagnostics=diagnostics,
        ),
        skills=_skill_descriptors_from_paths(
            _as_path_list(contribution.get("skillPaths")),
            extension=extension,
            diagnostics=diagnostics,
        ),
        themes=_theme_descriptors_from_paths(
            _as_path_list(contribution.get("themePaths")),
            extension=extension,
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


def _as_path_list(value: object) -> list[Path]:
    if not isinstance(value, list):
        return []
    return [Path(item) for item in value if isinstance(item, str | Path)]


def _prompt_descriptors_from_paths(
    paths: Sequence[Path],
    *,
    extension: LoadedExtension,
    diagnostics: list[ResourceDiagnostic],
) -> list[PromptFragmentDescriptor]:
    descriptors: list[PromptFragmentDescriptor] = []
    for path in paths:
        descriptor, diagnostic = _prompt_descriptor_from_path(path, extension=extension)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if descriptor is not None:
            descriptors.append(descriptor)
    return descriptors


def _prompt_descriptor_from_path(
    path: Path,
    *,
    extension: LoadedExtension,
) -> tuple[PromptFragmentDescriptor | None, ResourceDiagnostic | None]:
    if not path.is_file():
        return None, ResourceDiagnostic(
            code="extension_prompt_path_not_found",
            message=f"Extension prompt path does not exist or is not a file: {path}",
            source_path=path,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, ResourceDiagnostic(
            code="extension_prompt_path_read_failed",
            message=f"Failed to read extension prompt path {path}: {exc}",
            source_path=path,
        )
    return (
        PromptFragmentDescriptor(
            name=path.stem,
            source_path=path,
            text=text,
            canonical_name=path.name,
            source=extension.source,
            source_kind=extension.source_kind,
            source_scope=extension.source_scope,
            source_root=path.parent,
        ),
        None,
    )


def _skill_descriptors_from_paths(
    paths: Sequence[Path],
    *,
    extension: LoadedExtension,
    diagnostics: list[ResourceDiagnostic],
) -> list[SkillDescriptor]:
    descriptors: list[SkillDescriptor] = []
    for path in paths:
        descriptor, diagnostic = _skill_descriptor_from_path(path, extension=extension)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if descriptor is not None:
            descriptors.append(descriptor)
    return descriptors


def _skill_descriptor_from_path(
    path: Path,
    *,
    extension: LoadedExtension,
) -> tuple[SkillDescriptor | None, ResourceDiagnostic | None]:
    skill_file = path / "SKILL.md" if path.is_dir() else path
    if not skill_file.is_file():
        return None, ResourceDiagnostic(
            code="extension_skill_path_not_found",
            message=f"Extension skill path does not exist or is not a skill file: {path}",
            source_path=path,
        )
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return None, ResourceDiagnostic(
            code="extension_skill_path_read_failed",
            message=f"Failed to read extension skill path {skill_file}: {exc}",
            source_path=skill_file,
        )
    return (
        SkillDescriptor(
            name=skill_file.parent.name if skill_file.name == "SKILL.md" else skill_file.stem,
            source_path=skill_file,
            content=content,
            canonical_name=f"{skill_file.parent.name}/SKILL.md" if skill_file.name == "SKILL.md" else skill_file.name,
            source=extension.source,
            source_kind=extension.source_kind,
            source_scope=extension.source_scope,
            source_root=skill_file.parent.parent if skill_file.name == "SKILL.md" else skill_file.parent,
        ),
        None,
    )


def _theme_descriptors_from_paths(
    paths: Sequence[Path],
    *,
    extension: LoadedExtension,
    diagnostics: list[ResourceDiagnostic],
) -> list[ThemeDescriptor]:
    descriptors: list[ThemeDescriptor] = []
    for path in paths:
        descriptor, diagnostic = _theme_descriptor_from_path(path, extension=extension)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if descriptor is not None:
            descriptors.append(descriptor)
    return descriptors


def _theme_descriptor_from_path(
    path: Path,
    *,
    extension: LoadedExtension,
) -> tuple[ThemeDescriptor | None, ResourceDiagnostic | None]:
    if not path.exists():
        return None, ResourceDiagnostic(
            code="extension_theme_path_not_found",
            message=f"Extension theme path does not exist: {path}",
            source_path=path,
        )
    return (
        ThemeDescriptor(
            name=path.stem if path.is_file() else path.name,
            source_path=path,
            canonical_name=path.name,
            source=extension.source,
            source_kind=extension.source_kind,
            source_scope=extension.source_scope,
            source_root=path.parent,
        ),
        None,
    )


def _compact_custom_instructions(options: object | None) -> str | None:
    if isinstance(options, str):
        return options
    if isinstance(options, dict):
        value = options.get("customInstructions", options.get("custom_instructions"))
        return value if isinstance(value, str) else None
    return None

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from loushang.agent import ThinkingLevel
from loushang.coding.commands import SessionCommandDescriptor
from loushang.coding.compaction import BranchSummaryResult
from loushang.coding.types import ModelSelection
from loushang.harness.agent_transcript import CompactionResult
from loushang.harness.extensions.events import VALID_EXTENSION_EVENTS
from loushang.harness.extensions.types import (
    BeforeAgentStartResult,
    ContextResult,
    ExtensionHandler,
    ExtensionResourceContribution,
    InputEvent,
    InputEventResult,
    InputSource,
    LoadedExtension,
    RegisteredCommand,
    RegisteredFlag,
    RegisteredShortcut,
    ResolvedCommand,
    ResolvedFlag,
    ResolvedShortcut,
    ToolCallDecision,
    ToolResultDecision,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.source import SourceInfo
from loushang.harness.runtime import ProductRuntimeBindings
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.workspace.exec import ExecResult, ExecUpdateCallback


async def _ignore_thinking_level(level: ThinkingLevel) -> None:
    del level


class ExtensionContext(Protocol):
    @property
    def ui(self) -> "ExtensionContext": ...

    @property
    def hasUI(self) -> bool: ...

    @property
    def has_ui(self) -> bool: ...

    @property
    def cwd(self) -> str: ...

    @property
    def sessionManager(self) -> object | None: ...

    @property
    def session_manager(self) -> object | None: ...

    @property
    def modelRegistry(self) -> object | None: ...

    @property
    def model_registry(self) -> object | None: ...

    @property
    def model(self) -> object | None: ...

    @property
    def signal(self) -> object | None: ...

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
    ) -> ExecResult: ...

    def get_active_tool_names(self) -> list[str]: ...

    def getActiveTools(self) -> list[str]: ...

    def getAllTools(self) -> list[object]: ...

    def get_all_tools(self) -> list[object]: ...

    def register_tool(self, tool: ToolDefinition | object) -> None: ...

    def registerTool(self, tool: ToolDefinition | object) -> None: ...

    def getFlag(self, name: str) -> bool | str | None: ...

    def get_flag(self, name: str) -> bool | str | None: ...

    def get_model_selection(self) -> ModelSelection | None: ...

    async def set_active_tools(self, tool_names: list[str]) -> None: ...

    async def setActiveTools(self, tool_names: list[str]) -> None: ...

    async def set_model(self, selection: ModelSelection) -> None: ...

    async def setModel(self, selection: ModelSelection) -> None: ...

    def getThinkingLevel(self) -> ThinkingLevel: ...

    def get_thinking_level(self) -> ThinkingLevel: ...

    async def setThinkingLevel(self, level: ThinkingLevel) -> None: ...

    async def set_thinking_level(self, level: ThinkingLevel) -> None: ...

    async def appendEntry(
        self, custom_type: str, data: object | None = None
    ) -> None: ...

    async def append_entry(
        self, custom_type: str, data: object | None = None
    ) -> None: ...

    async def sendMessage(
        self, message: object, options: object | None = None
    ) -> None: ...

    async def send_message(
        self, message: object, options: object | None = None
    ) -> None: ...

    async def sendUserMessage(
        self, content: object, options: object | None = None
    ) -> None: ...

    async def send_user_message(
        self, content: object, options: object | None = None
    ) -> None: ...

    async def setSessionName(self, name: str | None) -> None: ...

    async def set_session_name(self, name: str | None) -> None: ...

    def getSessionName(self) -> str | None: ...

    def get_session_name(self) -> str | None: ...

    async def setLabel(self, entry_id: str, label: str | None) -> None: ...

    async def set_label(self, entry_id: str, label: str | None) -> None: ...

    def listCommands(self) -> list[SessionCommandDescriptor]: ...

    def list_commands(self) -> list[SessionCommandDescriptor]: ...

    def request_resource_refresh(self) -> None: ...

    def abort(self) -> None: ...

    def isIdle(self) -> bool: ...

    def is_idle(self) -> bool: ...

    def hasPendingMessages(self) -> bool: ...

    def has_pending_messages(self) -> bool: ...

    def get_context_usage(self) -> object | None: ...

    def compact(self, options: object | None = None) -> Awaitable[object | None]: ...

    def getSystemPrompt(self) -> str: ...

    def get_system_prompt(self) -> str: ...

    async def waitForIdle(self) -> None: ...

    async def wait_for_idle(self) -> None: ...

    async def reload(self) -> None: ...

    async def navigateTree(
        self, target_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def navigate_tree(
        self, target_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def fork(
        self, entry_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def newSession(self, options: object | None = None) -> dict[str, object]: ...

    async def new_session(self, options: object | None = None) -> dict[str, object]: ...

    async def switchSession(
        self, session_path: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def switch_session(
        self, session_path: str, options: object | None = None
    ) -> dict[str, object]: ...

    def shutdown(self) -> None: ...

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None: ...

    def notify(self, message: str, notify_type: str | None = None) -> None: ...

    def set_status(self, key: str, text: str | None) -> None: ...

    def setStatus(self, key: str, text: str | None) -> None: ...

    def set_widget(
        self, key: str, lines: list[str] | None, *, placement: str | None = None
    ) -> None: ...

    def setWidget(
        self, key: str, lines: list[str] | None, *, placement: str | None = None
    ) -> None: ...

    def set_title(self, title: str) -> None: ...

    def setTitle(self, title: str) -> None: ...

    def set_editor_text(self, text: str) -> None: ...

    def setEditorText(self, text: str) -> None: ...

    def pasteToEditor(self, text: str) -> None: ...

    def getEditorText(self) -> str: ...

    def onTerminalInput(self, handler: Callable[[str], None]) -> Callable[[], None]: ...

    def setWorkingMessage(self, message: str | None = None) -> None: ...

    def setWorkingVisible(self, visible: bool) -> None: ...

    def setWorkingIndicator(self, options: object | None = None) -> None: ...

    def setHiddenThinkingLabel(self, label: str | None = None) -> None: ...

    def setFooter(self, factory: object | None) -> None: ...

    def setHeader(self, factory: object | None) -> None: ...

    def addAutocompleteProvider(self, factory: object) -> None: ...

    def setEditorComponent(self, factory: object | None) -> None: ...

    def getAllThemes(self) -> list[object]: ...

    def getTheme(self, name: str) -> object | None: ...

    def setTheme(self, theme: object) -> dict[str, object]: ...

    def getToolsExpanded(self) -> bool: ...

    def setToolsExpanded(self, expanded: bool) -> None: ...

    async def select(
        self, title: str, options: list[str], *, timeout: float | None = None
    ) -> str | None: ...

    async def confirm(
        self, title: str, message: str, *, timeout: float | None = None
    ) -> bool: ...

    async def input(
        self,
        title: str,
        placeholder: str | None = None,
        *,
        timeout: float | None = None,
    ) -> str | None: ...

    async def editor(self, title: str, prefill: str | None = None) -> str | None: ...


class ExtensionCommandContext(Protocol):
    @property
    def ui(self) -> "ExtensionCommandContext": ...

    @property
    def hasUI(self) -> bool: ...

    @property
    def has_ui(self) -> bool: ...

    @property
    def cwd(self) -> str: ...

    @property
    def sessionManager(self) -> object | None: ...

    @property
    def session_manager(self) -> object | None: ...

    @property
    def modelRegistry(self) -> object | None: ...

    @property
    def model_registry(self) -> object | None: ...

    @property
    def model(self) -> object | None: ...

    @property
    def signal(self) -> object | None: ...

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
    ) -> ExecResult: ...

    def get_active_tool_names(self) -> list[str]: ...

    def getActiveTools(self) -> list[str]: ...

    def getAllTools(self) -> list[object]: ...

    def get_all_tools(self) -> list[object]: ...

    def register_tool(self, tool: ToolDefinition | object) -> None: ...

    def registerTool(self, tool: ToolDefinition | object) -> None: ...

    def get_model_selection(self) -> ModelSelection | None: ...

    async def set_active_tools(self, tool_names: list[str]) -> None: ...

    async def setActiveTools(self, tool_names: list[str]) -> None: ...

    async def set_model(self, selection: ModelSelection) -> None: ...

    async def appendEntry(
        self, custom_type: str, data: object | None = None
    ) -> None: ...

    async def append_entry(
        self, custom_type: str, data: object | None = None
    ) -> None: ...

    async def sendMessage(
        self, message: object, options: object | None = None
    ) -> None: ...

    async def send_message(
        self, message: object, options: object | None = None
    ) -> None: ...

    async def sendUserMessage(
        self, content: object, options: object | None = None
    ) -> None: ...

    async def send_user_message(
        self, content: object, options: object | None = None
    ) -> None: ...

    async def setSessionName(self, name: str | None) -> None: ...

    async def set_session_name(self, name: str | None) -> None: ...

    def getSessionName(self) -> str | None: ...

    def get_session_name(self) -> str | None: ...

    async def setLabel(self, entry_id: str, label: str | None) -> None: ...

    async def set_label(self, entry_id: str, label: str | None) -> None: ...

    def listCommands(self) -> list[SessionCommandDescriptor]: ...

    def list_commands(self) -> list[SessionCommandDescriptor]: ...

    def request_resource_refresh(self) -> None: ...

    def abort(self) -> None: ...

    def isIdle(self) -> bool: ...

    def is_idle(self) -> bool: ...

    def hasPendingMessages(self) -> bool: ...

    def has_pending_messages(self) -> bool: ...

    def get_context_usage(self) -> object | None: ...

    def compact(self, options: object | None = None) -> Awaitable[object | None]: ...

    def getSystemPrompt(self) -> str: ...

    def get_system_prompt(self) -> str: ...

    async def waitForIdle(self) -> None: ...

    async def wait_for_idle(self) -> None: ...

    async def reload(self) -> None: ...

    async def navigateTree(
        self, target_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def navigate_tree(
        self, target_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def fork(
        self, entry_id: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def newSession(self, options: object | None = None) -> dict[str, object]: ...

    async def new_session(self, options: object | None = None) -> dict[str, object]: ...

    async def switchSession(
        self, session_path: str, options: object | None = None
    ) -> dict[str, object]: ...

    async def switch_session(
        self, session_path: str, options: object | None = None
    ) -> dict[str, object]: ...

    def shutdown(self) -> None: ...

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None: ...

    def notify(self, message: str, notify_type: str | None = None) -> None: ...

    def set_status(self, key: str, text: str | None) -> None: ...

    def setStatus(self, key: str, text: str | None) -> None: ...

    def set_widget(
        self, key: str, lines: list[str] | None, *, placement: str | None = None
    ) -> None: ...

    def setWidget(
        self, key: str, lines: list[str] | None, *, placement: str | None = None
    ) -> None: ...

    def set_title(self, title: str) -> None: ...

    def setTitle(self, title: str) -> None: ...

    def set_editor_text(self, text: str) -> None: ...

    def setEditorText(self, text: str) -> None: ...

    def pasteToEditor(self, text: str) -> None: ...

    def getEditorText(self) -> str: ...

    def onTerminalInput(self, handler: Callable[[str], None]) -> Callable[[], None]: ...

    def setWorkingMessage(self, message: str | None = None) -> None: ...

    def setWorkingVisible(self, visible: bool) -> None: ...

    def setWorkingIndicator(self, options: object | None = None) -> None: ...

    def setHiddenThinkingLabel(self, label: str | None = None) -> None: ...

    def setFooter(self, factory: object | None) -> None: ...

    def setHeader(self, factory: object | None) -> None: ...

    def addAutocompleteProvider(self, factory: object) -> None: ...

    def setEditorComponent(self, factory: object | None) -> None: ...

    def getAllThemes(self) -> list[object]: ...

    def getTheme(self, name: str) -> object | None: ...

    def setTheme(self, theme: object) -> dict[str, object]: ...

    def getToolsExpanded(self) -> bool: ...

    def setToolsExpanded(self, expanded: bool) -> None: ...

    async def select(
        self, title: str, options: list[str], *, timeout: float | None = None
    ) -> str | None: ...

    async def confirm(
        self, title: str, message: str, *, timeout: float | None = None
    ) -> bool: ...

    async def input(
        self,
        title: str,
        placeholder: str | None = None,
        *,
        timeout: float | None = None,
    ) -> str | None: ...

    async def editor(self, title: str, prefill: str | None = None) -> str | None: ...


class ReplacedSessionContext(ExtensionCommandContext, Protocol):
    """Context passed to `withSession` callbacks after a session replacement."""


@dataclass(frozen=True)
class SessionStartEvent:
    reason: str = "startup"
    previous_session_file: str | None = None
    type: Literal["session_start"] = "session_start"

    @property
    def previousSessionFile(self) -> str | None:
        return self.previous_session_file


@dataclass(frozen=True)
class SessionShutdownEvent:
    reason: str = "quit"
    target_session_file: str | None = None
    type: Literal["session_shutdown"] = "session_shutdown"

    @property
    def targetSessionFile(self) -> str | None:
        return self.target_session_file


@dataclass(frozen=True)
class SessionRefreshEvent:
    reason: str
    type: Literal["session_refresh"] = "session_refresh"


@dataclass(frozen=True)
class SessionBeforeSwitchEvent:
    reason: str
    cwd: str
    target_session_file: str | None = None
    type: Literal["session_before_switch"] = "session_before_switch"

    @property
    def targetSessionFile(self) -> str | None:
        return self.target_session_file


@dataclass(frozen=True)
class SessionBeforeForkEvent:
    entry_id: str
    cwd: str
    position: str = "before"
    type: Literal["session_before_fork"] = "session_before_fork"

    @property
    def entryId(self) -> str:
        return self.entry_id


@dataclass(frozen=True)
class SessionBeforeCompactEvent:
    reason: str
    cwd: str
    custom_instructions: str | None = None
    type: Literal["session_before_compact"] = "session_before_compact"

    @property
    def customInstructions(self) -> str | None:
        return self.custom_instructions


@dataclass(frozen=True)
class SessionBeforeTreeEvent:
    target_id: str
    old_leaf_id: str | None
    cwd: str
    new_leaf_id: str | None = None
    summarize: bool = False
    custom_instructions: str | None = None
    replace_instructions: bool = False
    label: str | None = None
    type: Literal["session_before_tree"] = "session_before_tree"

    @property
    def targetId(self) -> str:
        return self.target_id

    @property
    def oldLeafId(self) -> str | None:
        return self.old_leaf_id

    @property
    def newLeafId(self) -> str | None:
        return self.new_leaf_id

    @property
    def customInstructions(self) -> str | None:
        return self.custom_instructions

    @property
    def replaceInstructions(self) -> bool:
        return self.replace_instructions


@dataclass(frozen=True)
class SessionActionDecision:
    cancel: bool = False
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class SessionBeforeForkResult(SessionActionDecision):
    skip_conversation_restore: bool = False


@dataclass(frozen=True)
class SessionBeforeCompactResult(SessionActionDecision):
    compaction: CompactionResult | None = None


@dataclass(frozen=True)
class SessionBeforeTreeResult(SessionActionDecision):
    summary: BranchSummaryResult | None = None
    custom_instructions: str | None = None
    replace_instructions: bool | None = None
    label: str | None = None


@dataclass
class ExtensionRuntimeBindings(ProductRuntimeBindings):
    get_model_selection: Callable[[], ModelSelection | None]
    set_model: Callable[[ModelSelection], Awaitable[None]]
    list_commands: Callable[[], list[SessionCommandDescriptor]] = lambda: []
    get_thinking_level: Callable[[], ThinkingLevel] = lambda: "off"
    set_thinking_level: Callable[[ThinkingLevel], Awaitable[None]] = (
        _ignore_thinking_level
    )


__all__ = [
    "BeforeAgentStartResult",
    "ContextResult",
    "ExtensionContext",
    "ExtensionCommandContext",
    "ReplacedSessionContext",
    "ExtensionHandler",
    "ExtensionResourceContribution",
    "ExtensionRuntimeBindings",
    "InputEvent",
    "InputEventResult",
    "InputSource",
    "LoadedExtension",
    "RegisteredCommand",
    "RegisteredFlag",
    "RegisteredShortcut",
    "ResolvedCommand",
    "ResolvedFlag",
    "ResolvedShortcut",
    "SourceInfo",
    "SessionActionDecision",
    "SessionStartEvent",
    "SessionShutdownEvent",
    "SessionBeforeCompactEvent",
    "SessionBeforeForkEvent",
    "SessionBeforeCompactResult",
    "SessionBeforeForkResult",
    "SessionBeforeSwitchEvent",
    "SessionBeforeTreeEvent",
    "SessionBeforeTreeResult",
    "SessionRefreshEvent",
    "ToolCallDecision",
    "ToolResultDecision",
    "VALID_EXTENSION_EVENTS",
]

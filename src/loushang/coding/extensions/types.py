from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import inspect
from pathlib import Path
from typing import Any, Literal, Protocol

from loushang.agent import AgentMessage, ThinkingLevel
from loushang.coding.compaction import BranchSummaryResult, CompactionResult
from loushang.coding.exec import ExecResult, ExecUpdateCallback
from loushang.coding.loader import (
    ExtensionDescriptor,
    PromptFragmentDescriptor,
    ResourceDiagnostic,
    SkillDescriptor,
    ThemeDescriptor,
)
from loushang.coding.loader.types import ResourceSourceKind, ResourceSourceScope
from loushang.coding.commands import SessionCommandDescriptor
from loushang.coding.source_info import SourceOrigin, SourceScope
from loushang.coding.tools import ToolDefinition
from loushang.coding.types import ModelSelection


VALID_EXTENSION_EVENTS = (
    "session_start",
    "session_before_switch",
    "session_before_fork",
    "session_before_compact",
    "session_before_tree",
    "session_compact",
    "session_tree",
    "session_refresh",
    "before_agent_start",
    "session_shutdown",
    "resources_discover",
    "input",
    "agent_start",
    "agent_end",
    "turn_start",
    "turn_end",
    "message_start",
    "message_update",
    "message_end",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
    "before_provider_request",
    "after_provider_response",
    "user_bash",
    "model_select",
    "context",
    "tool_call",
    "tool_result",
)


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

    def setThinkingLevel(self, level: ThinkingLevel) -> None: ...

    def set_thinking_level(self, level: ThinkingLevel) -> None: ...

    def appendEntry(self, custom_type: str, data: object | None = None) -> None: ...

    def append_entry(self, custom_type: str, data: object | None = None) -> None: ...

    async def sendMessage(self, message: object, options: object | None = None) -> None: ...

    async def send_message(self, message: object, options: object | None = None) -> None: ...

    async def sendUserMessage(self, content: object, options: object | None = None) -> None: ...

    async def send_user_message(self, content: object, options: object | None = None) -> None: ...

    def setSessionName(self, name: str | None) -> None: ...

    def set_session_name(self, name: str | None) -> None: ...

    def getSessionName(self) -> str | None: ...

    def get_session_name(self) -> str | None: ...

    def setLabel(self, entry_id: str, label: str | None) -> None: ...

    def set_label(self, entry_id: str, label: str | None) -> None: ...

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

    async def navigateTree(self, target_id: str, options: object | None = None) -> dict[str, object]: ...

    async def navigate_tree(self, target_id: str, options: object | None = None) -> dict[str, object]: ...

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]: ...

    async def newSession(self, options: object | None = None) -> dict[str, object]: ...

    async def new_session(self, options: object | None = None) -> dict[str, object]: ...

    async def switchSession(self, session_path: str, options: object | None = None) -> dict[str, object]: ...

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]: ...

    def shutdown(self) -> None: ...

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None: ...

    def notify(self, message: str, notify_type: str | None = None) -> None: ...

    def set_status(self, key: str, text: str | None) -> None: ...

    def setStatus(self, key: str, text: str | None) -> None: ...

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None: ...

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None: ...

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

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None: ...

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool: ...

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None: ...

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

    def appendEntry(self, custom_type: str, data: object | None = None) -> None: ...

    def append_entry(self, custom_type: str, data: object | None = None) -> None: ...

    async def sendMessage(self, message: object, options: object | None = None) -> None: ...

    async def send_message(self, message: object, options: object | None = None) -> None: ...

    async def sendUserMessage(self, content: object, options: object | None = None) -> None: ...

    async def send_user_message(self, content: object, options: object | None = None) -> None: ...

    def setSessionName(self, name: str | None) -> None: ...

    def set_session_name(self, name: str | None) -> None: ...

    def getSessionName(self) -> str | None: ...

    def get_session_name(self) -> str | None: ...

    def setLabel(self, entry_id: str, label: str | None) -> None: ...

    def set_label(self, entry_id: str, label: str | None) -> None: ...

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

    async def navigateTree(self, target_id: str, options: object | None = None) -> dict[str, object]: ...

    async def navigate_tree(self, target_id: str, options: object | None = None) -> dict[str, object]: ...

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]: ...

    async def newSession(self, options: object | None = None) -> dict[str, object]: ...

    async def new_session(self, options: object | None = None) -> dict[str, object]: ...

    async def switchSession(self, session_path: str, options: object | None = None) -> dict[str, object]: ...

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]: ...

    def shutdown(self) -> None: ...

    def record_diagnostic(self, diagnostic: ResourceDiagnostic) -> None: ...

    def notify(self, message: str, notify_type: str | None = None) -> None: ...

    def set_status(self, key: str, text: str | None) -> None: ...

    def setStatus(self, key: str, text: str | None) -> None: ...

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None: ...

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None: ...

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

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None: ...

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool: ...

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None: ...

    async def editor(self, title: str, prefill: str | None = None) -> str | None: ...


class ReplacedSessionContext(ExtensionCommandContext, Protocol):
    """Context passed to `withSession` callbacks after a session replacement."""


ExtensionHandler = Callable[[object, ExtensionContext], object | None]
InputSource = Literal["interactive", "rpc", "extension"]


@dataclass
class InputEvent:
    text: str
    images: list[object] | None = None
    source: InputSource = "interactive"
    type: Literal["input"] = "input"


@dataclass
class InputEventResult:
    action: Literal["continue", "transform", "handled"]
    text: str | None = None
    images: list[object] | None = None


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    source: str = "filesystem"
    scope: SourceScope = "project"
    origin: SourceOrigin = "top-level"
    base_dir: Path | None = None


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
class ExtensionRuntimeBindings:
    cwd: str
    get_active_tool_names: Callable[[], list[str]]
    get_model_selection: Callable[[], ModelSelection | None]
    set_active_tools: Callable[[list[str]], Awaitable[None]]
    set_model: Callable[[ModelSelection], Awaitable[None]]
    request_resource_refresh: Callable[[], None]
    shutdown: Callable[[], None]
    record_diagnostic: Callable[[ResourceDiagnostic], None]
    register_tool: Callable[[object, object | None], None] = lambda tool, source_info=None: None
    get_all_tools: Callable[[], list[object]] = lambda: []
    session_manager: object | None = None
    model_registry: object | None = None
    get_signal: Callable[[], object | None] = lambda: None
    append_entry: Callable[[str, object | None], None] = lambda custom_type, data=None: None
    send_message: Callable[[object, object | None], Awaitable[None]] | None = None
    send_user_message: Callable[[object, object | None], Awaitable[None]] | None = None
    set_session_name: Callable[[str | None], None] = lambda name: None
    get_session_name: Callable[[], str | None] = lambda: None
    set_label: Callable[[str, str | None], None] = lambda entry_id, label: None
    list_commands: Callable[[], list[SessionCommandDescriptor]] = lambda: []
    abort: Callable[[], None] = lambda: None
    is_idle: Callable[[], bool] = lambda: True
    has_pending_messages: Callable[[], bool] = lambda: False
    get_context_usage: Callable[[], object | None] = lambda: None
    get_thinking_level: Callable[[], ThinkingLevel] = lambda: "off"
    set_thinking_level: Callable[[ThinkingLevel], None] = lambda level: None
    register_provider: Callable[[str, object], None] | None = None
    unregister_provider: Callable[[str], None] | None = None
    set_extension_status: Callable[[str, str | None], None] = lambda key, text: None
    footer_data_provider: object | None = None
    compact: Callable[[str | None], Awaitable[object | None]] | None = None
    get_system_prompt: Callable[[], str] = lambda: ""
    wait_for_idle: Callable[[], Awaitable[None]] | None = None
    reload: Callable[[], Awaitable[None]] | None = None
    navigate_tree: Callable[[str, object | None], Awaitable[dict[str, object]]] | None = None
    fork: Callable[[str, object | None], Awaitable[dict[str, object]]] | None = None
    new_session: Callable[[object | None], Awaitable[dict[str, object]]] | None = None
    switch_session: Callable[[str, object | None], Awaitable[dict[str, object]]] | None = None
    exec_command: Callable[..., Awaitable[ExecResult]] | None = None
    ui_context: object | None = None
    on_error: Callable[[dict[str, object]], None] | None = None


@dataclass(frozen=True)
class BeforeAgentStartResult:
    system_prompt_append: str = ""
    system_prompt: str | None = None
    extra_messages: list[object] = field(default_factory=list)
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)
    block: bool = False
    reason: str | None = None

    @property
    def systemPrompt(self) -> str | None:
        return self.system_prompt

    @property
    def extraMessages(self) -> list[object]:
        return self.extra_messages


@dataclass(frozen=True)
class ContextResult:
    messages: list[AgentMessage] | None = None
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCallDecision:
    block: bool = False
    reason: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class ToolResultDecision:
    result: object | None = None
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class RegisteredCommand:
    name: str
    handler: Callable[[str, ExtensionCommandContext], Awaitable[None]]
    description: str | None = None
    get_argument_completions: Callable[[str], list[object] | Awaitable[list[object] | None] | None] | None = None

    def __post_init__(self) -> None:
        if not _is_async_callable(self.handler):
            raise TypeError("RegisteredCommand.handler must be an async callable.")


@dataclass(frozen=True, kw_only=True)
class ResolvedCommand(RegisteredCommand):
    invocation_name: str
    source_info: SourceInfo
    extension_name: str


@dataclass(frozen=True)
class RegisteredFlag:
    name: str
    type: Literal["boolean", "string"]
    description: str | None = None
    default: bool | str | None = None


@dataclass(frozen=True, kw_only=True)
class ResolvedFlag(RegisteredFlag):
    source_info: SourceInfo
    extension_name: str


@dataclass(frozen=True)
class RegisteredShortcut:
    shortcut: str
    handler: Callable[[ExtensionContext], object | None]
    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResolvedShortcut(RegisteredShortcut):
    source_info: SourceInfo
    extension_name: str


@dataclass(frozen=True)
class LoadedExtension:
    name: str
    source_path: Path
    entry_path: Path | None = None
    source: str = "filesystem"
    source_kind: ResourceSourceKind = "project_local"
    source_scope: ResourceSourceScope = "project"
    source_root: Path | None = None
    hooks: dict[str, list[ExtensionHandler]] = field(default_factory=dict)
    tool_definitions: list[ToolDefinition] = field(default_factory=list)
    commands: dict[str, RegisteredCommand] = field(default_factory=dict)
    flags: dict[str, RegisteredFlag] = field(default_factory=dict)
    shortcuts: dict[str, RegisteredShortcut] = field(default_factory=dict)
    message_renderers: dict[str, Callable[[object, object, object], object | None]] = field(default_factory=dict)
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    api: object | None = None


@dataclass(frozen=True)
class ExtensionResourceContribution:
    prompt_descriptors: list[PromptFragmentDescriptor] = field(default_factory=list)
    skills: list[SkillDescriptor] = field(default_factory=list)
    extensions: list[ExtensionDescriptor] = field(default_factory=list)
    prompts: list[PromptFragmentDescriptor] = field(default_factory=list)
    themes: list[ThemeDescriptor] = field(default_factory=list)
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


def _is_async_callable(value: object) -> bool:
    if inspect.iscoroutinefunction(value):
        return True
    call = getattr(value, "__call__", None)
    return inspect.iscoroutinefunction(call)


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

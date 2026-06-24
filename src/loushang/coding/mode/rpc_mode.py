from __future__ import annotations

import asyncio
import inspect
import io
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from math import isfinite
from pathlib import Path
from typing import Any, NotRequired, Required, TextIO, TypedDict, cast

from loushang.coding.commands import complete_slash_commands
from loushang.coding.diagnostics import (
    DiagnosticsQuery,
    serialize_diagnostic,
    serialize_diagnostic_summary,
    serialize_error_report,
)
from loushang.coding.event import (
    SUPPORTED_JSON_EVENT_VIEWS,
    JsonEventView,
    normalize_event_select,
    project_session_event,
    shape_stream_event,
    should_emit_projected_event,
)
from loushang.coding.message.json_codec import serialize_agent_message
from loushang.coding.mode.base import ModeAdapter, ModeState
from loushang.coding.store import SessionQuery
from loushang.coding.tools import ToolDefinitionResolver, ToolRenderRuntime
from loushang.coding.types import ModelSelection

_THINKING_LEVEL_ORDER: tuple[str, ...] = ("off", "minimal", "low", "medium", "high", "xhigh")
_MISSING = object()


class RpcModelCost(TypedDict):
    input: float | int
    output: float | int
    cacheRead: float | int
    cacheWrite: float | int


class RpcModel(TypedDict, total=False):
    provider: Required[str]
    id: Required[str]
    name: Required[str]
    endpointId: NotRequired[str]
    api: NotRequired[str]
    baseUrl: NotRequired[str]
    input: NotRequired[list[str]]
    contextWindow: NotRequired[int]
    maxTokens: NotRequired[int]
    reasoning: NotRequired[bool]
    cost: NotRequired[RpcModelCost]
    compat: NotRequired[dict[str, Any]]


class RpcSessionState(TypedDict, total=False):
    sessionId: Required[str]
    sessionName: NotRequired[str]
    sessionFile: NotRequired[str]
    model: Required[RpcModel | None]
    thinkingLevel: Required[str]
    isStreaming: Required[bool]
    isCompacting: Required[bool]
    steeringMode: Required[str | None]
    followUpMode: Required[str | None]
    autoCompactionEnabled: Required[bool | None]
    messageCount: Required[int]
    pendingMessageCount: Required[int]


class RpcExtensionUIContext:
    """RPC-backed extension UI context for headless hosts."""

    def __init__(self, output) -> None:
        self._output = output
        self._pending: dict[str, asyncio.Future[object]] = {}
        self._notifications: list[dict[str, object]] = []
        self._statuses: dict[str, str] = {}
        self._widgets: dict[str, dict[str, object]] = {}
        self._title: str | None = None
        self._editor_text = ""
        self._working_message: str | None = None
        self._working_visible = True
        self._working_indicator: object | None = None
        self._hidden_thinking_label: str | None = None
        self._footer: object | None = None
        self._header: object | None = None
        self._editor_component: object | None = None
        self._autocomplete_providers: list[object] = []
        self._tools_expanded = False

    async def select(self, title: str, options: list[str], *, timeout: float | None = None) -> str | None:
        response = await self._request_dialog(
            {"method": "select", "title": title, "options": list(options), **_timeout_payload(timeout)},
            timeout=timeout,
            default={"cancelled": True},
        )
        if response.get("cancelled") is True:
            return None
        value = response.get("value")
        return value if isinstance(value, str) else None

    async def confirm(self, title: str, message: str, *, timeout: float | None = None) -> bool:
        response = await self._request_dialog(
            {"method": "confirm", "title": title, "message": message, **_timeout_payload(timeout)},
            timeout=timeout,
            default={"confirmed": False},
        )
        return bool(response.get("confirmed", False)) if response.get("cancelled") is not True else False

    async def input(self, title: str, placeholder: str | None = None, *, timeout: float | None = None) -> str | None:
        payload: dict[str, object] = {"method": "input", "title": title, **_timeout_payload(timeout)}
        if placeholder is not None:
            payload["placeholder"] = placeholder
        response = await self._request_dialog(payload, timeout=timeout, default={"cancelled": True})
        if response.get("cancelled") is True:
            return None
        value = response.get("value")
        return value if isinstance(value, str) else None

    async def editor(self, title: str, prefill: str | None = None, *, timeout: float | None = None) -> str | None:
        payload: dict[str, object] = {"method": "editor", "title": title}
        if prefill is not None:
            payload["prefill"] = prefill
        if timeout is not None:
            payload["timeout"] = timeout
        response = await self._request_dialog(payload, timeout=timeout, default={"cancelled": True})
        if response.get("cancelled") is True:
            return None
        value = response.get("value")
        return value if isinstance(value, str) else None

    def notify(self, message: str, notify_type: str | None = None) -> None:
        payload: dict[str, object] = {"method": "notify", "message": message}
        if notify_type is not None:
            payload["notifyType"] = notify_type
        self._notifications.append({key: value for key, value in payload.items() if key != "method"})
        self._emit_request(payload)

    def set_status(self, key: str, text: str | None) -> None:
        payload: dict[str, object] = {"method": "setStatus", "statusKey": key}
        if text is not None:
            payload["statusText"] = text
            self._statuses[key] = text
        else:
            self._statuses.pop(key, None)
        self._emit_request(payload)

    def setStatus(self, key: str, text: str | None) -> None:
        self.set_status(key, text)

    def set_widget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        payload: dict[str, object] = {"method": "setWidget", "widgetKey": key}
        if lines is not None:
            payload["widgetLines"] = list(lines)
        if placement is not None:
            payload["widgetPlacement"] = placement
        if lines is None:
            self._widgets.pop(key, None)
        else:
            widget: dict[str, object] = {"lines": list(lines)}
            if placement is not None:
                widget["placement"] = placement
            self._widgets[key] = widget
        self._emit_request(payload)

    def setWidget(self, key: str, lines: list[str] | None, *, placement: str | None = None) -> None:
        self.set_widget(key, lines, placement=placement)

    def set_title(self, title: str) -> None:
        self._title = title
        self._emit_request({"method": "setTitle", "title": title})

    def setTitle(self, title: str) -> None:
        self.set_title(title)

    def set_editor_text(self, text: str) -> None:
        self._editor_text = text
        self._emit_request({"method": "set_editor_text", "text": text})

    def setEditorText(self, text: str) -> None:
        self.set_editor_text(text)

    def pasteToEditor(self, text: str) -> None:
        self.set_editor_text(text)

    def getEditorText(self) -> str:
        return self._editor_text

    def onTerminalInput(self, handler) -> object:
        del handler
        return lambda: None

    def setWorkingMessage(self, message: str | None = None) -> None:
        self._working_message = message

    def setWorkingVisible(self, visible: bool) -> None:
        self._working_visible = visible

    def setWorkingIndicator(self, options: object | None = None) -> None:
        self._working_indicator = options

    def setHiddenThinkingLabel(self, label: str | None = None) -> None:
        self._hidden_thinking_label = label

    def setFooter(self, factory: object | None) -> None:
        self._footer = factory

    def setHeader(self, factory: object | None) -> None:
        self._header = factory

    def addAutocompleteProvider(self, factory: object) -> None:
        self._autocomplete_providers.append(factory)

    def setEditorComponent(self, factory: object | None) -> None:
        self._editor_component = factory

    def getAllThemes(self) -> list[object]:
        return []

    def getTheme(self, name: str) -> object | None:
        del name
        return None

    def setTheme(self, theme: object) -> dict[str, object]:
        del theme
        return {"success": False, "error": "Theme switching not supported in RPC mode"}

    def getToolsExpanded(self) -> bool:
        return self._tools_expanded

    def setToolsExpanded(self, expanded: bool) -> None:
        self._tools_expanded = expanded

    def get_snapshot(self) -> dict[str, object]:
        snapshot: dict[str, object] = {
            "notifications": list(self._notifications),
            "statuses": dict(self._statuses),
            "widgets": {key: dict(value) for key, value in self._widgets.items()},
            "title": self._title,
            "editorText": self._editor_text,
            "workingMessage": self._working_message,
            "workingVisible": self._working_visible,
            "workingIndicator": self._working_indicator,
            "hiddenThinkingLabel": self._hidden_thinking_label,
            "hasFooter": self._footer is not None,
            "hasHeader": self._header is not None,
            "hasEditorComponent": self._editor_component is not None,
            "autocompleteProviderCount": len(self._autocomplete_providers),
            "toolsExpanded": self._tools_expanded,
        }
        return snapshot

    def emit_extension_error(self, error: dict[str, object]) -> None:
        self._output(
            {
                "type": "extension_error",
                "extensionPath": str(error.get("extensionPath", "")),
                "event": str(error.get("event", "")),
                "error": str(error.get("error", "")),
            }
        )

    def resolve_response(self, response: dict[str, object]) -> None:
        request_id = response.get("id")
        if not isinstance(request_id, str):
            return
        future = self._pending.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(response)

    async def _request_dialog(
        self,
        payload: dict[str, object],
        *,
        timeout: float | None,
        default: dict[str, object],
    ) -> dict[str, object]:
        request_id = self._emit_request(payload)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[object] = loop.create_future()
        self._pending[request_id] = future
        try:
            result = await asyncio.wait_for(future, timeout=timeout) if timeout is not None else await future
        except TimeoutError:
            self._pending.pop(request_id, None)
            return default
        return result if isinstance(result, dict) else {}

    def _emit_request(self, payload: dict[str, object]) -> str:
        request_id = str(uuid.uuid4())
        self._output({"type": "extension_ui_request", "id": request_id, **payload})
        return request_id


class RpcMode(ModeAdapter):
    """JSONL RPC shell for driving an active coding session."""

    def __init__(
        self,
        *,
        runtime: Any,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO | None = None,
        event_view: JsonEventView = "full",
        event_select: str | Sequence[str] | None = None,
        render_tool_events: bool = False,
    ) -> None:
        if event_view not in SUPPORTED_JSON_EVENT_VIEWS:
            raise ValueError(f"unsupported json event view: {event_view}")
        self.runtime = runtime
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = sys.stderr if stderr is None else stderr
        self.event_view = event_view
        self.event_select = normalize_event_select(event_select)
        self.render_tool_events = render_tool_events
        self._stdin_uses_thread = _stream_supports_fileno(stdin)
        self.session = self._require_current_session()
        self._tool_render_runtime: ToolRenderRuntime | None = None
        self._tool_definition_resolver: ToolDefinitionResolver | None = None
        self._configure_tool_rendering(self.session)
        self._unsubscribe = self.session.subscribe(self._handle_event)
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._active_prompt_task: asyncio.Task[None] | None = None
        self._active_bash_task: asyncio.Task[None] | None = None
        self._running = True
        self.extension_ui_context = RpcExtensionUIContext(self._write_json_line)
        self._bind_extension_ui_context(self.session)

    async def start(self, user_input: str | None = None) -> int:
        del user_input
        return await self.run()

    async def stop(self) -> int:
        self._running = False
        self._unsubscribe()
        return 0

    async def submit_input(self, input_payload: object) -> int:
        if not isinstance(input_payload, str):
            raise TypeError("Rpc mode submit_input expects a string")
        try:
            await self._handle_line(input_payload)
        except Exception:
            return 1
        return 0

    async def wait_for_idle(self) -> int:
        await self.session.wait_for_idle()
        return 0

    def rebind_session(self, session: object | None = None) -> int:
        if session is None:
            session = self._require_current_session()
        self._bind_session(session)
        return 0

    async def dispose(self) -> int:
        self._running = False
        self._unsubscribe()
        disposer = getattr(self.runtime, "dispose", None)
        if callable(disposer):
            await disposer()
        return 0

    def render_event(self, event: object) -> None:
        self._handle_event(event)

    async def run(self) -> int:
        try:
            while self._running:
                line = await self._read_line()
                if line == "":
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                await self._handle_line(stripped)
            await self._drain_background_tasks()
            return 0
        except Exception as exc:
            self.stderr.write(f"Error: {exc}\n")
            return 1
        finally:
            self._unsubscribe()

    def get_mode_state(self) -> ModeState:
        try:
            return self._serialize_session_state(self.session)
        except Exception:
            return {
                "sessionId": "",
                "thinkingLevel": "off",
                "isStreaming": False,
                "isCompacting": False,
                "steeringMode": "one-at-a-time",
                "followUpMode": "one-at-a-time",
                "autoCompactionEnabled": False,
                "messageCount": 0,
                "pendingMessageCount": 0,
                "model": None,
            }

    async def _read_line(self) -> str:
        if self._stdin_uses_thread:
            return await asyncio.to_thread(self.stdin.readline)
        return self.stdin.readline()

    async def _handle_line(self, line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            self._write_response_error(command="parse", error=f"Failed to parse command: {exc.msg}")
            return

        if not isinstance(payload, dict):
            self._write_response_error(command="invalid", error="RPC commands must be JSON objects")
            return

        if payload.get("type") == "extension_ui_response":
            self.extension_ui_context.resolve_response(payload)
            return

        command_id = payload.get("id")
        if command_id is not None and not isinstance(command_id, str):
            self._write_response_error(command="invalid", error="command id must be a string")
            return

        command_type = payload.get("type")
        if not isinstance(command_type, str) or not command_type:
            self._write_response_error(id=command_id, command="invalid", error="RPC command missing string type")
            return

        handler = getattr(self, f"_handle_{command_type}_command", None)
        if handler is None:
            self._write_response_error(
                id=command_id,
                command=command_type,
                error=f"unsupported command: {command_type}",
                code="unsupported_command",
            )
            return

        try:
            result = handler(command_id, payload)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            self._write_response_error(id=command_id, command=command_type, error=str(exc))

    async def _handle_prompt_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        message = self._require_string(payload, "message")
        streaming_behavior = payload.get("streamingBehavior", payload.get("streaming_behavior"))
        images = self._coerce_images(payload.get("images"))
        task = asyncio.create_task(
            self._run_prompt(
                session=self.session,
                command_id=command_id,
                message=message,
                images=images,
                streaming_behavior=streaming_behavior if isinstance(streaming_behavior, str) else None,
            )
        )
        self._active_prompt_task = task
        self._track_background_task(task)

    async def _run_prompt(
        self,
        *,
        session: Any,
        command_id: str | None,
        message: str,
        images: list[object] | None,
        streaming_behavior: str | None,
    ) -> None:
        preflight_succeeded = False

        def on_preflight(did_succeed: bool) -> None:
            nonlocal preflight_succeeded
            if did_succeed and not preflight_succeeded:
                preflight_succeeded = True
                self._write_response_success(id=command_id, command="prompt")

        try:
            await session.prompt(
                message,
                images=images,
                streaming_behavior=streaming_behavior,
                source="rpc",
                preflight_result=on_preflight,
            )
            await session.wait_for_idle()
        except Exception as exc:
            if not preflight_succeeded:
                self._write_response_error(id=command_id, command="prompt", error=str(exc))
        else:
            if not preflight_succeeded:
                self._write_response_success(id=command_id, command="prompt")
        finally:
            if self._active_prompt_task is asyncio.current_task():
                self._active_prompt_task = None

    def _handle_steer_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self.session.steer(self._require_string(payload, "message"), images=self._coerce_images(payload.get("images")))
        self._write_response_success(id=command_id, command="steer")

    def _handle_follow_up_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self.session.follow_up(self._require_string(payload, "message"), images=self._coerce_images(payload.get("images")))
        self._write_response_success(id=command_id, command="follow_up")

    def _handle_abort_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        self.session.abort()
        self._write_response_success(id=command_id, command="abort")

    def _handle_get_state_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        try:
            state = self._serialize_session_state(self.session)
        except Exception:
            self._write_response_error(
                id=command_id,
                command="get_state",
                error="Failed to serialize session state.",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_state",
            data=state,
        )

    def _handle_get_extension_ui_state_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        self._write_response_success(
            id=command_id,
            command="get_extension_ui_state",
            data=self.extension_ui_context.get_snapshot(),
        )

    def _handle_get_messages_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        messages = self._get_session_messages(self.session)
        if not isinstance(messages, list):
            self._write_response_error(
                id=command_id,
                command="get_messages",
                error="Message log returned an invalid response.",
            )
            return
        serialized_messages: list[dict[str, Any]] = []
        for message in messages:
            try:
                serialized_messages.append(serialize_agent_message(message))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command="get_messages",
            data={"messages": serialized_messages},
        )

    def _handle_list_sessions_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        try:
            query = self._session_query_from_payload(payload)
        except ValueError as error:
            self._write_response_error(id=command_id, command="list_sessions", error=str(error))
            return
        all_sessions = payload.get("allSessions", payload.get("all_sessions", False))
        if not isinstance(all_sessions, bool):
            raise ValueError("list_sessions allSessions must be boolean")
        use_index = payload.get("useIndex", payload.get("use_index", False))
        refresh_index = payload.get("refreshIndex", payload.get("refresh_index", False))
        if not isinstance(use_index, bool):
            raise ValueError("list_sessions useIndex must be boolean")
        if not isinstance(refresh_index, bool):
            raise ValueError("list_sessions refreshIndex must be boolean")
        use_index = use_index or refresh_index
        if refresh_index:
            refresher = getattr(self.runtime, "refresh_all_session_indexes" if all_sessions else "refresh_session_index", None)
            if not callable(refresher):
                self._write_response_error(
                    id=command_id,
                    command="list_sessions",
                    error="Session index refresh is not available.",
                )
                return
            try:
                refresher()
            except Exception as error:
                self._write_response_error(
                    id=command_id,
                    command="list_sessions",
                    error=f"Failed to refresh session index: {error}",
                )
                return
        finder = (
            getattr(self.runtime, "find_all_indexed_session_summaries" if use_index else "find_all_session_summaries", None)
            if all_sessions
            else None
        )
        if not callable(finder):
            finder = getattr(self.runtime, "find_indexed_session_summaries" if use_index else "find_session_summaries", None)
        if callable(finder):
            def lister():
                return finder(query)
        else:
            if all_sessions:
                lister = getattr(self.runtime, "list_all_indexed_session_summaries" if use_index else "list_all_session_summaries", None)
            else:
                lister = getattr(self.runtime, "list_indexed_session_summaries" if use_index else "list_session_summaries", None)
            if not callable(lister) and not use_index:
                lister = getattr(self.runtime, "list_sessions", None)
        if not callable(lister):
            self._write_response_error(
                id=command_id,
                command="list_sessions",
                error="Session listing is not available.",
            )
            return
        try:
            raw_sessions = lister()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="list_sessions",
                error=f"Failed to list sessions: {error}",
            )
            return
        if not isinstance(raw_sessions, list):
            self._write_response_error(
                id=command_id,
                command="list_sessions",
                error="Session listing returned an invalid response.",
            )
            return
        sessions = []
        for session in raw_sessions:
            try:
                sessions.append(self._serialize_session_listing_item(session))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command="list_sessions",
            data={"sessions": sessions},
        )

    def _session_query_from_payload(self, payload: dict[str, Any]) -> SessionQuery:
        limit = self._optional_int(payload, "limit")
        if limit is not None and limit < 0:
            raise ValueError("Session limit must be non-negative.")
        return SessionQuery(
            cwd=self._optional_string(payload, "cwd"),
            name=self._optional_string(payload, "name"),
            parent_session=self._optional_string(payload, "parentSession", "parent_session"),
            text=self._optional_string(payload, "text", "query"),
            has_diagnostics=self._optional_bool(payload, "hasDiagnostics", "has_diagnostics"),
            limit=limit,
        )

    async def _handle_new_session_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        previous = self.session
        try:
            session = await self.runtime.new_session(
                cwd=self._optional_path(payload.get("cwd")),
                parent_session=self._optional_string(payload, "parentSession", "parent_session"),
            )
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="new_session",
                error=f"Failed to create new session: {error}",
            )
            return
        self._bind_session(session)
        self._write_response_success(
            id=command_id,
            command="new_session",
            data={
                "cancelled": session is previous,
            },
        )

    async def _handle_switch_session_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        previous = self.session
        session_id = payload.get("sessionId", payload.get("session_id", payload.get("sessionPath")))
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("switch_session requires sessionId")
        try:
            session = await self.runtime.switch_session(session_id)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="switch_session",
                error=f"Failed to switch session: {error}",
            )
            return
        self._bind_session(session)
        self._write_response_success(
            id=command_id,
            command="switch_session",
            data={
                "cancelled": session is previous,
            },
        )

    async def _handle_fork_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        previous = self.session
        entry_id = payload.get("entryId", payload.get("entry_id"))
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("fork requires entryId")
        try:
            position = payload.get("position", "before")
            if position not in {"before", "at"}:
                raise ValueError("fork position must be 'before' or 'at'")
            fork_with_result = getattr(self.runtime, "fork_session_with_result", None)
            if callable(fork_with_result):
                session, text = await fork_with_result(entry_id, position=position)
            else:
                text = self._extract_session_entry_text(entry_id) if position == "before" else None
                session = await self.runtime.fork_session(entry_id)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="fork",
                error=f"Failed to fork session: {error}",
            )
            return
        self._bind_session(session)
        self._write_response_success(
            id=command_id,
            command="fork",
            data={
                "cancelled": session is previous,
                "text": text,
            },
        )

    async def _handle_clone_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        previous = self.session
        try:
            session = await self.runtime.clone_session()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="clone",
                error=f"Failed to clone session: {error}",
            )
            return
        self._bind_session(session)
        self._write_response_success(
            id=command_id,
            command="clone",
            data={"cancelled": session is previous},
        )

    async def _handle_set_model_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        provider = self._require_string(payload, "provider")
        model_id = self._require_string(payload, "modelId", "model_id")
        endpoint_id = payload.get("endpointId") or payload.get("endpoint_id")
        selection = ModelSelection(
            provider=provider,
            model_id=model_id,
            endpoint_id=endpoint_id if isinstance(endpoint_id, str) else None,
        )
        try:
            available_models = self.session.get_available_models()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_model",
                error=f"Failed to query model registry: {error}",
            )
            return
        if not isinstance(available_models, list):
            self._write_response_error(
                id=command_id,
                command="set_model",
                error="Model registry returned an invalid response.",
            )
            return
        if available_models and selection not in available_models:
            self._write_response_error(
                id=command_id,
                command="set_model",
                error=f"Model not found: {provider}/{model_id}",
            )
            return
        try:
            await self.session.set_model(selection)
        except KeyError:
            self._write_response_error(
                id=command_id,
                command="set_model",
                error=f"Model not found: {provider}/{model_id}",
            )
            return
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_model",
                error=f"Failed to set model: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="set_model",
            data=self._serialize_state_model(self.session, self.session.get_state()),
        )

    def _handle_get_available_models_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        getter = getattr(self.session, "get_available_models", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_available_models",
                error="Model registry is not available.",
            )
            return
        try:
            models = getter()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_available_models",
                error=f"Failed to query model registry: {error}",
            )
            return
        if not isinstance(models, list):
            self._write_response_error(
                id=command_id,
                command="get_available_models",
                error="Model registry returned an invalid response.",
            )
            return
        try:
            serialized = self._serialize_available_models(self.session, models)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_available_models",
                error=f"Failed to serialize model registry: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_available_models",
            data={"models": serialized},
        )

    async def _handle_cycle_model_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        try:
            selection = await self.session.cycle_model()
        except TypeError as error:
            if str(error) == "Model registry returned an invalid response.":
                self._write_response_error(
                    id=command_id,
                    command="cycle_model",
                    error=str(error),
                )
                return
            self._write_response_error(
                id=command_id,
                command="cycle_model",
                error=f"Failed to cycle model: {error}",
            )
            return
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="cycle_model",
                error=f"Failed to cycle model: {error}",
            )
            return
        if selection is None:
            self._write_response_success(
                id=command_id,
                command="cycle_model",
                data=None,
            )
            return
        try:
            model = self._serialize_state_model(self.session, self.session.get_state())
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="cycle_model",
                error=f"Failed to serialize model: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="cycle_model",
            data={
                "model": model,
                "thinkingLevel": self.session.get_state().thinking_level,
                "isScoped": False,
            },
        )

    async def _handle_set_active_tools_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        tool_names = payload.get("toolNames", payload.get("tool_names"))
        if not isinstance(tool_names, list) or not all(isinstance(name, str) and name for name in tool_names):
            raise ValueError("set_active_tools requires toolNames")
        try:
            await self.session.set_active_tools(tool_names)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_active_tools",
                error=f"Failed to set active tools: {error}",
            )
            return
        try:
            state = self._serialize_session_state(self.session)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_active_tools",
                error=f"Failed to read session state: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="set_active_tools",
            data=state,
        )

    def _handle_set_thinking_level_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        level = self._require_string(payload, "level")
        try:
            self.session.set_thinking_level(level)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_thinking_level",
                error=f"Failed to set thinking level: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_thinking_level")

    def _handle_cycle_thinking_level_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        try:
            next_level = self.session.cycle_thinking_level()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="cycle_thinking_level",
                error=f"Failed to set thinking level: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="cycle_thinking_level",
            data={"level": next_level},
        )

    def _handle_set_steering_mode_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        mode = self._require_mode(payload, "mode")
        try:
            self.session.set_steering_mode(mode)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_steering_mode",
                error=f"Failed to set steering mode: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_steering_mode")

    def _handle_set_follow_up_mode_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        mode = self._require_mode(payload, "mode")
        try:
            self.session.set_follow_up_mode(mode)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_follow_up_mode",
                error=f"Failed to set follow-up mode: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_follow_up_mode")

    def _handle_get_session_stats_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        getter = getattr(self.session, "get_session_stats", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_session_stats",
                error="Session stats are not available.",
            )
            return
        try:
            stats = getter()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_session_stats",
                error=f"Failed to query session stats: {error}",
            )
            return
        try:
            serialized = self._serialize_session_stats(stats)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_session_stats",
                error=f"Session stats returned an invalid response: {error}",
            )
            return
        if not isinstance(serialized, dict):
            self._write_response_error(
                id=command_id,
                command="get_session_stats",
                error="Session stats returned an invalid response.",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_session_stats",
            data=serialized,
        )

    def _handle_set_session_name_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        name = self._require_string(payload, "name").strip()
        if not name:
            self._write_response_error(id=command_id, command="set_session_name", error="Session name cannot be empty")
            return
        try:
            self.session.set_session_name(name)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_session_name",
                error=f"Failed to set session name: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_session_name")

    def _handle_get_last_assistant_text_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        try:
            text = self._extract_last_assistant_text()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_last_assistant_text",
                error=f"Failed to read last assistant text: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_last_assistant_text",
            data={"text": text},
        )

    def _handle_get_fork_messages_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        getter = getattr(self.session, "getUserMessagesForForking", None)
        if not callable(getter):
            getter = getattr(self.session, "get_user_messages_for_forking", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_fork_messages",
                error="Fork messages are not available.",
            )
            return
        try:
            raw_messages = getter()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_fork_messages",
                error=f"Failed to query fork messages: {error}",
            )
            return
        if not isinstance(raw_messages, list):
            self._write_response_error(
                id=command_id,
                command="get_fork_messages",
                error="Fork messages returned an invalid response.",
            )
            return
        messages = self._camelize(self._serialize_json_value(raw_messages))
        self._write_response_success(
            id=command_id,
            command="get_fork_messages",
            data={"messages": messages},
        )

    def _handle_get_commands_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        commands = []
        getter = getattr(self.session, "list_commands", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_commands",
                error="Command registry is not available.",
            )
            return
        try:
            raw_commands = getter()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_commands",
                error=f"Failed to query commands: {error}",
            )
            return
        if not isinstance(raw_commands, list):
            self._write_response_error(
                id=command_id,
                command="get_commands",
                error="Command registry returned an invalid response.",
            )
            return
        for command in raw_commands:
            try:
                commands.append(self._serialize_command_descriptor(command))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command="get_commands",
            data={"commands": commands},
        )

    async def _handle_get_command_completions_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        prefix = payload.get("prefix", "")
        if not isinstance(prefix, str):
            self._write_response_error(
                id=command_id,
                command="get_command_completions",
                error="Command completion prefix must be a string.",
                code="invalid_request",
            )
            return
        command_name = payload.get("command")
        if command_name is not None:
            if not isinstance(command_name, str) or not command_name:
                self._write_response_error(
                    id=command_id,
                    command="get_command_completions",
                    error="Command completion command must be a non-empty string.",
                    code="invalid_request",
                )
                return
            getter = getattr(self.session, "get_command_argument_completions", None)
            if not callable(getter):
                self._write_response_success(
                    id=command_id,
                    command="get_command_completions",
                    data={"completions": []},
                )
                return
            try:
                completions = await getter(command_name, prefix)
            except Exception as error:
                self._write_response_error(
                    id=command_id,
                    command="get_command_completions",
                    error=f"Failed to query command completions: {error}",
                    code="command_completion_failed",
                )
                return
            self._write_response_success(
                id=command_id,
                command="get_command_completions",
                data={"completions": completions if isinstance(completions, list) else []},
            )
            return

        getter = getattr(self.session, "list_commands", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_command_completions",
                error="Command registry is not available.",
                code="command_registry_unavailable",
            )
            return
        try:
            raw_commands = getter()
            if not isinstance(raw_commands, list):
                raise TypeError("Command registry returned an invalid response.")
            completions = complete_slash_commands(prefix, raw_commands)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_command_completions",
                error=f"Failed to query command completions: {error}",
                code="command_completion_failed",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_command_completions",
            data={"completions": completions},
        )

    def _handle_get_diagnostics_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self._handle_diagnostics_query_command(
            command_id=command_id,
            payload=payload,
            command="get_diagnostics",
            runtime_method="get_diagnostics",
            session_method="get_diagnostics",
            fallback_to_last=True,
        )

    def _handle_get_session_diagnostics_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self._handle_diagnostics_query_command(
            command_id=command_id,
            payload=payload,
            command="get_session_diagnostics",
            runtime_method="get_session_diagnostics",
            session_method="get_session_diagnostics",
            fallback_to_last=False,
        )

    def _handle_get_diagnostics_summary_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self._handle_diagnostics_summary_command(
            command_id=command_id,
            payload=payload,
            command="get_diagnostics_summary",
            runtime_method="get_diagnostics_summary",
            session_method="get_diagnostics_summary",
        )

    def _handle_get_session_diagnostics_summary_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self._handle_diagnostics_summary_command(
            command_id=command_id,
            payload=payload,
            command="get_session_diagnostics_summary",
            runtime_method="get_session_diagnostics_summary",
            session_method="get_session_diagnostics_summary",
        )

    def _handle_diagnostics_query_command(
        self,
        *,
        command_id: str | None,
        payload: dict[str, Any],
        command: str,
        runtime_method: str,
        session_method: str,
        fallback_to_last: bool,
    ) -> None:
        raw_limit = payload.get("limit", 50)
        if not isinstance(raw_limit, int) or raw_limit <= 0:
            self._write_response_error(
                id=command_id,
                command=command,
                error="Diagnostic limit must be a positive integer.",
            )
            return

        query = self._diagnostics_query_from_payload(payload, default_limit=raw_limit)
        getter = getattr(self.runtime, runtime_method, None)
        if callable(getter):
            def get_diagnostics():
                return getter(query=query)
        else:
            getter = getattr(self.session, session_method, None)
            if callable(getter):
                def get_diagnostics():
                    return getter(query=query)
            else:
                getter = getattr(self.session, "get_last_diagnostics", None) if fallback_to_last else None
                if callable(getter):
                    def get_diagnostics():
                        return getter(limit=raw_limit)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command=command,
                error="Diagnostics are not available.",
            )
            return
        try:
            raw_diagnostics = get_diagnostics()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command=command,
                error=f"Failed to query diagnostics: {error}",
            )
            return
        if not isinstance(raw_diagnostics, list):
            self._write_response_error(
                id=command_id,
                command=command,
                error="Diagnostics returned an invalid response.",
            )
            return

        diagnostics = []
        for record in raw_diagnostics:
            try:
                diagnostics.append(serialize_diagnostic(record))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command=command,
            data={"diagnostics": diagnostics},
        )

    def _handle_diagnostics_summary_command(
        self,
        *,
        command_id: str | None,
        payload: dict[str, Any],
        command: str,
        runtime_method: str,
        session_method: str,
    ) -> None:
        try:
            query = self._diagnostics_query_from_payload(payload, default_limit=None)
        except ValueError as error:
            self._write_response_error(id=command_id, command=command, error=str(error))
            return
        getter = getattr(self.runtime, runtime_method, None)
        if callable(getter):
            def get_summary():
                return getter(query=query)
        else:
            getter = getattr(self.session, session_method, None)
            if callable(getter):
                def get_summary():
                    return getter(query=query)
        if not callable(getter):
            self._write_response_error(id=command_id, command=command, error="Diagnostics are not available.")
            return
        try:
            summary = serialize_diagnostic_summary(get_summary())
        except Exception as error:
            self._write_response_error(id=command_id, command=command, error=f"Failed to query diagnostics: {error}")
            return
        self._write_response_success(id=command_id, command=command, data={"summary": summary})

    def _diagnostics_query_from_payload(self, payload: dict[str, Any], *, default_limit: int | None) -> DiagnosticsQuery:
        raw_limit = payload.get("limit", default_limit)
        if raw_limit is not None and (not isinstance(raw_limit, int) or raw_limit <= 0):
            raise ValueError("Diagnostic limit must be a positive integer.")
        return DiagnosticsQuery(
            phase=self._optional_string(payload, "phase"),  # type: ignore[arg-type]
            source=self._optional_string(payload, "source"),  # type: ignore[arg-type]
            level=self._optional_string(payload, "level", "diagnosticType", "diagnostic_type"),  # type: ignore[arg-type]
            session_id=self._optional_string(payload, "sessionId", "session_id"),
            entry_id=self._optional_string(payload, "entryId", "entry_id"),
            tool_call_id=self._optional_string(payload, "toolCallId", "tool_call_id"),
            code=self._optional_string(payload, "code"),
            limit=raw_limit,
        )

    def _handle_get_last_error_report_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        getter = getattr(self.session, "get_last_error_report", None)
        if not callable(getter):
            self._write_response_error(
                id=command_id,
                command="get_last_error_report",
                error="Diagnostics are not available.",
            )
            return
        try:
            report = serialize_error_report(getter())
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_last_error_report",
                error=f"Failed to query last error report: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="get_last_error_report",
            data={"report": report},
        )

    def _handle_get_packages_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        catalog_path = self._optional_string(payload, "catalogPath", "catalog_path")
        getter = getattr(self.runtime, "get_packages", None)
        if callable(getter):
            get_packages = getter
        else:
            getter = getattr(self.session, "get_packages", None)
            if not callable(getter):
                self._write_response_error(
                    id=command_id,
                    command="get_packages",
                    error="Package listing is not available.",
                )
                return
            get_packages = getter
        try:
            packages = get_packages(catalog_path=catalog_path)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="get_packages",
                error=f"Failed to query packages: {error}",
                code="package_query_failed",
            )
            return
        if not isinstance(packages, list):
            self._write_response_error(
                id=command_id,
                command="get_packages",
                error="Package listing returned an invalid response.",
                code="invalid_package_query_response",
            )
            return
        self._write_response_success(id=command_id, command="get_packages", data={"packages": packages})

    async def _handle_materialize_package_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_lifecycle_command(
            command_id=command_id,
            payload=payload,
            command="materialize_package",
            method_name="materialize_package",
            unavailable_message="Package materialization is not available.",
            failure_message="Failed to materialize package",
            invalid_message="Package materialization returned an invalid response.",
            failure_code="package_materialization_failed",
            invalid_code="invalid_package_materialization_response",
        )

    async def _handle_install_package_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_lifecycle_command(
            command_id=command_id,
            payload=payload,
            command="install_package",
            method_name="install_package",
            unavailable_message="Package installation is not available.",
            failure_message="Failed to install package",
            invalid_message="Package installation returned an invalid response.",
            failure_code="package_installation_failed",
            invalid_code="invalid_package_installation_response",
        )

    async def _handle_update_package_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_lifecycle_command(
            command_id=command_id,
            payload=payload,
            command="update_package",
            method_name="update_package",
            unavailable_message="Package update is not available.",
            failure_message="Failed to update package",
            invalid_message="Package update returned an invalid response.",
            failure_code="package_update_failed",
            invalid_code="invalid_package_update_response",
        )

    async def _handle_update_packages_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_collection_command(
            command_id=command_id,
            command="update_packages",
            method_name="update_packages",
            data_key="records",
            unavailable_message="Package update is not available.",
            failure_message="Failed to update packages",
            invalid_message="Package update returned an invalid response.",
            failure_code="package_update_failed",
            invalid_code="invalid_package_update_response",
        )

    async def _handle_check_package_updates_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_collection_command(
            command_id=command_id,
            command="check_package_updates",
            method_name="check_package_updates",
            data_key="updates",
            unavailable_message="Package update check is not available.",
            failure_message="Failed to check package updates",
            invalid_message="Package update check returned an invalid response.",
            failure_code="package_update_check_failed",
            invalid_code="invalid_package_update_check_response",
        )

    async def _handle_remove_package_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_lifecycle_command(
            command_id=command_id,
            payload=payload,
            command="remove_package",
            method_name="remove_package",
            unavailable_message="Package removal is not available.",
            failure_message="Failed to remove package",
            invalid_message="Package removal returned an invalid response.",
            failure_code="package_removal_failed",
            invalid_code="invalid_package_removal_response",
        )

    async def _handle_uninstall_package_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        await self._handle_package_lifecycle_command(
            command_id=command_id,
            payload=payload,
            command="uninstall_package",
            method_name="uninstall_package",
            unavailable_message="Package uninstallation is not available.",
            failure_message="Failed to uninstall package",
            invalid_message="Package uninstallation returned an invalid response.",
            failure_code="package_uninstallation_failed",
            invalid_code="invalid_package_uninstallation_response",
        )

    async def _handle_package_collection_command(
        self,
        *,
        command_id: str | None,
        command: str,
        method_name: str,
        data_key: str,
        unavailable_message: str,
        failure_message: str,
        invalid_message: str,
        failure_code: str,
        invalid_code: str,
    ) -> None:
        method = getattr(self.runtime, method_name, None)
        if not callable(method):
            method = getattr(self.session, method_name, None)
        if not callable(method):
            self._write_response_error(id=command_id, command=command, error=unavailable_message)
            return
        try:
            result = method()
            if inspect.isawaitable(result):
                result = await result
        except Exception as error:
            self._write_response_error(id=command_id, command=command, error=f"{failure_message}: {error}", code=failure_code)
            return
        if not isinstance(result, list):
            self._write_response_error(id=command_id, command=command, error=invalid_message, code=invalid_code)
            return
        self._write_response_success(id=command_id, command=command, data={data_key: result})

    async def _handle_package_lifecycle_command(
        self,
        *,
        command_id: str | None,
        payload: dict[str, Any],
        command: str,
        method_name: str,
        unavailable_message: str,
        failure_message: str,
        invalid_message: str,
        failure_code: str,
        invalid_code: str,
    ) -> None:
        source = self._require_string(payload, "source")
        getter = getattr(self.runtime, method_name, None)
        if callable(getter):
            lifecycle_method = getter
        else:
            getter = getattr(self.session, method_name, None)
            if not callable(getter):
                self._write_response_error(
                    id=command_id,
                    command=command,
                    error=unavailable_message,
                )
                return
            lifecycle_method = getter
        try:
            record = lifecycle_method(source)
            if inspect.isawaitable(record):
                record = await record
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command=command,
                error=f"{failure_message}: {error}",
                code=failure_code,
            )
            return
        if not isinstance(record, dict):
            self._write_response_error(
                id=command_id,
                command=command,
                error=invalid_message,
                code=invalid_code,
            )
            return
        if failure := _package_lifecycle_failure(record):
            self._write_response_error(
                id=command_id,
                command=command,
                error=f"{failure_message}: {failure}",
                code=failure_code,
            )
            return
        self._write_response_success(id=command_id, command=command, data={"record": record})

    async def _handle_bash_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        self._ensure_no_active_bash(command="bash")
        command = self._require_string(payload, "command")
        task = asyncio.create_task(
            self._run_bash(
                command_id=command_id,
                command=command,
                cwd=self._optional_string(payload, "cwd"),
                env=self._coerce_env(payload.get("env")),
                timeout_seconds=self._optional_number(payload, "timeoutSeconds", "timeout_seconds"),
                stdin=self._optional_string(payload, "stdin"),
            )
        )
        self._active_bash_task = task
        self._track_background_task(task)

    async def _run_bash(
        self,
        *,
        command_id: str | None,
        command: str,
        cwd: str | None,
        env: list[list[str]] | None,
        timeout_seconds: float | None,
        stdin: str | None,
    ) -> None:
        try:
            result = await self.session.execute_bash(
                command,
                cwd=cwd,
                env=env,
                timeout_seconds=timeout_seconds,
                stdin=stdin,
            )
        except Exception as exc:
            self._write_response_error(id=command_id, command="bash", error=str(exc))
        else:
            try:
                data = self._camelize(self._serialize_json_value(result))
            except Exception as exc:
                self._write_response_error(
                    id=command_id,
                    command="bash",
                    error=f"Failed to serialize bash result: {exc}",
                )
                return
            self._write_response_success(
                id=command_id,
                command="bash",
                data=data,
            )
        finally:
            if self._active_bash_task is asyncio.current_task():
                self._active_bash_task = None

    def _handle_abort_bash_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        self.session.abort_bash()
        self._write_response_success(id=command_id, command="abort_bash")

    async def _handle_compact_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        try:
            result = await self.session.compact(
                custom_instructions=self._optional_string(payload, "customInstructions", "custom_instructions")
            )
        except Exception as exc:
            self._write_response_error(id=command_id, command="compact", error=f"Failed to compact session: {exc}")
            return
        try:
            data = self._camelize(self._serialize_json_value(result))
        except Exception as exc:
            self._write_response_error(
                id=command_id,
                command="compact",
                error=f"Failed to serialize compact response: {exc}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="compact",
            data=data,
        )

    def _handle_set_auto_retry_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("set_auto_retry requires boolean enabled")
        try:
            self.session.set_auto_retry_enabled(enabled)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_auto_retry",
                error=f"Failed to set auto-retry: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_auto_retry")

    def _handle_abort_retry_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        del payload
        self.session.abort_retry()
        self._write_response_success(id=command_id, command="abort_retry")

    def _handle_set_auto_compaction_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("set_auto_compaction requires boolean enabled")
        try:
            self.session.set_auto_compaction_enabled(enabled)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_auto_compaction",
                error=f"Failed to set auto-compaction: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_auto_compaction")

    def _handle_export_html_command(self, command_id: str | None, payload: dict[str, Any]) -> None:
        output_path = self._optional_string(payload, "outputPath", "output_path")
        try:
            path = self.session.export_to_html(output_path)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="export_html",
                error=f"Failed to export HTML: {error}",
            )
            return
        if not isinstance(path, str):
            if isinstance(path, Path):
                path = str(path)
            else:
                self._write_response_error(
                    id=command_id,
                    command="export_html",
                    error="Export returned an invalid response.",
                )
                return
        self._write_response_success(
            id=command_id,
            command="export_html",
            data={"path": path},
        )

    def _bind_session(self, session: Any) -> None:
        self._unsubscribe()
        self.session = session
        self._configure_tool_rendering(session)
        self._unsubscribe = self.session.subscribe(self._handle_event)
        self._bind_extension_ui_context(session)

    def _bind_extension_ui_context(self, session: Any) -> None:
        setter = getattr(session, "set_extension_ui_context", None)
        if callable(setter):
            setter(self.extension_ui_context)

    def _handle_event(self, event: object) -> None:
        if not isinstance(event, dict):
            return
        for projected_event in project_session_event(
            event,
            event_view=self.event_view,
            tool_render_runtime=self._tool_render_runtime,
            tool_definition_resolver=self._tool_definition_resolver,
        ):
            if should_emit_projected_event(projected_event, self.event_select):
                self._write_json_line(shape_stream_event(projected_event, event_view=self.event_view))

    def _configure_tool_rendering(self, session: Any) -> None:
        if not self.render_tool_events:
            self._tool_render_runtime = None
            self._tool_definition_resolver = None
            return
        self._tool_render_runtime = ToolRenderRuntime(cwd=_session_cwd(session))
        self._tool_definition_resolver = _tool_definition_resolver(session)

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)

        def cleanup(done: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done)

        task.add_done_callback(cleanup)

    async def _drain_background_tasks(self) -> None:
        while self._background_tasks:
            await asyncio.sleep(0)
            await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

    def _ensure_no_active_bash(self, *, command: str) -> None:
        task = self._active_bash_task
        if task is not None and not task.done():
            raise RuntimeError(f"{command} requires the active bash command to finish or abort first")

    def _require_current_session(self) -> Any:
        getter = getattr(self.runtime, "get_current_session", None)
        if callable(getter):
            session = getter()
        else:
            session = getattr(self.runtime, "session", None)
        if session is None:
            raise RuntimeError("RPC mode requires an active session")
        return session

    def _serialize_session_state(self, session: Any) -> RpcSessionState:
        """Return the canonical `get_state` payload for the current session."""

        state_getter = getattr(session, "get_session_state", None)
        if callable(state_getter):
            serialized = self._serialize_json_value(state_getter())
            if not isinstance(serialized, dict):
                raise TypeError("session state must serialize to an object")
            return cast(RpcSessionState, self._camelize(serialized))

        state = session.get_state()
        session_id = self._safe_getattr(session, "session_id", None)
        if session_id is None:
            session_id_value = ""
        elif isinstance(session_id, str):
            session_id_value = session_id
        else:
            session_id_value = self._safe_string(session_id)

        session_name = self._safe_getattr(session, "session_name", None)
        if session_name is not None and not isinstance(session_name, str):
            session_name = self._safe_string(session_name)

        session_file = self._safe_getattr(session, "session_file", None)
        if isinstance(session_file, Path):
            session_file_value: str | None = str(session_file)
        elif session_file is None:
            session_file_value = None
        else:
            session_file_value = self._safe_string(session_file)
        steering = self._list_attr(state, "steering")
        follow_up = self._list_attr(state, "follow_up")
        thinking_level = self._safe_getattr(state, "thinking_level", "off")
        if not isinstance(thinking_level, str):
            thinking_level = self._safe_string(thinking_level) or "off"
        if thinking_level not in _THINKING_LEVEL_ORDER:
            thinking_level = "off"
        try:
            model = self._serialize_state_model(session, state)
        except Exception:
            model = None
        payload = {
            "sessionId": session_id_value,
            "model": model,
            "isStreaming": self._run_status(state) == "running",
            "isCompacting": bool(self._safe_getattr(state, "is_compacting", False)),
            "steeringMode": self._queue_mode(session, "steering_mode"),
            "followUpMode": self._queue_mode(session, "follow_up_mode"),
            "autoCompactionEnabled": bool(self._safe_getattr(session, "auto_compaction_enabled", False)),
            "messageCount": len(self._get_session_messages(session)),
            "pendingMessageCount": len(steering) + len(follow_up),
            "thinkingLevel": thinking_level,
        }
        if isinstance(session_name, str) and session_name:
            payload["sessionName"] = session_name
        if session_file_value:
            payload["sessionFile"] = session_file_value
        return payload

    def _run_status(self, state: Any) -> str:
        run = self._safe_getattr(state, "run", None)
        status = self._safe_getattr(run, "status", None)
        return status if isinstance(status, str) else "idle"

    def _queue_mode(self, session: Any, attr: str) -> str:
        value = self._safe_getattr(session, attr, None)
        if value in {"all", "one-at-a-time"}:
            return value
        agent_value = self._safe_getattr(self._safe_getattr(session, "agent", None), attr, None)
        if agent_value in {"all", "one-at-a-time"}:
            return agent_value
        return "one-at-a-time"

    def _list_attr(self, target: Any, attr: str) -> list[object]:
        value = self._safe_getattr(target, attr, None)
        return list(value) if isinstance(value, list) else []

    def _serialize_state_model(self, session: Any, state: Any) -> RpcModel | None:
        """Project the active session model into the RPC wire shape."""

        agent = self._safe_getattr(session, "agent", None)
        agent_state = self._safe_getattr(agent, "state", None)
        model = self._safe_getattr(agent_state, "model", None)
        if model is not None:
            try:
                payload = self._serialize_model(session, model)
                if payload is not None and not _is_unknown_model(payload):
                    return payload
            except Exception:
                pass

        selection = self._safe_getattr(state, "model_selection", None)
        resolved_model = self._resolve_model_for_rpc(session, selection)
        if resolved_model is not None:
            try:
                payload = self._serialize_model(session, resolved_model)
                if payload is not None and not _is_unknown_model(payload):
                    return payload
            except Exception:
                pass

        try:
            payload = self._serialize_model_selection_as_model(selection)
            if payload is not None and not _is_unknown_model(payload):
                return payload
            return self._serialize_default_model(session)
        except Exception:
            return None

    def _serialize_default_model(self, session: Any) -> RpcModel | None:
        """Fallback to first non-placeholder model from session's model list."""

        getter = getattr(session, "get_available_models", None)
        if not callable(getter):
            return None
        try:
            models = getter()
        except Exception:
            return None
        if not isinstance(models, list):
            return None
        for selection in models:
            payload = None
            try:
                payload = self._serialize_model_selection_as_model(selection)
            except Exception:
                payload = None
            if payload is not None and not _is_unknown_model(payload):
                return payload
            try:
                resolved = self._resolve_model_for_rpc(session, selection)
            except Exception:
                resolved = None
            if resolved is None:
                continue
            try:
                payload = self._serialize_model(session, resolved)
            except Exception:
                payload = None
            if payload is not None and not _is_unknown_model(payload):
                return payload
        return None

    def _serialize_available_models(self, session: Any, selections: list[Any]) -> list[RpcModel]:
        serialized: list[RpcModel] = []
        for selection in selections:
            try:
                resolved_model = self._resolve_model_for_rpc(session, selection)
                payload = (
                    self._serialize_model(session, resolved_model)
                    if resolved_model is not None
                    else self._serialize_model_selection_as_model(selection)
                )
            except Exception:
                continue
            if payload is not None:
                serialized.append(payload)
        return serialized

    def _resolve_model_for_rpc(self, session: Any, selection: Any) -> object | None:
        registry = self._safe_getattr(session, "model_registry", None)
        builder = self._safe_getattr(registry, "build_model", None)
        if selection is not None and callable(builder):
            try:
                return builder(selection)
            except Exception:
                return None
        return None

    def _serialize_session_stats(self, stats: Any) -> dict[str, Any]:
        return self._camelize(self._serialize_json_value(stats))

    def _serialize_session_listing_item(self, session: Any) -> dict[str, Any]:
        serialized = self._serialize_json_value(session)
        if not isinstance(serialized, dict):
            raise TypeError("session listing items must serialize to objects")
        return self._camelize(serialized)

    def _serialize_command_descriptor(self, command: object) -> dict[str, Any]:
        name = self._safe_getattr(command, "name", None)
        if not isinstance(name, str) or not name:
            raise ValueError("command descriptor requires name")
        description = self._safe_getattr(command, "description", None)
        source = self._safe_getattr(command, "source", None)
        payload = {
            "name": name,
            "description": description if isinstance(description, str) else None,
            "source": source if isinstance(source, str) else "",
            "sourceInfo": self._serialize_command_source_info(self._safe_getattr(command, "source_info", None)),
        }
        invocation_name = self._safe_getattr(command, "invocation_name", None)
        if isinstance(invocation_name, str) and invocation_name:
            payload["invocationName"] = invocation_name
        conflict_group = self._safe_getattr(command, "conflict_group", None)
        if isinstance(conflict_group, str) and conflict_group:
            payload["conflictGroup"] = conflict_group
        argument_hint = self._safe_getattr(command, "argument_hint", None)
        if isinstance(argument_hint, str) and argument_hint:
            payload["argumentHint"] = argument_hint
        return payload

    def _serialize_command_source_info(self, source_info: object) -> dict[str, Any]:
        path = self._safe_getattr(source_info, "path", "")
        base_dir = self._safe_getattr(source_info, "base_dir", None)
        return {
            "path": self._safe_string(path),
            "source": self._safe_getattr(source_info, "source", "filesystem"),
            "scope": self._safe_getattr(source_info, "scope", "project"),
            "origin": self._safe_getattr(source_info, "origin", "top-level"),
            "baseDir": self._safe_string(base_dir) if base_dir is not None else None,
        }

    def _get_session_messages(self, session: Any) -> list[object]:
        context_getter = self._safe_getattr(session, "get_session_context", None)
        if callable(context_getter):
            try:
                context = context_getter()
            except Exception:
                context = None
            else:
                messages = self._safe_getattr(context, "messages", None)
                if isinstance(messages, list):
                    return list(messages)
        messages = self._safe_getattr(session, "messages", None)
        if isinstance(messages, list):
            return list(messages)
        return []

    def _serialize_model_selection(self, selection: ModelSelection | None) -> dict[str, str] | None:
        if selection is None:
            return None
        payload = {
            "provider": selection.provider,
            "modelId": selection.model_id,
        }
        if selection.endpoint_id:
            payload["endpointId"] = selection.endpoint_id
        return payload

    def _serialize_model_selection_as_model(self, selection: ModelSelection | None) -> RpcModel | None:
        if selection is None:
            return None
        provider = self._safe_getattr(selection, "provider", None)
        model_id = self._safe_getattr(selection, "model_id", None)
        if not isinstance(provider, str) or not isinstance(model_id, str):
            provider = self._safe_string(provider) if provider is not None else None
            model_id = self._safe_string(model_id) if model_id is not None else None
            if not provider or not model_id:
                return None
        payload: RpcModel = {
            "provider": provider,
            "id": model_id,
        }
        return payload

    def _serialize_model(self, session: Any, model: object) -> RpcModel | None:
        provider = self._safe_getattr(model, "provider_id", None) or self._safe_getattr(model, "provider", None)
        model_id = self._safe_getattr(model, "id", None)
        if not provider or not model_id:
            return None

        data: RpcModel = {
            "provider": str(provider),
            "id": str(model_id),
        }
        name = self._safe_getattr(model, "name", None)
        if isinstance(name, str) and name:
            data["name"] = name
        else:
            data["name"] = str(model_id)

        endpoint = self._resolve_model_endpoint(session, model)
        if endpoint is not None:
            api = self._safe_getattr(endpoint, "api", None)
            if isinstance(api, str) and api:
                data["api"] = api
            base_url = self._safe_getattr(endpoint, "base_url", None)
            if isinstance(base_url, str) and base_url:
                data["baseUrl"] = base_url

        modalities = self._safe_getattr(model, "input", None)
        if isinstance(modalities, tuple | list):
            data["input"] = [str(modality) for modality in modalities]

        context_window = self._safe_getattr(model, "context_window", None)
        if isinstance(context_window, int):
            data["contextWindow"] = context_window

        max_tokens = self._safe_getattr(model, "max_tokens", None)
        if isinstance(max_tokens, int):
            data["maxTokens"] = max_tokens

        reasoning = self._safe_getattr(model, "reasoning", None)
        if isinstance(reasoning, bool):
            data["reasoning"] = reasoning

        pricing = self._safe_getattr(model, "pricing", None)
        cost = self._serialize_model_cost(pricing)
        if cost is not None:
            data["cost"] = cost

        compat = self._safe_getattr(model, "compat", None)
        serialized_compat = self._serialize_model_compat(compat)
        if serialized_compat is not None:
            data["compat"] = serialized_compat

        return data

    def _resolve_model_endpoint(self, session: Any, model: object) -> object | None:
        provider = self._safe_getattr(model, "provider_id", None) or self._safe_getattr(model, "provider", None)
        endpoint_id = self._safe_getattr(model, "endpoint_id", None)
        if not provider or not endpoint_id:
            return None

        registry = self._safe_getattr(session, "model_registry", None)
        if registry is None:
            return None

        ai_registry = self._safe_getattr(registry, "ai_registry", None)
        getter = self._safe_getattr(ai_registry, "get_endpoint", None)
        if callable(getter):
            try:
                endpoint = getter(provider, endpoint_id)
            except Exception:
                endpoint = None
            if endpoint is not None:
                return endpoint

        getter = self._safe_getattr(registry, "get_endpoint", None)
        if callable(getter):
            try:
                return getter(provider, endpoint_id)
            except Exception:
                return None

        return None

    def _serialize_model_cost(self, pricing: object) -> RpcModelCost | None:
        if pricing is None:
            return None
        input_cost = self._safe_getattr(pricing, "input", None)
        output_cost = self._safe_getattr(pricing, "output", None)
        cache_read = self._safe_getattr(pricing, "cache_read", None)
        cache_write = self._safe_getattr(pricing, "cache_write", None)
        values = (input_cost, output_cost, cache_read, cache_write)
        if any(
            value is None
            or isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
            or value < 0
            for value in values
        ):
            return None
        return {
            "input": cast(float | int, input_cost),
            "output": cast(float | int, output_cost),
            "cacheRead": cast(float | int, cache_read),
            "cacheWrite": cast(float | int, cache_write),
        }

    def _serialize_model_compat(self, compat: object) -> dict[str, Any] | None:
        if compat is None:
            return None
        to_raw = self._safe_getattr(compat, "to_raw", None)
        if callable(to_raw):
            try:
                raw = to_raw()
            except Exception:
                return None
            if isinstance(raw, dict) and raw:
                return raw
            return None
        if isinstance(compat, dict) and compat:
            return compat
        return None

    def _safe_getattr(self, target: Any, name: str, default: object) -> object:
        try:
            return getattr(target, name, default)
        except Exception:
            return default

    def _serialize_json_value(self, value: object, *, _seen: set[int] | None = None) -> object:
        if _seen is None:
            _seen = set()

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Path):
            return str(value)
        if is_dataclass(value):
            return {key: self._serialize_json_value(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            obj_id = id(value)
            if obj_id in _seen:
                return "<circular>"
            _seen.add(obj_id)
            serialized = {}
            for key, item in value.items():
                try:
                    key_text = str(key)
                except Exception:
                    key_text = ""
                serialized[key_text] = self._serialize_json_value(item, _seen=_seen)
            _seen.remove(obj_id)
            return serialized
        if isinstance(value, list | tuple | set | frozenset):
            obj_id = id(value)
            if obj_id in _seen:
                return "<circular>"
            _seen.add(obj_id)
            serialized = [self._serialize_json_value(item, _seen=_seen) for item in value]
            _seen.remove(obj_id)
            return serialized
        if hasattr(value, "__dict__"):
            obj_id = id(value)
            if obj_id in _seen:
                return "<circular>"
            _seen.add(obj_id)
            serialized = {
                key: self._serialize_json_value(item, _seen=_seen)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
            _seen.remove(obj_id)
            return serialized
        return repr(value)

    def _camelize(self, value: object) -> object:
        if isinstance(value, dict):
            return {_snake_to_camel(str(key)): self._camelize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._camelize(item) for item in value]
        return value

    def _extract_last_assistant_text(self) -> str | None:
        getter = getattr(self.session, "getLastAssistantText", None)
        if not callable(getter):
            getter = getattr(self.session, "get_last_assistant_text", None)
        if callable(getter):
            return getter()
        return None

    def _extract_session_entry_text(self, entry_id: str) -> str | None:
        getter = getattr(self.session, "get_entry_text", None)
        if callable(getter):
            return getter(entry_id)
        return None

    def _safe_string(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            try:
                return repr(value)
            except Exception:
                return ""

    def _coerce_images(self, images: object) -> list[object] | None:
        if images is None:
            return None
        if not isinstance(images, list):
            raise ValueError("images must be a list")
        return images

    def _coerce_env(self, env: object) -> list[list[str]] | None:
        if env is None:
            return None
        if isinstance(env, str) or not isinstance(env, list):
            raise ValueError("env must contain 2-item string pairs")
        normalized: list[list[str]] = []
        for pair in env:
            if isinstance(pair, str) or not isinstance(pair, list | tuple) or len(pair) != 2:
                raise ValueError("env must contain 2-item string pairs")
            if not all(isinstance(part, str) for part in pair):
                raise ValueError("env must contain 2-item string pairs")
            normalized.append([pair[0], pair[1]])
        return normalized

    def _require_mode(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if value in {"all", "one-at-a-time"}:
            return value
        raise ValueError(f"{key} must be 'all' or 'one-at-a-time'")

    def _require_string(self, payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        if not keys:
            raise ValueError("missing required string field")
        raise ValueError(f"missing required string field: {keys[0]}")

    def _optional_string(self, payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                return value
            raise ValueError(f"{key} must be a string")
        return None

    def _optional_number(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
            raise ValueError(f"{key} must be a number")
        return None

    def _optional_int(self, payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            raise ValueError(f"{key} must be an integer")
        return None

    def _optional_bool(self, payload: dict[str, Any], *keys: str) -> bool | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            raise ValueError(f"{key} must be a boolean")
        return None

    def _optional_path(self, value: object) -> str | Path | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, Path):
            return value
        raise ValueError("cwd must be a string")

    def _write_response_success(self, *, command: str, id: str | None = None, data: object = _MISSING) -> None:
        payload: dict[str, object] = {
            "type": "response",
            "command": command,
            "success": True,
        }
        if id is not None:
            payload["id"] = id
        if data is not _MISSING:
            payload["data"] = data
        self._write_json_line(payload)

    def _write_response_error(
        self,
        *,
        command: str,
        error: str,
        id: str | None = None,
        code: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "type": "response",
            "command": command,
            "success": False,
            "error": error,
        }
        if id is not None:
            payload["id"] = id
        if code is not None:
            payload["errorCode"] = code
            payload["errorInfo"] = {
                "code": code,
                "message": error,
                "command": command,
            }
        self._write_json_line(payload)

    def _write_json_line(self, payload: object) -> None:
        def _safe_extract_fallback_fields(item: object) -> tuple[object | None, object | None]:
            if not isinstance(item, dict):
                return None, None
            fallback_command = item.get("command")
            fallback_id = item.get("id")
            return (
                fallback_id if fallback_id is not None else None,
                fallback_command if fallback_command is not None else None,
            )

        try:
            serialized = self._serialize_json_value(payload)
            line = json.dumps(serialized, ensure_ascii=False)
        except Exception:
            fallback_id, fallback_command = _safe_extract_fallback_fields(payload)
            fallback_payload: dict[str, object] = {
                "type": "response",
                "command": "response",
                "success": False,
                "error": "Failed to serialize RPC output.",
            }
            if fallback_id is not None:
                fallback_payload["id"] = fallback_id if isinstance(fallback_id, str) else self._safe_string(fallback_id)
            if fallback_command is not None:
                fallback_payload["command"] = (
                    fallback_command if isinstance(fallback_command, str) else self._safe_string(fallback_command)
                )
            line = json.dumps(
                fallback_payload,
                ensure_ascii=False,
            )
        self.stdout.write(line + "\n")
        flush = getattr(self.stdout, "flush", None)
        if callable(flush):
            flush()


async def run_rpc_mode(
    *,
    runtime: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    event_view: JsonEventView = "full",
    event_select: str | Sequence[str] | None = None,
    render_tool_events: bool = False,
) -> int:
    mode = RpcMode(
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
    )
    return await mode.run()


def _session_cwd(session: Any) -> str:
    session_manager = getattr(session, "session_manager", None)
    get_cwd = getattr(session_manager, "get_cwd", None)
    if callable(get_cwd):
        try:
            return str(get_cwd())
        except Exception:
            return ""
    return ""


def _tool_definition_resolver(session: Any) -> ToolDefinitionResolver | None:
    getter = getattr(session, "getToolDefinition", None)
    if not callable(getter):
        getter = getattr(session, "get_tool_definition", None)
    if not callable(getter):
        return None

    def resolve(name: str):
        try:
            return getter(name)
        except Exception:
            return None

    return resolve


def _stream_supports_fileno(stream: TextIO) -> bool:
    fileno = getattr(stream, "fileno", None)
    if not callable(fileno):
        return False
    try:
        fileno()
    except (io.UnsupportedOperation, OSError, ValueError):
        return False
    return True


def _package_lifecycle_failure(record: dict[str, Any]) -> str | None:
    if record.get("lifecycle") != "failed":
        return None
    message = record.get("errorMessage", record.get("error_message"))
    return str(message) if isinstance(message, str) and message else "Package lifecycle failed."


def _snake_to_camel(value: str) -> str:
    if "_" not in value:
        return value
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _is_unknown_model(payload: RpcModel | dict[str, object] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    provider = payload.get("provider")
    model_id = payload.get("id")
    return provider == "unknown" and model_id == "unknown"


def _timeout_payload(timeout: float | None) -> dict[str, object]:
    return {"timeout": timeout} if timeout is not None else {}

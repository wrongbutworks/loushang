"""Product-neutral JSONL RPC runtime."""

from __future__ import annotations

import asyncio
import inspect
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from loushang.ai.model import ModelSelection
from loushang.harness.commands import complete_slash_commands
from loushang.harness.events import RuntimeEvent
from loushang.harness.host.jsonl_command_host import (
    JsonlCommand,
    JsonlCommandHost,
    JsonlCommandHostError,
)
from loushang.harness.host.jsonl_command_router import (
    JsonlCommandRoute,
    JsonlCommandRouter,
)
from loushang.harness.host.mode import ModeAdapter, ModeState
from loushang.harness.host.product_host import (
    ProductHostRuntime,
    ProductHostTaskTracker,
)
from loushang.harness.host.rpc.arguments import (
    optional_bool,
    optional_env_pairs,
    optional_int,
    optional_number,
    optional_string,
    require_mode,
    require_string,
)
from loushang.harness.host.rpc.commands import (
    RpcDiagnosticsCommands,
    RpcPackageCommands,
)
from loushang.harness.host.rpc.output import RpcOutput
from loushang.harness.host.rpc.projections import (
    STANDARD_AGENT_RPC_EVENT_PROJECTION,
    STANDARD_RPC_DIAGNOSTICS_PROJECTION,
    RpcDiagnosticsProjection,
    RpcEventProjection,
)
from loushang.harness.host.rpc.remote_ui import RpcExtensionUIContext
from loushang.harness.host.rpc.routing import legacy_rpc_routes
from loushang.harness.host.rpc.wire import (
    camelize,
    project_available_models,
    project_command_descriptor,
    project_json_value,
    project_session_listing_item,
    project_session_state,
    project_session_stats,
    project_state_model,
    session_messages,
)
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime
from loushang.harness.session import (
    SessionLifecycleOperationPorts,
    SessionOperationResolver,
    SessionOperationRuntime,
    SessionPromptRequest,
    SessionRpcOperationBinding,
    current_session_operation_resolver,
)
from loushang.harness.transcript import (
    SessionQuery,
    create_agent_transcript_message_codec,
)

_MISSING = object()
_MESSAGE_CODEC = create_agent_transcript_message_codec()
serialize_agent_message = _MESSAGE_CODEC.serialize


class RpcHost(ModeAdapter):
    """Product-neutral JSONL RPC host for an active Agent session."""

    def __init__(
        self,
        *,
        runtime: Any,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO | None = None,
        event_view: str = "full",
        event_select: str | Sequence[str] | None = None,
        render_tool_events: bool = False,
        event_projection: RpcEventProjection = STANDARD_AGENT_RPC_EVENT_PROJECTION,
        diagnostics_projection: RpcDiagnosticsProjection = (
            STANDARD_RPC_DIAGNOSTICS_PROJECTION
        ),
    ) -> None:
        if event_view not in event_projection.supported_views:
            raise ValueError(f"unsupported json event view: {event_view}")
        self.runtime = runtime
        self.stdin = stdin
        self.stdout = stdout
        self._rpc_output = RpcOutput(stdout)
        self.stderr = sys.stderr if stderr is None else stderr
        self.event_view = event_view
        self._event_projection = event_projection
        self.event_select = tuple(event_projection.normalize_select(event_select))
        self.render_tool_events = render_tool_events
        self._host_runtime = ProductHostRuntime(stdin=stdin)
        self.session = self._require_current_session()
        self._session_operation_resolver = self._build_session_operation_resolver()
        self._rpc_operations = SessionRpcOperationBinding(
            get_operations=self._require_session_operations,
            bind_session=self._bind_session,
        )
        self._tool_render_runtime: ToolRenderRuntime | None = None
        self._tool_definition_resolver: ToolDefinitionResolver | None = None
        self._configure_tool_rendering(self.session)
        self._unsubscribe = self._subscribe_to_events(self.session)
        self._task_tracker = ProductHostTaskTracker()
        self._active_prompt_task: asyncio.Task[None] | None = None
        self._active_bash_task: asyncio.Task[None] | None = None
        self.extension_ui_context = RpcExtensionUIContext(self._write_json_line)
        self._bind_extension_ui_context(self.session)
        self._diagnostics_commands = RpcDiagnosticsCommands(
            runtime=runtime,
            get_session=lambda: self.session,
            output=self._rpc_output,
            projection=diagnostics_projection,
        )
        self._package_commands = RpcPackageCommands(
            runtime=runtime,
            get_session=lambda: self.session,
            output=self._rpc_output,
        )
        self._command_router = JsonlCommandRouter(
            routes=self._command_routes(),
            on_unsupported=self._handle_unsupported_jsonl_command,
        )
        self._command_host = JsonlCommandHost(
            port=self._command_router,
            on_error=self._handle_jsonl_command_error,
            stdin=stdin,
            command_name="rpc_command",
        )

    async def start(self, user_input: str | None = None) -> int:
        del user_input
        return await self.run()

    async def stop(self) -> int:
        self._host_runtime.stop()
        self._command_host.stop()
        self._unsubscribe()
        return 0

    async def submit_input(self, input_payload: object) -> int:
        if not isinstance(input_payload, str):
            raise TypeError("Rpc mode submit_input expects a string")
        try:
            await self._command_host.handle_line(input_payload)
        except Exception:
            return 1
        return 0

    async def wait_for_idle(self) -> int:
        await self._require_session_operations().wait_for_idle()
        return 0

    def rebind_session(self, session: object | None = None) -> int:
        if session is None:
            session = self._require_current_session()
        self._bind_session(session)
        return 0

    async def dispose(self) -> int:
        self._host_runtime.stop()
        self._command_host.stop()
        self._unsubscribe()
        disposer = getattr(self.runtime, "dispose", None)
        if callable(disposer):
            await disposer()
        return 0

    def render_event(self, event: object) -> None:
        self._handle_event(event)

    async def run(self) -> int:
        try:
            return await self._host_runtime.run(
                self._handle_line,
                handle_failure=self._handle_host_failure,
            )
        finally:
            await self._task_tracker.drain()
            self._command_host.stop()
            self._unsubscribe()

    def get_mode_state(self) -> ModeState:
        try:
            return project_session_state(self.session)
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

    async def _handle_host_failure(self, error: Exception) -> None:
        self.stderr.write(f"Error: {error}\n")

    async def _drain_background_tasks(self) -> None:
        """Compatibility hook over the Channel-owned task tracker."""

        await self._task_tracker.drain()

    async def _handle_line(self, line: str) -> None:
        """Test-facing adapter for the Channel-owned JSONL command host."""

        await self._command_host.handle_line(line)

    def _command_routes(self) -> tuple[JsonlCommandRoute, ...]:
        """Bind the declared Product RPC surface to the Channel router.

        This explicit table replaces the former ``getattr`` convention.  The
        route registry is transport-neutral; response projection is handled by
        the shared host contract.
        """

        return (
            JsonlCommandRoute(
                command_type="extension_ui_response",
                handler=self._handle_extension_ui_response,
            ),
            *legacy_rpc_routes(
                (
                    ("prompt", self._handle_prompt_command),
                    ("steer", self._handle_steer_command),
                    ("follow_up", self._handle_follow_up_command),
                    ("abort", self._handle_abort_command),
                    ("get_state", self._handle_get_state_command),
                    (
                        "get_extension_ui_state",
                        self._handle_get_extension_ui_state_command,
                    ),
                    ("get_messages", self._handle_get_messages_command),
                    ("list_sessions", self._handle_list_sessions_command),
                    ("new_session", self._handle_new_session_command),
                    ("switch_session", self._handle_switch_session_command),
                    ("fork", self._handle_fork_command),
                    ("clone", self._handle_clone_command),
                    ("set_model", self._handle_set_model_command),
                    (
                        "get_available_models",
                        self._handle_get_available_models_command,
                    ),
                    ("cycle_model", self._handle_cycle_model_command),
                    ("set_active_tools", self._handle_set_active_tools_command),
                    ("set_thinking_level", self._handle_set_thinking_level_command),
                    (
                        "cycle_thinking_level",
                        self._handle_cycle_thinking_level_command,
                    ),
                    ("set_steering_mode", self._handle_set_steering_mode_command),
                    ("set_follow_up_mode", self._handle_set_follow_up_mode_command),
                    ("get_session_stats", self._handle_get_session_stats_command),
                    ("set_session_name", self._handle_set_session_name_command),
                    (
                        "get_last_assistant_text",
                        self._handle_get_last_assistant_text_command,
                    ),
                    ("get_fork_messages", self._handle_get_fork_messages_command),
                    ("get_commands", self._handle_get_commands_command),
                    (
                        "get_command_completions",
                        self._handle_get_command_completions_command,
                    ),
                    *self._diagnostics_commands.bindings(),
                    *self._package_commands.bindings(),
                    ("bash", self._handle_bash_command),
                    ("abort_bash", self._handle_abort_bash_command),
                    ("compact", self._handle_compact_command),
                    ("set_auto_retry", self._handle_set_auto_retry_command),
                    ("abort_retry", self._handle_abort_retry_command),
                    (
                        "set_auto_compaction",
                        self._handle_set_auto_compaction_command,
                    ),
                    ("export_html", self._handle_export_html_command),
                )
            ),
        )

    def _handle_extension_ui_response(self, command: JsonlCommand) -> None:
        self.extension_ui_context.resolve_response(dict(command.payload))

    def _handle_unsupported_jsonl_command(self, command: JsonlCommand) -> None:
        self._write_response_error(
            id=command.command_id,
            command=command.command_type,
            error=f"unsupported command: {command.command_type}",
            code="unsupported_command",
        )

    def _handle_jsonl_command_error(self, error: JsonlCommandHostError) -> None:
        if error.reason == "invalid_json":
            self._write_response_error(
                command="parse", error=f"Failed to parse command: {error.message}"
            )
            return
        if error.reason == "not_object":
            self._write_response_error(
                command="invalid", error="RPC commands must be JSON objects"
            )
            return
        if error.reason == "non_json_value":
            detail = error.message.removeprefix(
                "JSONL command contains a value outside strict JSON: "
            )
            self._write_response_error(
                id=error.command_id,
                command="invalid",
                error=f"RPC command contains a value outside strict JSON: {detail}",
            )
            return
        if error.reason == "invalid_id":
            self._write_response_error(
                command="invalid", error="command id must be a string"
            )
            return
        if error.reason == "missing_type":
            self._write_response_error(
                id=error.command_id,
                command="invalid",
                error="RPC command missing string type",
            )
            return
        self._write_response_error(
            id=error.command_id,
            command=error.command_type or "invalid",
            error=error.message,
        )

    async def _handle_prompt_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        request = self._rpc_operations.prompt_request(payload)
        task = asyncio.create_task(
            self._run_prompt(
                operations=self._require_session_operations(),
                command_id=command_id,
                request=request,
            )
        )
        self._active_prompt_task = task
        self._task_tracker.track(task)

    async def _run_prompt(
        self,
        *,
        operations: SessionOperationRuntime,
        command_id: str | None,
        request: SessionPromptRequest,
    ) -> None:
        preflight_succeeded = False

        def on_preflight(did_succeed: bool) -> None:
            nonlocal preflight_succeeded
            if did_succeed and not preflight_succeeded:
                preflight_succeeded = True
                self._write_response_success(id=command_id, command="prompt")

        try:
            await operations.prompt(
                request,
                on_preflight=on_preflight,
            )
        except Exception as exc:
            if not preflight_succeeded:
                self._write_response_error(
                    id=command_id, command="prompt", error=str(exc)
                )
        else:
            if not preflight_succeeded:
                self._write_response_success(id=command_id, command="prompt")
        finally:
            if self._active_prompt_task is asyncio.current_task():
                self._active_prompt_task = None

    def _handle_steer_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._rpc_operations.steer(payload)
        self._write_response_success(id=command_id, command="steer")

    def _handle_follow_up_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._rpc_operations.follow_up(payload)
        self._write_response_success(id=command_id, command="follow_up")

    def _handle_abort_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        self._rpc_operations.abort()
        self._write_response_success(id=command_id, command="abort")

    def _handle_get_state_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        try:
            state = project_session_state(self.session)
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

    def _handle_get_extension_ui_state_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        self._write_response_success(
            id=command_id,
            command="get_extension_ui_state",
            data=self.extension_ui_context.get_snapshot(),
        )

    def _handle_get_messages_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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

    def _handle_list_sessions_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        try:
            query = self._session_query_from_payload(payload)
        except ValueError as error:
            self._write_response_error(
                id=command_id, command="list_sessions", error=str(error)
            )
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
            refresher = getattr(
                self.runtime,
                "refresh_all_session_indexes"
                if all_sessions
                else "refresh_session_index",
                None,
            )
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
            getattr(
                self.runtime,
                "find_all_indexed_session_summaries"
                if use_index
                else "find_all_session_summaries",
                None,
            )
            if all_sessions
            else None
        )
        if not callable(finder):
            finder = getattr(
                self.runtime,
                "find_indexed_session_summaries"
                if use_index
                else "find_session_summaries",
                None,
            )
        if callable(finder):

            def lister():
                return finder(query)
        else:
            if all_sessions:
                lister = getattr(
                    self.runtime,
                    "list_all_indexed_session_summaries"
                    if use_index
                    else "list_all_session_summaries",
                    None,
                )
            else:
                lister = getattr(
                    self.runtime,
                    "list_indexed_session_summaries"
                    if use_index
                    else "list_session_summaries",
                    None,
                )
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
                sessions.append(project_session_listing_item(session))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command="list_sessions",
            data={"sessions": sessions},
        )

    def _session_query_from_payload(self, payload: dict[str, Any]) -> SessionQuery:
        limit = optional_int(payload, "limit")
        if limit is not None and limit < 0:
            raise ValueError("Session limit must be non-negative.")
        return SessionQuery(
            cwd=optional_string(payload, "cwd"),
            name=optional_string(payload, "name"),
            parent_session=optional_string(
                payload, "parentSession", "parent_session"
            ),
            text=optional_string(payload, "text", "query"),
            has_diagnostics=optional_bool(
                payload, "hasDiagnostics", "has_diagnostics"
            ),
            limit=limit,
        )

    async def _handle_new_session_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        previous = self.session
        try:
            operation = await self._rpc_operations.new_session(payload)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="new_session",
                error=f"Failed to create new session: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="new_session",
            data={
                "cancelled": operation.current is previous,
            },
        )

    async def _handle_switch_session_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        previous = self.session
        try:
            operation = await self._rpc_operations.switch_session(payload)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="switch_session",
                error=f"Failed to switch session: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="switch_session",
            data={
                "cancelled": operation.current is previous,
            },
        )

    async def _handle_fork_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        previous = self.session
        try:
            operation = await self._rpc_operations.fork(payload)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="fork",
                error=f"Failed to fork session: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="fork",
            data={
                "cancelled": operation.current is previous,
                "text": operation.payload,
            },
        )

    async def _handle_clone_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        previous = self.session
        try:
            operation = await self._rpc_operations.clone()
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="clone",
                error=f"Failed to clone session: {error}",
            )
            return
        self._write_response_success(
            id=command_id,
            command="clone",
            data={"cancelled": operation.current is previous},
        )

    async def _handle_set_model_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        provider = require_string(payload, "provider")
        model_id = require_string(payload, "modelId", "model_id")
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
            data=project_state_model(self.session, self.session.get_state()),
        )

    def _handle_get_available_models_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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
            serialized = project_available_models(self.session, models)
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

    async def _handle_cycle_model_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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
            model = project_state_model(self.session, self.session.get_state())
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

    async def _handle_set_active_tools_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        tool_names = payload.get("toolNames", payload.get("tool_names"))
        if not isinstance(tool_names, list) or not all(
            isinstance(name, str) and name for name in tool_names
        ):
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
            state = project_session_state(self.session)
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

    async def _handle_set_thinking_level_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        level = require_string(payload, "level")
        try:
            result = self.session.set_thinking_level(level)
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_thinking_level",
                error=f"Failed to set thinking level: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_thinking_level")

    async def _handle_cycle_thinking_level_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        try:
            result = self.session.cycle_thinking_level()
            next_level = await result if inspect.isawaitable(result) else result
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

    def _handle_set_steering_mode_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        mode = require_mode(payload, "mode")
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

    def _handle_set_follow_up_mode_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        mode = require_mode(payload, "mode")
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

    def _handle_get_session_stats_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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
            serialized = project_session_stats(stats)
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

    async def _handle_set_session_name_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        name = require_string(payload, "name").strip()
        if not name:
            self._write_response_error(
                id=command_id,
                command="set_session_name",
                error="Session name cannot be empty",
            )
            return
        try:
            await self._require_session_operations().set_session_name(name)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_session_name",
                error=f"Failed to set session name: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_session_name")

    def _handle_get_last_assistant_text_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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

    def _handle_get_fork_messages_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
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
        messages = camelize(project_json_value(raw_messages))
        self._write_response_success(
            id=command_id,
            command="get_fork_messages",
            data={"messages": messages},
        )

    def _handle_get_commands_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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
                commands.append(project_command_descriptor(command))
            except Exception:
                continue
        self._write_response_success(
            id=command_id,
            command="get_commands",
            data={"commands": commands},
        )

    async def _handle_get_command_completions_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
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
                data={
                    "completions": completions if isinstance(completions, list) else []
                },
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

    async def _handle_bash_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._ensure_no_active_bash(command="bash")
        command = require_string(payload, "command")
        task = asyncio.create_task(
            self._run_bash(
                command_id=command_id,
                command=command,
                cwd=optional_string(payload, "cwd"),
                env=optional_env_pairs(payload.get("env")),
                timeout_seconds=optional_number(
                    payload, "timeoutSeconds", "timeout_seconds"
                ),
                stdin=optional_string(payload, "stdin"),
            )
        )
        self._active_bash_task = task
        self._task_tracker.track(task)

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
                data = camelize(project_json_value(result))
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

    def _handle_abort_bash_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        self.session.abort_bash()
        self._write_response_success(id=command_id, command="abort_bash")

    async def _handle_compact_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        try:
            result = await self._rpc_operations.compact(payload)
        except Exception as exc:
            self._write_response_error(
                id=command_id,
                command="compact",
                error=f"Failed to compact session: {exc}",
            )
            return
        try:
            data = camelize(project_json_value(result))
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

    def _handle_set_auto_retry_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        try:
            self._rpc_operations.set_auto_retry(payload)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_auto_retry",
                error=f"Failed to set auto-retry: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_auto_retry")

    def _handle_abort_retry_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        self._rpc_operations.abort_retry()
        self._write_response_success(id=command_id, command="abort_retry")

    def _handle_set_auto_compaction_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        try:
            self._rpc_operations.set_auto_compaction(payload)
        except Exception as error:
            self._write_response_error(
                id=command_id,
                command="set_auto_compaction",
                error=f"Failed to set auto-compaction: {error}",
            )
            return
        self._write_response_success(id=command_id, command="set_auto_compaction")

    def _handle_export_html_command(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        output_path = optional_string(payload, "outputPath", "output_path")
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
        self._unsubscribe = self._subscribe_to_events(session)
        self._bind_extension_ui_context(session)

    def _bind_extension_ui_context(self, session: Any) -> None:
        setter = getattr(session, "set_extension_ui_context", None)
        if callable(setter):
            setter(self.extension_ui_context)

    def _handle_event(self, event: object) -> None:
        if not isinstance(event, dict):
            return
        for projected_event in self._event_projection.project_session_event(
            event,
            event_view=self.event_view,
            tool_render_runtime=self._tool_render_runtime,
            tool_definition_resolver=self._tool_definition_resolver,
        ):
            if self._event_projection.should_emit_projected_event(
                projected_event, self.event_select
            ):
                self._write_json_line(
                    self._event_projection.shape_stream_event(
                        projected_event, event_view=self.event_view
                    )
                )

    def _subscribe_to_events(self, session: Any):
        """Prefer the common runtime event stream when one is available.

        Products may still expose a lower-level session event stream when no
        runtime projection is available; the injected projection owns its
        payload vocabulary.
        """

        subscribe_runtime_events = getattr(session, "subscribe_runtime_events", None)
        if callable(subscribe_runtime_events):
            return subscribe_runtime_events(self._handle_runtime_event)
        return session.subscribe(self._handle_event)

    def _handle_runtime_event(self, event: RuntimeEvent[object]) -> None:
        for projected_event in self._event_projection.project_runtime_event_to_json_views(
            event,
            event_view=self.event_view,
            tool_render_runtime=self._tool_render_runtime,
            tool_definition_resolver=self._tool_definition_resolver,
        ):
            if self._event_projection.should_emit_runtime_event_view(
                projected_event, self.event_select
            ):
                self._write_json_line(
                    self._event_projection.shape_runtime_event_view(projected_event)
                )

    def _configure_tool_rendering(self, session: Any) -> None:
        if not self.render_tool_events:
            self._tool_render_runtime = None
            self._tool_definition_resolver = None
            return
        self._tool_render_runtime = ToolRenderRuntime(cwd=_session_cwd(session))
        self._tool_definition_resolver = _tool_definition_resolver(session)

    def _ensure_no_active_bash(self, *, command: str) -> None:
        task = self._active_bash_task
        if task is not None and not task.done():
            raise RuntimeError(
                f"{command} requires the active bash command to finish or abort first"
            )

    def _require_current_session(self) -> Any:
        getter = getattr(self.runtime, "get_current_session", None)
        if callable(getter):
            session = getter()
        else:
            session = getattr(self.runtime, "session", None)
        if session is None:
            raise RuntimeError("RPC mode requires an active session")
        return session

    def _build_session_operation_resolver(self) -> SessionOperationResolver:
        runtime = self.runtime
        clone_operation = getattr(runtime, "clone_session_operation", None)
        if not callable(clone_operation):

            async def clone_operation():
                return await runtime.fork_session_operation(None, position="at")

        return current_session_operation_resolver(
            runtime,
            lifecycle=SessionLifecycleOperationPorts(
                new_session=lambda cwd, parent: runtime.new_session_operation(
                    cwd=cwd, parent_session=parent
                ),
                restore_session=lambda session_ref: runtime.restore_session_operation(
                    session_ref
                ),
                fork_session=lambda entry_id, position: runtime.fork_session_operation(
                    entry_id, position=position
                ),
                clone_session=clone_operation,
            ),
        )

    def _require_session_operations(self) -> SessionOperationRuntime:
        return self._session_operation_resolver()

    def _get_session_messages(self, session: Any) -> list[object]:
        """Narrow test seam for validating malformed upstream message logs."""

        return session_messages(session)

    def _extract_last_assistant_text(self) -> str | None:
        getter = getattr(self.session, "get_last_assistant_text", None)
        if callable(getter):
            return getter()
        return None

    def _extract_session_entry_text(self, entry_id: str) -> str | None:
        getter = getattr(self.session, "get_entry_text", None)
        if callable(getter):
            return getter(entry_id)
        return None

    def _write_response_success(
        self, *, command: str, id: str | None = None, data: object = _MISSING
    ) -> None:
        if data is _MISSING:
            self._rpc_output.success(command=command, request_id=id)
        else:
            self._rpc_output.success(command=command, request_id=id, data=data)

    def _write_response_error(
        self,
        *,
        command: str,
        error: str,
        id: str | None = None,
        code: str | None = None,
    ) -> None:
        self._rpc_output.error(
            command=command,
            error=error,
            request_id=id,
            code=code,
        )

    def _write_json_line(self, payload: object) -> None:
        self._rpc_output.write(payload)


async def run_rpc_host(
    *,
    runtime: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    event_view: str = "full",
    event_select: str | Sequence[str] | None = None,
    render_tool_events: bool = False,
    event_projection: RpcEventProjection = STANDARD_AGENT_RPC_EVENT_PROJECTION,
    diagnostics_projection: RpcDiagnosticsProjection = (
        STANDARD_RPC_DIAGNOSTICS_PROJECTION
    ),
) -> int:
    mode = RpcHost(
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
        event_projection=event_projection,
        diagnostics_projection=diagnostics_projection,
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
    getter = getattr(session, "get_tool_definition", None)
    if not callable(getter):
        return None

    def resolve(name: str):
        try:
            return getter(name)
        except Exception:
            return None

    return resolve


__all__ = ["RpcHost", "run_rpc_host"]

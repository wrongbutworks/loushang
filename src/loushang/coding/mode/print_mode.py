from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Literal, TextIO

from loushang.channel import dispose_product_host
from loushang.coding.event import (
    SUPPORTED_JSON_EVENT_VIEWS,
    JsonEventView,
    project_runtime_event_to_json_views,
    project_session_event,
    should_emit_projected_event,
    should_emit_runtime_event_view,
)
from loushang.coding.mode.base import ModeAdapter, ModeState
from loushang.coding.work_executor import SubmitCodingTurn
from loushang.coding.work_runtime import CodingWorkRuntime
from loushang.coding.work_shell import CodingWorkShell
from loushang.harness.conversation import NativeConversationHeaderCodec
from loushang.harness.events import RuntimeEvent, normalize_event_select
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime
from loushang.protocol import require_json_value
from loushang.work import EventLogBackend

_HEADER_CODEC = NativeConversationHeaderCodec()


class _CodingPrintFailure(RuntimeError):
    pass


class PrintMode(ModeAdapter):
    def __init__(
        self,
        *,
        runtime: Any,
        session: Any,
        stdout: TextIO,
        stderr: TextIO | None = None,
        output_mode: Literal["text", "json"] = "text",
        event_view: JsonEventView = "full",
        event_select: Sequence[str] | str | None = None,
        render_tool_events: bool = False,
        work_event_log: EventLogBackend | None = None,
        coding_work_runtime: CodingWorkRuntime | None = None,
        method_id: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        step_index: int | None = None,
        step_title: str | None = None,
        planned_constraint: Mapping[str, object] | None = None,
        audit_policy: Mapping[str, object] | None = None,
        plan_facts: Mapping[str, object] | None = None,
        step_facts: Mapping[str, object] | None = None,
    ) -> None:
        if output_mode not in {"text", "json"}:
            raise ValueError(f"unsupported output mode: {output_mode}")
        if output_mode != "json":
            if event_view != "full":
                raise ValueError("event_view is only supported for json output mode")
            if event_select:
                raise ValueError("event_select is only supported for json output mode")
            if render_tool_events:
                raise ValueError(
                    "render_tool_events is only supported for json output mode"
                )
        elif event_view not in SUPPORTED_JSON_EVENT_VIEWS:
            raise ValueError(f"unsupported json event view: {event_view}")
        self.runtime = runtime
        self.session = session
        self.stdout = stdout
        if stderr is not None:
            self.stderr = stderr
        elif output_mode == "json":
            self.stderr = sys.stderr
        else:
            self.stderr = stdout
        self.output_mode = output_mode
        self.event_view = event_view
        self.event_select = normalize_event_select(event_select)
        self.render_tool_events = render_tool_events
        self.work_event_log = work_event_log
        self.coding_work_runtime = coding_work_runtime
        self.method_id = method_id
        self.plan_id = plan_id
        self.step_id = step_id
        self.step_index = step_index
        self.step_title = step_title
        self.planned_constraint = planned_constraint
        self.audit_policy = audit_policy
        self.plan_facts = plan_facts
        self.step_facts = step_facts
        self._tool_render_runtime: ToolRenderRuntime | None = None
        self._tool_definition_resolver: ToolDefinitionResolver | None = None
        self._disposed = False
        self._configure_tool_rendering(session)

    async def start(
        self,
        user_input: str | None = None,
        *,
        images: list[object] | None = None,
        follow_up_messages: Sequence[str] = (),
        dispose: bool = True,
    ) -> int:
        if user_input is None:
            raise ValueError("Print mode requires a user input")
        return await self.run_once(
            user_input,
            images=images,
            follow_up_messages=follow_up_messages,
            dispose=dispose,
        )

    async def stop(self) -> int:
        return 0

    async def submit_input(self, input_payload: object) -> int:
        if not isinstance(input_payload, str):
            raise TypeError("Print mode submit_input expects a string")
        return await self.run_once(input_payload)

    async def wait_for_idle(self) -> int:
        await self.session.wait_for_idle()
        return 0

    def rebind_session(self, session: object | None = None) -> int:
        if session is None:
            getter = getattr(self.runtime, "get_current_session", None)
            if not callable(getter):
                raise ValueError("Print mode rebind_session requires a session")
            session = getter()
        self.session = session
        self._configure_tool_rendering(session)
        return 0

    async def dispose(self) -> int:
        if self._disposed:
            return 0
        self._disposed = True
        await dispose_product_host(self.runtime, self.session)
        return 0

    def render_event(self, event: object) -> None:
        self._handle_event(event)

    async def run_once(
        self,
        user_input: str,
        *,
        images: list[object] | None = None,
        follow_up_messages: Sequence[str] = (),
        dispose: bool = True,
    ) -> int:
        def unsubscribe() -> None:
            return None

        exit_code = 0
        try:
            if self.output_mode == "json":
                header = self.session.session_manager.get_header()
                self._write_json_line(dict(_HEADER_CODEC.encode_header(header)))
            unsubscribe = self._subscribe_to_events()
            await self._prompt_session(
                user_input,
                images=images,
            )
            await self.session.wait_for_idle()
            for message in follow_up_messages:
                await self._prompt_session(
                    message,
                    include_work_metadata=False,
                )
                await self.session.wait_for_idle()
            assistant_failure = _last_assistant_failure_message(self.session)
            if assistant_failure is not None:
                self.stderr.write(assistant_failure + "\n")
                exit_code = 1
        except Exception as exc:
            self.stderr.write(f"Error: {exc}\n")
            exit_code = 1
        finally:
            unsubscribe()
            if dispose:
                try:
                    await self.dispose()
                except Exception as exc:
                    self.stderr.write(f"Error: {exc}\n")
                    exit_code = 1
        return exit_code

    async def run_plan(
        self,
        turns: Sequence[SubmitCodingTurn],
        *,
        dispose: bool = True,
    ) -> int:
        """Run one fixed MethodPlan through the Work-owned step sequencer."""

        if self.work_event_log is None:
            raise ValueError("Work event log is required for planned execution")

        def unsubscribe() -> None:
            return None

        async def after_turn(
            turn: SubmitCodingTurn, turn_index: int, turn_count: int
        ) -> None:
            del turn, turn_index, turn_count
            assistant_failure = _last_assistant_failure_message(self.session)
            if assistant_failure is not None:
                raise _CodingPrintFailure(assistant_failure)

        exit_code = 0
        try:
            if self.output_mode == "json":
                header = self.session.session_manager.get_header()
                self._write_json_line(dict(_HEADER_CODEC.encode_header(header)))
            unsubscribe = self._subscribe_to_events()
            shell = CodingWorkShell(
                session=self.session,
                event_log=self.work_event_log,
                coding_runtime=self.coding_work_runtime,
            )
            await shell.submit_coding_plan(
                turns,
                session_id=_work_session_id(self.session),
                after_turn=after_turn,
                wait_for_idle_after_prompt=True,
            )
        except _CodingPrintFailure as error:
            self.stderr.write(f"{error}\n")
            exit_code = 1
        except Exception as error:
            self.stderr.write(f"Error: {error}\n")
            exit_code = 1
        finally:
            unsubscribe()
            if dispose:
                try:
                    await self.dispose()
                except Exception as error:
                    self.stderr.write(f"Error: {error}\n")
                    exit_code = 1
        return exit_code

    def get_mode_state(self) -> ModeState:
        return _serialize_print_mode_state(self.session)

    def _handle_event(self, event: object) -> None:
        if self.output_mode == "json":
            if isinstance(event, dict):
                for projected_event in project_session_event(
                    event,
                    event_view=self.event_view,
                    tool_render_runtime=self._tool_render_runtime,
                    tool_definition_resolver=self._tool_definition_resolver,
                ):
                    if should_emit_projected_event(projected_event, self.event_select):
                        self._write_json_line(projected_event)
            return
        rendered = self._render_event(event)
        if rendered is None:
            return
        self.stdout.write(rendered + "\n")

    def _subscribe_to_events(self):
        subscribe_runtime_events = getattr(
            self.session, "subscribe_runtime_events", None
        )
        if self.output_mode == "json" and callable(subscribe_runtime_events):
            return subscribe_runtime_events(self._handle_runtime_event)
        return self.session.subscribe(self._handle_event)

    def _handle_runtime_event(self, event: RuntimeEvent[object]) -> None:
        for projected_event in project_runtime_event_to_json_views(
            event,
            event_view=self.event_view,
            tool_render_runtime=self._tool_render_runtime,
            tool_definition_resolver=self._tool_definition_resolver,
        ):
            if should_emit_runtime_event_view(projected_event, self.event_select):
                self._write_json_line(projected_event.payload)

    def _write_json_line(self, payload: object) -> None:
        projected = require_json_value(payload, name="print_json_event")
        self.stdout.write(
            json.dumps(projected, ensure_ascii=False, allow_nan=False) + "\n"
        )

    def _configure_tool_rendering(self, session: Any) -> None:
        if not self.render_tool_events:
            self._tool_render_runtime = None
            self._tool_definition_resolver = None
            return
        self._tool_render_runtime = ToolRenderRuntime(cwd=_session_cwd(session))
        self._tool_definition_resolver = _tool_definition_resolver(session)

    def _render_event(self, event: object) -> str | None:
        if not isinstance(event, dict):
            return None

        event_type = event.get("type")
        if event_type == "tool_execution_start":
            return self._render_tool_event_line(event, phase="start")
        if event_type == "tool_execution_end":
            return self._render_tool_event_line(event, phase="end")
        if event_type != "message_end":
            return None

        message = event.get("message")
        role = getattr(message, "role", None)
        if role != "assistant":
            return None

        content = getattr(message, "content", None)
        if not isinstance(content, list):
            return None

        text_parts = [
            part.text
            for part in content
            if getattr(part, "type", None) == "text"
            and isinstance(getattr(part, "text", None), str)
        ]
        if not text_parts:
            return None
        return "\n".join(text_parts)

    def _render_tool_event_line(
        self, event: dict[str, object], *, phase: str
    ) -> str | None:
        tool_name = event.get("tool_name")
        tool_call_id = event.get("tool_call_id")
        if not isinstance(tool_name, str):
            return None

        parts = [f"[tool:{tool_name}"]
        if isinstance(tool_call_id, str) and tool_call_id:
            parts.append(f" {tool_call_id}")
        parts.append(f"] {phase}")

        args = event.get("args")
        rendered_args = self._render_tool_args(args)
        if rendered_args is not None:
            parts.append(f" {rendered_args}")
        return "".join(parts)

    def _render_tool_args(self, args: object) -> str | None:
        if args is None:
            return None
        if args in ({}, [], ()):
            return None
        try:
            return json.dumps(args, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return repr(args)

    async def _prompt_session(
        self,
        user_input: str,
        *,
        images: list[object] | None = None,
        include_work_metadata: bool = True,
    ) -> None:
        if self.work_event_log is None:
            await _prompt_session(self.session, user_input, images=images)
            return
        shell = CodingWorkShell(
            session=self.session,
            event_log=self.work_event_log,
            coding_runtime=self.coding_work_runtime,
        )
        await shell.submit_coding_turn(
            user_input,
            session_id=_work_session_id(self.session),
            images=images,
            method_id=self.method_id if include_work_metadata else None,
            plan_id=self.plan_id if include_work_metadata else None,
            step_id=self.step_id if include_work_metadata else None,
            step_index=self.step_index if include_work_metadata else None,
            step_title=self.step_title if include_work_metadata else None,
            planned_constraint=(
                self.planned_constraint if include_work_metadata else None
            ),
            audit_policy=self.audit_policy if include_work_metadata else None,
            plan_facts=self.plan_facts if include_work_metadata else None,
            step_facts=self.step_facts if include_work_metadata else None,
        )


def _serialize_print_mode_state(session: Any) -> ModeState:
    state_getter = getattr(session, "get_state", None)
    state = state_getter() if callable(state_getter) else None
    session_id = _safe_getattr(session, "session_id", "")
    session_name = _safe_getattr(session, "session_name", None)
    session_file = _safe_getattr(session, "session_file", None)
    steering = _safe_list(getattr(state, "steering", None))
    follow_up = _safe_list(getattr(state, "follow_up", None))
    thinking = getattr(state, "thinking_level", "off") if state is not None else "off"
    is_compacting = bool(
        _safe_getattr(state, "is_compacting", False) if state is not None else False
    )
    run_status = _safe_getattr(_safe_getattr(state, "run", None), "status", "idle")

    model = _serialize_model_snapshot(session, state)
    payload: ModeState = {
        "sessionId": str(session_id),
        "model": model,
        "thinkingLevel": str(thinking),
        "isStreaming": run_status == "running",
        "isCompacting": is_compacting,
        "steeringMode": _queue_mode(session, "steering_mode"),
        "followUpMode": _queue_mode(session, "follow_up_mode"),
        "autoCompactionEnabled": bool(
            _safe_getattr(session, "auto_compaction_enabled", False)
        ),
        "messageCount": _count_messages(session),
        "pendingMessageCount": len(steering) + len(follow_up),
    }
    if isinstance(session_name, str) and session_name:
        payload["sessionName"] = session_name
    if isinstance(session_file, str) and session_file:
        payload["sessionFile"] = session_file
    return payload


def _last_assistant_failure_message(session: Any) -> str | None:
    for message in reversed(_session_messages(session)):
        if _safe_getattr(message, "role", None) != "assistant":
            continue
        stop_reason = _safe_getattr(
            message, "stop_reason", _safe_getattr(message, "stopReason", None)
        )
        if stop_reason not in {"error", "aborted"}:
            return None
        error_message = _safe_getattr(
            message, "error_message", _safe_getattr(message, "errorMessage", None)
        )
        return (
            error_message
            if isinstance(error_message, str) and error_message
            else f"Request {stop_reason}"
        )
    return None


def _session_messages(session: Any) -> list[object]:
    context_getter = getattr(session, "get_session_context", None)
    if callable(context_getter):
        try:
            context = context_getter()
        except Exception:
            context = None
        messages = _safe_getattr(context, "messages", None)
        if isinstance(messages, list | tuple):
            return list(messages)
    messages = _safe_getattr(session, "messages", None)
    if isinstance(messages, list | tuple):
        return list(messages)
    agent_state = _safe_getattr(_safe_getattr(session, "agent", None), "state", None)
    messages = _safe_getattr(agent_state, "messages", None)
    if isinstance(messages, list | tuple):
        return list(messages)
    return []


def _serialize_model_snapshot(session: Any, state: Any) -> dict[str, object] | None:
    model = _safe_getattr(
        _safe_getattr(_safe_getattr(session, "agent", None), "state", None),
        "model",
        None,
    )
    if model is not None:
        provider = _safe_getattr(model, "provider_id", None) or _safe_getattr(
            model, "provider", None
        )
        model_id = _safe_getattr(model, "id", None)
        if (
            isinstance(provider, str)
            and isinstance(model_id, str)
            and provider
            and model_id
            and not _is_unknown_model(provider, model_id)
        ):
            name = _safe_getattr(model, "name", model_id)
            return {
                "provider": provider,
                "id": model_id,
                "name": name if isinstance(name, str) and name else str(model_id),
            }

    model_selection = _safe_getattr(state, "model_selection", None)
    provider = _safe_getattr(model_selection, "provider", None)
    model_id = _safe_getattr(model_selection, "model_id", None)
    if (
        isinstance(provider, str)
        and isinstance(model_id, str)
        and provider
        and model_id
        and not _is_unknown_model(provider, model_id)
    ):
        return {"provider": provider, "id": model_id, "name": model_id}
    return None


def _count_messages(session: Any) -> int:
    context_getter = getattr(session, "get_session_context", None)
    if callable(context_getter):
        try:
            context = context_getter()
        except Exception:
            context = None
        else:
            messages = _safe_getattr(context, "messages", None)
            if isinstance(messages, list | tuple):
                return len(messages)
    messages = _safe_getattr(session, "messages", None)
    if isinstance(messages, list | tuple):
        return len(messages)
    return 0


def _safe_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _queue_mode(target: Any, attr: str) -> str:
    value = _safe_getattr(target, attr, None)
    if value in {"all", "one-at-a-time"}:
        return value
    agent_value = _safe_getattr(_safe_getattr(target, "agent", None), attr, None)
    if agent_value in {"all", "one-at-a-time"}:
        return agent_value
    return "one-at-a-time"


def _is_unknown_model(provider: str, model_id: str) -> bool:
    return provider == "unknown" and model_id == "unknown"


def _safe_getattr(target: Any, name: str, default: object) -> object:
    try:
        return getattr(target, name, default)
    except Exception:
        return default


def _work_session_id(session: Any) -> str:
    session_id = _safe_getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id
    session_manager = getattr(session, "session_manager", None)
    get_header = getattr(session_manager, "get_header", None)
    if callable(get_header):
        try:
            header = get_header()
        except Exception:
            header = None
        header_id = _safe_getattr(header, "conversation_id", None)
        if isinstance(header_id, str) and header_id:
            return header_id
    return "session"


async def run_print_mode(
    *,
    runtime: Any,
    session: Any,
    user_input: str,
    stdout: TextIO,
    stderr: TextIO | None = None,
    images: list[object] | None = None,
    follow_up_messages: Sequence[str] = (),
    output_mode: Literal["text", "json"] = "text",
    event_view: JsonEventView = "full",
    event_select: Sequence[str] | str | None = None,
    render_tool_events: bool = False,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: CodingWorkRuntime | None = None,
    method_id: str | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    step_index: int | None = None,
    step_title: str | None = None,
    planned_constraint: Mapping[str, object] | None = None,
    audit_policy: Mapping[str, object] | None = None,
    plan_facts: Mapping[str, object] | None = None,
    step_facts: Mapping[str, object] | None = None,
    dispose: bool = True,
) -> int:
    mode = PrintMode(
        runtime=runtime,
        session=session,
        stdout=stdout,
        stderr=stderr,
        output_mode=output_mode,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
        method_id=method_id,
        plan_id=plan_id,
        step_id=step_id,
        step_index=step_index,
        step_title=step_title,
        planned_constraint=planned_constraint,
        audit_policy=audit_policy,
        plan_facts=plan_facts,
        step_facts=step_facts,
    )
    return await mode.run_once(
        user_input,
        images=images,
        follow_up_messages=follow_up_messages,
        dispose=dispose,
    )


async def run_print_plan_mode(
    *,
    runtime: Any,
    session: Any,
    turns: Sequence[SubmitCodingTurn],
    stdout: TextIO,
    stderr: TextIO | None = None,
    output_mode: Literal["text", "json"] = "text",
    event_view: JsonEventView = "full",
    event_select: Sequence[str] | str | None = None,
    render_tool_events: bool = False,
    work_event_log: EventLogBackend,
    coding_work_runtime: CodingWorkRuntime | None = None,
    dispose: bool = True,
) -> int:
    mode = PrintMode(
        runtime=runtime,
        session=session,
        stdout=stdout,
        stderr=stderr,
        output_mode=output_mode,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
    )
    return await mode.run_plan(turns, dispose=dispose)


async def _prompt_session(
    session: Any, user_input: str, *, images: list[object] | None = None
) -> None:
    if images is None:
        await session.prompt(user_input)
        return
    await session.prompt(user_input, images=images)


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

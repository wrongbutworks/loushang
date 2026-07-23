from __future__ import annotations

import inspect
import time
import traceback
from collections.abc import Mapping, Sequence
from typing import Any, TextIO

from loushang.coding.domain.work import create_coding_work_runtime
from loushang.coding.model_selection import ensure_usable_session_model
from loushang.coding.presentation.tui.plain import (
    PlainCodingUiRenderer,
    build_plain_coding_event_projection,
)
from loushang.harnesstui.conversation.plain_prompt_host import (
    PlainPromptHostPorts,
    PreparedPlainPromptRun,
    run_plain_prompt_host,
)
from loushang.work import EventLogBackend
from loushang.work.session import SessionWorkRuntime, SessionWorkTurn


async def run_prompt_command(
    *,
    runtime: Any,
    session: Any,
    prompt: str,
    stdout: TextIO,
    stderr: TextIO,
    images: list[object] | None = None,
    follow_up_messages: Sequence[str] = (),
    verbose: bool = False,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: SessionWorkRuntime | None = None,
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
    """Run one product prompt and render the stable coding transcript."""

    renderer = PlainCodingUiRenderer(stdout=stdout, stderr=stderr)
    event_renderer = build_plain_coding_event_projection(
        renderer,
        render_user_messages=False,
    )

    async def submit_turn(text: str, turn_index: int, turn_count: int) -> None:
        del turn_count
        await _run_prompt_session(
            session,
            text,
            images=images if turn_index == 0 else None,
            work_event_log=work_event_log,
            coding_work_runtime=coding_work_runtime,
            method_id=method_id if turn_index == 0 else None,
            plan_id=plan_id if turn_index == 0 else None,
            step_id=step_id if turn_index == 0 else None,
            step_index=step_index if turn_index == 0 else None,
            step_title=step_title if turn_index == 0 else None,
            planned_constraint=planned_constraint if turn_index == 0 else None,
            audit_policy=audit_policy if turn_index == 0 else None,
            plan_facts=plan_facts if turn_index == 0 else None,
            step_facts=step_facts if turn_index == 0 else None,
        )

    def resolve_failure(previous_error: str | None) -> str | None:
        assistant_failure = _last_assistant_failure_message(session)
        if (
            assistant_failure is None
            and event_renderer.last_error_message != previous_error
        ):
            return event_renderer.last_error_message
        return assistant_failure

    return await run_plain_prompt_host(
        PreparedPlainPromptRun(
            prompts=(prompt, *follow_up_messages),
            ports=PlainPromptHostPorts[str | None](
                prepare=lambda: ensure_usable_session_model(session),
                subscribe=lambda: session.subscribe(event_renderer.handle),
                submit=submit_turn,
                wait_for_idle=session.wait_for_idle,
                capture_failure_state=lambda: event_renderer.last_error_message,
                resolve_failure=resolve_failure,
                render_user=renderer.render_user,
                render_worked=renderer.render_worked,
                render_error=renderer.render_error,
                dispose=lambda: _dispose_runtime_or_session(runtime, session),
            ),
            stderr=stderr,
            verbose=verbose,
            dispose=dispose,
        )
    )


class _CodingPromptFailure(RuntimeError):
    pass


async def run_prompt_plan_command(
    *,
    runtime: Any,
    session: Any,
    turns: Sequence[SessionWorkTurn],
    stdout: TextIO,
    stderr: TextIO,
    work_event_log: EventLogBackend,
    coding_work_runtime: SessionWorkRuntime | None = None,
    verbose: bool = False,
    dispose: bool = True,
) -> int:
    """Render and execute a fixed MethodPlan as one Work-owned run."""

    renderer = PlainCodingUiRenderer(stdout=stdout, stderr=stderr)
    event_renderer = build_plain_coding_event_projection(
        renderer,
        render_user_messages=False,
    )
    started_at = 0.0
    previous_error: str | None = None

    def before_turn(
        turn: SessionWorkTurn, turn_index: int, turn_count: int
    ) -> None:
        del turn_index, turn_count
        nonlocal started_at, previous_error
        started_at = time.monotonic()
        previous_error = event_renderer.last_error_message
        renderer.render_user(turn.text)

    def after_turn(
        turn: SessionWorkTurn, turn_index: int, turn_count: int
    ) -> None:
        del turn, turn_index, turn_count
        assistant_failure = _last_assistant_failure_message(session)
        if (
            assistant_failure is None
            and event_renderer.last_error_message != previous_error
        ):
            assistant_failure = event_renderer.last_error_message
        if assistant_failure is not None:
            raise _CodingPromptFailure(assistant_failure)
        renderer.render_worked(time.monotonic() - started_at)

    def unsubscribe() -> None:
        return None

    exit_code = 0
    try:
        await ensure_usable_session_model(session)
        unsubscribe = session.subscribe(event_renderer.handle)
        work_runtime = coding_work_runtime or create_coding_work_runtime(
            session=session,
            event_log=work_event_log,
            session_id=lambda: _work_session_id(session),
        )
        await work_runtime.submit_plan(
            turns,
            session_id=_work_session_id(session),
            before_turn=before_turn,
            after_turn=after_turn,
            wait_for_idle_after_prompt=True,
        )
    except _CodingPromptFailure:
        exit_code = 1
    except Exception as error:
        renderer.render_error(str(error) or type(error).__name__)
        if verbose:
            traceback.print_exception(
                type(error), error, error.__traceback__, file=stderr
            )
        exit_code = 1
    finally:
        unsubscribe()
        if dispose:
            try:
                await _dispose_runtime_or_session(runtime, session)
            except Exception as error:
                renderer.render_error(str(error) or type(error).__name__)
                if verbose:
                    traceback.print_exception(
                        type(error), error, error.__traceback__, file=stderr
                    )
                exit_code = 1
    return exit_code


async def _run_prompt_session(
    session: Any,
    user_input: str,
    *,
    images: list[object] | None = None,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: SessionWorkRuntime | None = None,
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
    if work_event_log is None:
        await _prompt_session(session, user_input, images=images)
        return
    work_runtime = coding_work_runtime or create_coding_work_runtime(
        session=session,
        event_log=work_event_log,
        session_id=lambda: _work_session_id(session),
    )
    await work_runtime.submit_turn(
        SessionWorkTurn(
            text=user_input,
            images=images,
            method_id=method_id,
            plan_id=plan_id,
            step_id=step_id,
            step_index=step_index,
            step_title=step_title,
            planned_constraint=planned_constraint,
            audit_policy=audit_policy,
            plan_facts=plan_facts,
            step_facts=step_facts,
        ),
        session_id=_work_session_id(session),
    )


async def _prompt_session(
    session: Any, user_input: str, *, images: list[object] | None = None
) -> None:
    if images is None:
        await session.prompt(user_input)
        return
    await session.prompt(user_input, images=images)


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
        if isinstance(messages, list):
            return list(messages)
    messages = _safe_getattr(session, "messages", None)
    if isinstance(messages, list):
        return list(messages)
    agent_state = _safe_getattr(_safe_getattr(session, "agent", None), "state", None)
    messages = _safe_getattr(agent_state, "messages", None)
    if isinstance(messages, list):
        return list(messages)
    return []


async def _dispose_runtime_or_session(runtime: Any, session: Any) -> None:
    disposer = getattr(runtime, "dispose", None)
    if not callable(disposer):
        disposer = getattr(session, "dispose", None)
    if not callable(disposer):
        return
    result = disposer()
    if inspect.isawaitable(result):
        await result


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


__all__ = ["run_prompt_command", "run_prompt_plan_command"]

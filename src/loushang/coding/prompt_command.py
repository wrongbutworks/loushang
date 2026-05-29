from __future__ import annotations

import inspect
import time
import traceback
from typing import Any, Sequence, TextIO

from loushang.coding.ui.events import CodingUiEventRenderer
from loushang.coding.ui.model import ensure_usable_session_model
from loushang.coding.ui.renderer import CodingUiRenderer


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
) -> int:
    """Run one product prompt and render the stable coding transcript."""

    renderer = CodingUiRenderer(stdout=stdout, stderr=stderr)
    event_renderer = CodingUiEventRenderer(renderer, render_user_messages=False)

    def unsubscribe() -> None:
        return None

    exit_code = 0
    try:
        await ensure_usable_session_model(session)
        unsubscribe = session.subscribe(event_renderer.handle)
        exit_code = await _run_turn(
            session,
            renderer,
            event_renderer,
            prompt,
            images=images,
        )
        if exit_code == 0:
            for message in follow_up_messages:
                exit_code = await _run_turn(
                    session,
                    renderer,
                    event_renderer,
                    message,
                )
                if exit_code != 0:
                    break
    except Exception as exc:
        renderer.render_error(str(exc) or exc.__class__.__name__)
        if verbose:
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=stderr)
        exit_code = 1
    finally:
        unsubscribe()
        try:
            await _dispose_runtime_or_session(runtime, session)
        except Exception as exc:
            renderer.render_error(str(exc) or exc.__class__.__name__)
            if verbose:
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=stderr)
            exit_code = 1
    return exit_code


async def _run_turn(
    session: Any,
    renderer: CodingUiRenderer,
    event_renderer: CodingUiEventRenderer,
    prompt: str,
    *,
    images: list[object] | None = None,
) -> int:
    started_at = time.monotonic()
    previous_error = event_renderer.last_error_message
    renderer.render_user(prompt)
    await _prompt_session(session, prompt, images=images)
    await session.wait_for_idle()
    assistant_failure = _last_assistant_failure_message(session)
    if assistant_failure is None and event_renderer.last_error_message != previous_error:
        assistant_failure = event_renderer.last_error_message
    if assistant_failure is not None:
        return 1
    renderer.render_worked(time.monotonic() - started_at)
    return 0


async def _prompt_session(session: Any, user_input: str, *, images: list[object] | None = None) -> None:
    if images is None:
        await session.prompt(user_input)
        return
    await session.prompt(user_input, images=images)


def _last_assistant_failure_message(session: Any) -> str | None:
    for message in reversed(_session_messages(session)):
        if _safe_getattr(message, "role", None) != "assistant":
            continue
        stop_reason = _safe_getattr(message, "stop_reason", _safe_getattr(message, "stopReason", None))
        if stop_reason not in {"error", "aborted"}:
            return None
        error_message = _safe_getattr(message, "error_message", _safe_getattr(message, "errorMessage", None))
        return error_message if isinstance(error_message, str) and error_message else f"Request {stop_reason}"
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


__all__ = ["run_prompt_command"]

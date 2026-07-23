from __future__ import annotations

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
    dispose_runtime_or_session,
    last_assistant_failure_message,
    run_plain_prompt_host,
    session_identity,
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
        assistant_failure = last_assistant_failure_message(session)
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
                dispose=lambda: dispose_runtime_or_session(runtime, session),
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
        assistant_failure = last_assistant_failure_message(session)
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
            session_id=lambda: session_identity(session),
        )
        await work_runtime.submit_plan(
            turns,
            session_id=session_identity(session),
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
                await dispose_runtime_or_session(runtime, session)
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
        session_id=lambda: session_identity(session),
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
        session_id=session_identity(session),
    )


async def _prompt_session(
    session: Any, user_input: str, *, images: list[object] | None = None
) -> None:
    if images is None:
        await session.prompt(user_input)
        return
    await session.prompt(user_input, images=images)


__all__ = ["run_prompt_command", "run_prompt_plan_command"]

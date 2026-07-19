"""Product-neutral lifecycle host for one-shot plain prompt runs."""

from __future__ import annotations

import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TextIO, TypeVar

FailureStateT = TypeVar("FailureStateT")
Cleanup = Callable[[], None]


def _no_cleanup() -> None:
    return None


@dataclass(frozen=True, slots=True)
class PlainPromptHostPorts(Generic[FailureStateT]):
    """Prepared product effects consumed by the one-shot prompt host.

    Session, model, raw event, work metadata, and failure interpretation stay
    behind these callbacks. The shared host only owns ordering and exit state.
    """

    prepare: Callable[[], Awaitable[object]]
    subscribe: Callable[[], Cleanup]
    submit: Callable[[str, int, int], Awaitable[None]]
    wait_for_idle: Callable[[], Awaitable[None]]
    capture_failure_state: Callable[[], FailureStateT]
    resolve_failure: Callable[[FailureStateT], str | None]
    render_user: Callable[[str], None]
    render_worked: Callable[[float], None]
    render_error: Callable[[str], None]
    dispose: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PreparedPlainPromptRun(Generic[FailureStateT]):
    """Prepared prompt sequence and product ports for one terminal run."""

    prompts: tuple[str, ...]
    ports: PlainPromptHostPorts[FailureStateT]
    stderr: TextIO
    verbose: bool = False
    dispose: bool = True
    now: Callable[[], float] = time.monotonic


async def run_plain_prompt_host(
    run: PreparedPlainPromptRun[FailureStateT],
) -> int:
    """Run prepared turns, then unsubscribe and optionally dispose.

    This deliberately preserves the original error boundary: ordinary run and
    disposal exceptions become exit code 1, while unsubscribe errors still
    propagate and prevent disposal rather than being silently swallowed.
    """

    unsubscribe = _no_cleanup
    exit_code = 0
    try:
        await run.ports.prepare()
        unsubscribe = run.ports.subscribe()
        turn_count = len(run.prompts)
        for turn_index, prompt in enumerate(run.prompts):
            exit_code = await _run_plain_prompt_turn(
                run,
                prompt,
                turn_index=turn_index,
                turn_count=turn_count,
            )
            if exit_code != 0:
                break
    except Exception as error:
        _present_exception(run, error)
        exit_code = 1
    finally:
        unsubscribe()
        if run.dispose:
            try:
                await run.ports.dispose()
            except Exception as error:
                _present_exception(run, error)
                exit_code = 1
    return exit_code


async def _run_plain_prompt_turn(
    run: PreparedPlainPromptRun[FailureStateT],
    prompt: str,
    *,
    turn_index: int,
    turn_count: int,
) -> int:
    started_at = run.now()
    previous_failure = run.ports.capture_failure_state()
    run.ports.render_user(prompt)
    await run.ports.submit(prompt, turn_index, turn_count)
    await run.ports.wait_for_idle()
    if run.ports.resolve_failure(previous_failure) is not None:
        return 1
    run.ports.render_worked(run.now() - started_at)
    return 0


def _present_exception(
    run: PreparedPlainPromptRun[FailureStateT],
    error: Exception,
) -> None:
    run.ports.render_error(str(error) or error.__class__.__name__)
    if run.verbose:
        traceback.print_exception(
            type(error),
            error,
            error.__traceback__,
            file=run.stderr,
        )


__all__ = [
    "PlainPromptHostPorts",
    "PreparedPlainPromptRun",
    "run_plain_prompt_host",
]

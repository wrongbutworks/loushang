from __future__ import annotations

import asyncio
import os
import signal as signal_module
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .operations import raise_if_operation_aborted


@dataclass(frozen=True)
class ExternalProcessResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ExternalProcessStreamResult:
    returncode: int
    stderr: str
    stopped_early: bool


async def run_external_process(
    command: Sequence[str],
    *,
    cwd: Path | str,
    signal: object | None = None,
) -> ExternalProcessResult:
    raise_if_operation_aborted(signal)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    communicate_task = asyncio.create_task(process.communicate())
    abort_task = (
        asyncio.create_task(_wait_for_abort(signal)) if signal is not None else None
    )
    tasks = [communicate_task, *([abort_task] if abort_task is not None else [])]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    if abort_task is not None and abort_task in done:
        _kill_process(process)
        try:
            await asyncio.wait_for(communicate_task, timeout=1)
        except asyncio.TimeoutError:
            communicate_task.cancel()
        raise_if_operation_aborted(signal)
        raise RuntimeError("Operation aborted")

    for task in pending:
        task.cancel()
    stdout, stderr = communicate_task.result()
    return ExternalProcessResult(
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


async def run_external_process_lines(
    command: Sequence[str],
    *,
    cwd: Path | str,
    on_stdout_line: Callable[[str], bool],
    signal: object | None = None,
) -> ExternalProcessStreamResult:
    raise_if_operation_aborted(signal)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout_task = asyncio.create_task(_stream_stdout_lines(process, on_stdout_line))
    stderr_task = asyncio.create_task(
        process.stderr.read() if process.stderr is not None else _empty_bytes()
    )
    abort_task = (
        asyncio.create_task(_wait_for_abort(signal)) if signal is not None else None
    )
    tasks = [stdout_task, *([abort_task] if abort_task is not None else [])]
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    if abort_task is not None and abort_task in done:
        _kill_process(process)
        await _wait_for_process_exit(process)
        stdout_task.cancel()
        stderr_task.cancel()
        raise_if_operation_aborted(signal)
        raise RuntimeError("Operation aborted")

    stopped_early = await stdout_task
    if abort_task is not None:
        abort_task.cancel()
    await _wait_for_process_exit(process)
    stderr = await _read_stderr_result(stderr_task)
    return ExternalProcessStreamResult(
        returncode=process.returncode if process.returncode is not None else 0,
        stderr=stderr.decode("utf-8", errors="replace"),
        stopped_early=stopped_early,
    )


async def _stream_stdout_lines(
    process: asyncio.subprocess.Process,
    on_stdout_line: Callable[[str], bool],
) -> bool:
    if process.stdout is None:
        return False
    stopped_early = False
    while True:
        line = await process.stdout.readline()
        if not line:
            return stopped_early
        should_continue = on_stdout_line(
            line.decode("utf-8", errors="replace").rstrip("\n")
        )
        if not should_continue:
            stopped_early = True
            _kill_process(process)
            return stopped_early


async def _wait_for_process_exit(process: asyncio.subprocess.Process) -> None:
    try:
        await asyncio.wait_for(process.wait(), timeout=1)
    except asyncio.TimeoutError:
        _kill_process(process)
        await process.wait()


async def _read_stderr_result(stderr_task: asyncio.Task[bytes]) -> bytes:
    try:
        return await stderr_task
    except asyncio.CancelledError:
        return b""


async def _empty_bytes() -> bytes:
    return b""


async def _wait_for_abort(signal: object | None) -> None:
    while signal is not None and not getattr(signal, "aborted", False):
        await asyncio.sleep(0.01)


def _kill_process(process: asyncio.subprocess.Process) -> None:
    try:
        if process.pid is not None and hasattr(os, "killpg"):
            os.killpg(process.pid, signal_module.SIGKILL)
            return
    except ProcessLookupError:
        return
    except OSError:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return

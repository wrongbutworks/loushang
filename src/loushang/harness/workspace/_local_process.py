"""Shared local OS mechanics for one-shot and hosted workspace processes."""

from __future__ import annotations

import asyncio
import os
import signal as signal_module
from collections.abc import Mapping


async def spawn_local_process(
    *,
    command: tuple[str, ...],
    cwd: str,
    environment: Mapping[str, str],
    pipe_stdin: bool,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=dict(environment),
        start_new_session=True,
        stdin=asyncio.subprocess.PIPE if pipe_stdin else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


def terminate_local_process(process: object) -> None:
    _signal_process_group(
        process,
        group_signal=signal_module.SIGTERM,
        fallback_method="terminate",
    )


def kill_local_process(process: object) -> None:
    _signal_process_group(
        process,
        group_signal=signal_module.SIGKILL,
        fallback_method="kill",
    )


def _signal_process_group(
    process: object,
    *,
    group_signal: signal_module.Signals,
    fallback_method: str,
) -> None:
    pid = getattr(process, "pid", None)
    try:
        if isinstance(pid, int) and pid > 0 and hasattr(os, "killpg"):
            os.killpg(pid, group_signal)
            return
    except ProcessLookupError:
        return
    except OSError:
        pass
    fallback = getattr(process, fallback_method, None)
    if not callable(fallback):
        return
    try:
        fallback()
    except ProcessLookupError:
        return


__all__ = [
    "kill_local_process",
    "spawn_local_process",
    "terminate_local_process",
]

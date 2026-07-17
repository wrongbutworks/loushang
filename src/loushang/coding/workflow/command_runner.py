from __future__ import annotations

import subprocess
from pathlib import Path

from loushang.harness.scenario import CommandRunResult


def run_local_shell_command(
    command: str,
    *,
    cwd: Path,
    timeout_s: float | None,
) -> CommandRunResult:
    """Coding's legacy local command assertion policy."""

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as error:
        return CommandRunResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error=f"timed out after {error.timeout}s: {command}",
        )
    return CommandRunResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


__all__ = ["run_local_shell_command"]

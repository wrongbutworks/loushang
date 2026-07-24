"""Coding model preparation bound to the shared scenario CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from loushang.coding.model_selection import ensure_usable_session_model
from loushang.harness.scenario.cli import run_workflow_cli
from loushang.harness.scenario.protocols import CommandRunResult
from loushang.harness.workspace.exec import ExecRequest, ExecService


async def run_prompt_steps_workflow(
    *,
    runtime: Any,
    session: Any,
    workflow_path: str | Path,
    cwd: str | Path,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool = False,
    default_step_timeout_s: float | None = 300.0,
    output_mode: str = "text",
) -> int:
    return await run_workflow_cli(
        runtime=runtime,
        session=session,
        workflow_path=workflow_path,
        cwd=cwd,
        stdout=stdout,
        stderr=stderr,
        verbose=verbose,
        default_step_timeout_s=default_step_timeout_s,
        output_mode=output_mode,
        prepare_agent_session=ensure_usable_session_model,
        command_runner=_run_coding_scenario_command,
    )


async def _run_coding_scenario_command(
    command: str,
    *,
    cwd: Path,
    timeout_s: float | None,
) -> CommandRunResult:
    result = await ExecService().execute(
        ExecRequest(
            command=("/bin/sh", "-c", command),
            cwd=str(cwd),
            timeout_seconds=timeout_s,
        )
    )
    return CommandRunResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        error=(
            f"timed out after {timeout_s}s: {command}" if result.timed_out else None
        ),
    )


__all__ = ["run_prompt_steps_workflow"]

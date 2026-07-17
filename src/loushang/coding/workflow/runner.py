"""Coding policy adapter for the Harness scenario runner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loushang.coding.workflow.command_runner import run_local_shell_command
from loushang.harness.scenario.protocols import CommandRunner, WorkflowAdapter
from loushang.harness.scenario.runner import (
    AgentSessionWorkflowAdapter,
)
from loushang.harness.scenario.runner import (
    run_workflow as _run_workflow,
)
from loushang.harness.scenario.schema import Workflow, WorkflowResult, WorkflowStep

StepStartCallback = Callable[[int, int, WorkflowStep], object]


async def run_workflow(
    workflow: Workflow,
    *,
    adapter: WorkflowAdapter,
    cwd: str | Path,
    default_step_timeout_s: float | None = 300.0,
    on_step_start: StepStartCallback | None = None,
    command_runner: CommandRunner | None = None,
) -> WorkflowResult:
    return await _run_workflow(
        workflow,
        adapter=adapter,
        cwd=cwd,
        default_step_timeout_s=default_step_timeout_s,
        on_step_start=on_step_start,
        command_runner=command_runner or run_local_shell_command,
    )


__all__ = ["AgentSessionWorkflowAdapter", "WorkflowAdapter", "run_workflow"]

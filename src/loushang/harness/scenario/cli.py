"""CLI entry helpers for Product-neutral scripted scenarios."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TextIO

from loushang.harness.scenario.loader import load_workflow, resolve_workflow_files

WorkflowCliRunner = Callable[..., Awaitable[int]]


async def run_fake_workflow_cli(
    workflow_path: str,
    *,
    project_root: str | Path,
    runner: WorkflowCliRunner,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool,
    output_mode: str,
    format_error: Callable[[BaseException], str] = str,
) -> int | None:
    """Run an all-fake workflow before a Product runtime is constructed."""

    root = Path(project_root)
    try:
        workflow_files = resolve_workflow_files(root, workflow_path)
        workflows = [load_workflow(path) for path in workflow_files]
    except Exception as error:
        stderr.write(f"Error: {format_error(error)}\n")
        return 1
    if not workflows or any(workflow.backend != "fake" for workflow in workflows):
        return None
    return await runner(
        runtime=None,
        session=None,
        workflow_path=Path(workflow_path),
        cwd=root,
        stdout=stdout,
        stderr=stderr,
        verbose=verbose,
        output_mode=output_mode,
    )


__all__ = ["WorkflowCliRunner", "run_fake_workflow_cli"]

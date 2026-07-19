from __future__ import annotations

import asyncio
import inspect
import traceback
from pathlib import Path
from typing import Any, TextIO

from loushang.coding.model_selection import ensure_usable_session_model
from loushang.coding.workflow.report import (
    format_workflow_json_report,
    format_workflow_report,
)
from loushang.coding.workflow.runner import run_workflow
from loushang.harness.scenario.fake_runtime import FakeWorkflowAdapter
from loushang.harness.scenario.loader import load_workflow, resolve_workflow_files
from loushang.harness.scenario.runner import AgentSessionWorkflowAdapter


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
    exit_code = 0
    try:
        root = Path(cwd).resolve()
        workflow_files = resolve_workflow_files(root, workflow_path)
        results = []
        passed = 0
        failed = 0
        for workflow_file in workflow_files:
            workflow = load_workflow(workflow_file)
            if output_mode != "json":
                stdout.write(f"workflow: {workflow.name}\n")
                stdout.flush()
            adapter = await _adapter_for_workflow(workflow.backend, session)
            result = await run_workflow(
                workflow,
                adapter=adapter,
                cwd=root,
                default_step_timeout_s=default_step_timeout_s,
                on_step_start=(
                    None
                    if output_mode == "json"
                    else lambda index, total, step: _write_step_progress(
                        stdout, index, total, _step_progress_label(step)
                    )
                ),
            )
            results.append(result)
            if output_mode != "json":
                stdout.write(format_workflow_report(result, include_header=False))
            if result.ok:
                passed += 1
            else:
                failed += 1
        if output_mode == "json":
            stdout.write(format_workflow_json_report(tuple(results)))
        elif len(workflow_files) > 1:
            stdout.write(f"workflow summary: {passed} passed, {failed} failed\n")
        exit_code = 0 if failed == 0 else 1
    except asyncio.CancelledError:
        stderr.write("Interrupted.\n")
        exit_code = 130
    except Exception as error:
        stderr.write(f"Error: {error}\n")
        if verbose:
            traceback.print_exception(
                type(error), error, error.__traceback__, file=stderr
            )
        exit_code = 1
    finally:
        try:
            await _dispose_runtime_or_session(runtime, session)
        except Exception as error:
            stderr.write(f"Error: {error}\n")
            if verbose:
                traceback.print_exception(
                    type(error), error, error.__traceback__, file=stderr
                )
            exit_code = 1
    return exit_code


def _write_step_progress(stdout: TextIO, index: int, total: int, prompt: str) -> None:
    stdout.write(f"[{index}/{total}] running: {prompt}\n")
    stdout.flush()


def _step_progress_label(step: object) -> str:
    for name in ("prompt", "text", "event", "kind"):
        value = getattr(step, name, None)
        if isinstance(value, str) and value:
            return value
    return step.__class__.__name__


async def _adapter_for_workflow(backend: str | None, session: Any) -> object:
    if backend == "fake":
        return FakeWorkflowAdapter()
    if backend is None:
        await ensure_usable_session_model(session)
        return AgentSessionWorkflowAdapter(session)
    raise ValueError(f"Unknown workflow backend: {backend}")


async def _dispose_runtime_or_session(runtime: Any, session: Any) -> None:
    disposer = getattr(runtime, "dispose", None)
    if not callable(disposer):
        disposer = getattr(session, "dispose", None)
    if not callable(disposer):
        return
    result = disposer()
    if inspect.isawaitable(result):
        await result

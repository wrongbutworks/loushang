# Agent Harness Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the prepared agent run contract to top-level `loushang.harness` while keeping `loushang.agent.Agent` as the low-level stateful runtime facade that depends only on `agent_loop`, not on harness.

**Architecture:** `loushang.agent` owns low-level agent primitives, `Agent`, and `agent_loop`. `loushang.harness` owns the single prepared-run contract (`AgentRunSpec`, `AgentRunResult`, `run_agent`) and may depend on `loushang.agent`; product packages such as `coding`, future `design`, `ppt`, and `cowork` depend on `loushang.harness`. During migration, `loushang.agent.harness` is a deprecated temporary compatibility re-export only; new code must import `loushang.harness`.

**Tech Stack:** Python 3.11+, `dataclasses`, `pytest`, `ruff`, existing `loushang.agent` / `loushang.ai` runtime.

---

## Boundary Decision

Target dependency graph:

```text
loushang.agent.Agent
  -> loushang.agent.agent_loop

loushang.harness.run_agent
  -> loushang.agent.agent_loop

loushang.agent.harness
  -> loushang.harness
  (deprecated temporary compatibility re-export)

loushang.coding / design / ppt / cowork
  -> loushang.harness
  -> loushang.agent
```

Non-goals for this refactor:

- Do not move `Agent` to `loushang.harness`.
- Do not introduce `HarnessRunSpec` or a second run result type.
- Do not migrate `coding.AgentSession` to direct harness execution yet.
- Do not add session persistence, resources, hooks, or product adapter protocols in this PR.
- Do not let `loushang.agent` import `loushang.harness`.

The important behavior-preserving change is that `Agent` stops routing through `run_agent`. It should call `run_agent_loop` and `run_agent_loop_continue` directly, exactly as PI's low-level `Agent` does.

## File Structure

- Create `src/loushang/harness/__init__.py`
  - Public exports for `AgentRunMode`, `AgentRunStatus`, `AgentEventSink`, `AgentRunSpec`, `AgentRunResult`, and `run_agent`.
- Create `src/loushang/harness/types.py`
  - Move the existing prepared run dataclasses from `src/loushang/agent/harness/types.py`.
- Create `src/loushang/harness/runner.py`
  - Move the existing `run_agent(spec)` wrapper from `src/loushang/agent/harness/runner.py`.
- Modify `src/loushang/agent/agent.py`
  - Remove imports from `loushang.agent.harness`.
  - Import `run_agent_loop` and `run_agent_loop_continue`.
  - Remove `_raise_failed_run()`.
  - Make `_run_prompt_messages()` and `_run_continuation()` call loop functions directly.
- Modify `src/loushang/agent/harness/__init__.py`
  - Convert to a temporary compatibility re-export from `loushang.harness` in the same task that creates `loushang.harness`.
  - Do not allow any intermediate commit with two independent `AgentRunSpec` / `AgentRunResult` definitions.
- Modify `src/loushang/agent/harness/runner.py` and `src/loushang/agent/harness/types.py`
  - Convert to thin compatibility modules re-exporting from `loushang.harness`.
  - Do not keep independent implementations.
- Delete `tests/agent/test_agent_harness.py`
  - New canonical tests should live in `tests/harness/test_agent_run.py`.
  - Legacy import compatibility coverage should live only in `tests/agent/test_agent_harness_compat.py`.
- Modify `tests/agent/test_agent_runtime.py`
  - Remove implementation-detail tests asserting that `Agent` routes through harness.
  - Keep behavior tests for prompt, continue, queues, listener ordering, abort, and state folding.
- Extend `tests/architecture/test_import_boundaries.py`
  - Lock that `loushang.agent` does not import `loushang.harness`.
  - Lock that `loushang.harness` does not import `loushang.ai`, `loushang.agent.agent`, `loushang.agent.harness`, `loushang.coding`, `loushang.tui`, `loushang.work`, or `loushang.method`.
  - Treat `src/loushang/agent/harness/*` as the only temporary compatibility exception.
- Modify docs:
  - `docs/internals/architecture/agent/ARD-001-agent-harness-and-product-adapters.md`
  - `docs/internals/architecture/agent/README.md`
  - `docs/internals/architecture/agent/agent-harness-module-ownership-inventory.md`
  - Optional: update references in `docs/internals/architecture/subsystem.md`, `docs/internals/architecture/coding/ARD-001-coding-product-boundaries.md`, and method README if they state `loushang.agent.harness`.

---

### Task 1: Add Canonical Top-Level Harness Package

**Files:**
- Create: `src/loushang/harness/__init__.py`
- Create: `src/loushang/harness/types.py`
- Create: `src/loushang/harness/runner.py`
- Modify: `src/loushang/agent/harness/__init__.py`
- Modify: `src/loushang/agent/harness/types.py`
- Modify: `src/loushang/agent/harness/runner.py`
- Delete: `tests/agent/test_agent_harness.py`
- Test: `tests/harness/test_agent_run.py`
- Test: `tests/agent/test_agent_harness_compat.py`

- [ ] **Step 1: Write the failing canonical harness tests**

Create `tests/harness/test_agent_run.py` by moving the canonical behavior coverage from `tests/agent/test_agent_harness.py`, changing imports to:

```python
from loushang.harness import AgentRunSpec, run_agent
```

Keep these test cases:

```python
def test_run_agent_collects_events_and_new_messages_for_prompt_run() -> None: ...
def test_run_agent_forwards_events_to_external_sink() -> None: ...
def test_run_agent_can_continue_from_existing_context() -> None: ...
def test_run_agent_returns_failed_result_when_loop_raises() -> None: ...
```

Then delete `tests/agent/test_agent_harness.py`. Use the new `tests/agent/test_agent_harness_compat.py` file for legacy import coverage. Do not keep canonical behavior tests under `tests/agent`.

- [ ] **Step 2: Run the new test and confirm import failure**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/harness/test_agent_run.py -q
```

Expected: FAIL because `loushang.harness` does not exist.

- [ ] **Step 3: Add `src/loushang/harness/types.py`**

Move the existing definitions without changing field names:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from loushang.agent.types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    StreamFn,
)

AgentRunMode = Literal["prompt", "continue"]
AgentRunStatus = Literal["completed", "failed"]
AgentEventSink = Callable[[AgentEvent], Awaitable[None] | None]


@dataclass(frozen=True, kw_only=True)
class AgentRunSpec:
    context: AgentContext
    config: AgentLoopConfig
    prompts: tuple[AgentMessage, ...] = ()
    mode: AgentRunMode = "prompt"
    signal: object | None = None
    stream_fn: StreamFn | None = None
    event_sink: AgentEventSink | None = None


@dataclass(frozen=True)
class AgentRunResult:
    status: AgentRunStatus
    new_messages: tuple[AgentMessage, ...] = ()
    events: tuple[AgentEvent, ...] = ()
    stop_reason: str | None = None
    error: Exception | None = None
```

- [ ] **Step 4: Add `src/loushang/harness/runner.py`**

Move the existing runner implementation, updating imports:

```python
from __future__ import annotations

from loushang.agent.agent_loop import run_agent_loop, run_agent_loop_continue
from loushang.agent.types import AgentEvent, AgentMessage
from loushang.harness.types import AgentRunResult, AgentRunSpec


async def run_agent(spec: AgentRunSpec) -> AgentRunResult:
    events: list[AgentEvent] = []

    async def emit(event: AgentEvent) -> None:
        events.append(event)
        if spec.event_sink is not None:
            result = spec.event_sink(event)
            if result is not None:
                await result

    try:
        if spec.mode == "continue":
            new_messages = await run_agent_loop_continue(
                spec.context,
                spec.config,
                emit,
                signal=spec.signal,
                stream_fn=spec.stream_fn,
            )
        else:
            new_messages = await run_agent_loop(
                list(spec.prompts),
                spec.context,
                spec.config,
                emit,
                signal=spec.signal,
                stream_fn=spec.stream_fn,
            )
    except Exception as error:  # noqa: BLE001 - harness returns failed run results for product adapters.
        return AgentRunResult(status="failed", events=tuple(events), error=error)

    return AgentRunResult(
        status="completed",
        new_messages=tuple(new_messages),
        events=tuple(events),
        stop_reason=_stop_reason(new_messages),
    )


def _stop_reason(messages: list[AgentMessage]) -> str | None:
    for message in reversed(messages):
        stop_reason = getattr(message, "stop_reason", None)
        if isinstance(stop_reason, str):
            return stop_reason
    return None
```

- [ ] **Step 5: Add `src/loushang/harness/__init__.py`**

```python
from loushang.harness.runner import run_agent
from loushang.harness.types import (
    AgentEventSink,
    AgentRunMode,
    AgentRunResult,
    AgentRunSpec,
    AgentRunStatus,
)

__all__ = [
    "AgentEventSink",
    "AgentRunMode",
    "AgentRunResult",
    "AgentRunSpec",
    "AgentRunStatus",
    "run_agent",
]
```

- [ ] **Step 6: Add legacy compatibility tests before the first commit**

Create `tests/agent/test_agent_harness_compat.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path


def test_legacy_agent_harness_imports_reexport_top_level_harness() -> None:
    from loushang.agent.harness import AgentRunResult as LegacyResult
    from loushang.agent.harness import AgentRunSpec as LegacySpec
    from loushang.agent.harness import run_agent as legacy_run_agent
    from loushang.agent.harness.runner import run_agent as legacy_runner_run_agent
    from loushang.agent.harness.types import AgentRunResult as LegacyTypesResult
    from loushang.agent.harness.types import AgentRunSpec as LegacyTypesSpec
    from loushang.harness import AgentRunResult, AgentRunSpec, run_agent

    assert LegacySpec is AgentRunSpec
    assert LegacyResult is AgentRunResult
    assert legacy_run_agent is run_agent
    assert LegacyTypesSpec is AgentRunSpec
    assert LegacyTypesResult is AgentRunResult
    assert legacy_runner_run_agent is run_agent


def test_agent_run_contract_has_single_source_definition() -> None:
    definitions: list[str] = []
    for path in Path("src/loushang").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in {"AgentRunSpec", "AgentRunResult"}:
                definitions.append(f"{path.as_posix()}:{node.name}")

    assert definitions == [
        "src/loushang/harness/types.py:AgentRunSpec",
        "src/loushang/harness/types.py:AgentRunResult",
    ]
```

- [ ] **Step 7: Convert legacy `src/loushang/agent/harness/types.py` to a re-export**

```python
from loushang.harness.types import (
    AgentEventSink,
    AgentRunMode,
    AgentRunResult,
    AgentRunSpec,
    AgentRunStatus,
)

__all__ = [
    "AgentEventSink",
    "AgentRunMode",
    "AgentRunResult",
    "AgentRunSpec",
    "AgentRunStatus",
]
```

- [ ] **Step 8: Convert legacy `src/loushang/agent/harness/runner.py` to a re-export**

```python
from loushang.harness.runner import run_agent

__all__ = ["run_agent"]
```

- [ ] **Step 9: Convert legacy `src/loushang/agent/harness/__init__.py` to a re-export**

Do not add a runtime `DeprecationWarning` in this first migration PR. The compatibility package exists to keep existing downstream imports quiet while code is moved; the deprecation is enforced by docs, import-boundary tests, and the follow-up deletion criteria below.

```python
from loushang.harness import (
    AgentEventSink,
    AgentRunMode,
    AgentRunResult,
    AgentRunSpec,
    AgentRunStatus,
    run_agent,
)

__all__ = [
    "AgentEventSink",
    "AgentRunMode",
    "AgentRunResult",
    "AgentRunSpec",
    "AgentRunStatus",
    "run_agent",
]
```

- [ ] **Step 10: Run canonical and compatibility harness tests**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/harness/test_agent_run.py tests/agent/test_agent_harness_compat.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/loushang/harness src/loushang/agent/harness tests/harness/test_agent_run.py tests/agent/test_agent_harness_compat.py
git add -A tests/agent/test_agent_harness.py
git commit -m "refactor(harness): add top-level prepared agent run contract"
```

---

### Task 2: Make `Agent` Independent From Harness

**Files:**
- Modify: `src/loushang/agent/agent.py`
- Modify: `tests/agent/test_agent_runtime.py`
- Test: `tests/agent/test_agent_runtime.py`

- [ ] **Step 1: Remove implementation-detail runtime tests**

Remove `test_prompt_routes_execution_through_harness` from `tests/agent/test_agent_runtime.py`; it locks an implementation detail that should no longer be true.

Keep behavior coverage by ensuring existing tests still assert:

```python
def test_prompt_updates_state_and_notifies_subscribers() -> None: ...
def test_continue_prefers_queued_steering_then_follow_up_when_last_message_is_assistant() -> None: ...
def test_state_folding_tracks_tool_execution_and_error_message() -> None: ...
def test_abort_cancels_non_cooperative_stream_prompt() -> None: ...
```

Do not add an optional local import check here. The required package boundary is locked in Task 3 by `tests/architecture/test_import_boundaries.py`.

- [ ] **Step 2: Run focused runtime tests as behavior safety**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/agent/test_agent_runtime.py -q
```

Expected: PASS or FAIL depending on whether only behavior tests remain. This step is a behavior safety check, not the dependency-boundary failure gate. Task 3 is the required failure gate for `Agent` no longer importing harness.

- [ ] **Step 3: Update imports in `src/loushang/agent/agent.py`**

Replace:

```python
from loushang.agent.harness import AgentRunResult, AgentRunSpec, run_agent
```

with:

```python
from loushang.agent.agent_loop import run_agent_loop, run_agent_loop_continue
```

Delete `_raise_failed_run()`.

- [ ] **Step 4: Update `_run_prompt_messages()`**

Replace the `run_agent(AgentRunSpec(...))` call with:

```python
async def _run_prompt_messages(self, messages: list[AgentMessage], skip_initial_steering_poll: bool = False) -> None:
    async def executor(signal: AbortSignal) -> None:
        await run_agent_loop(
            list(messages),
            self._create_context_snapshot(),
            self._create_loop_config(skip_initial_steering_poll=skip_initial_steering_poll),
            self._process_event,
            signal=signal,
            stream_fn=self.stream_fn,
        )

    await self._run_with_lifecycle(executor)
```

- [ ] **Step 5: Update `_run_continuation()`**

Replace the `run_agent(AgentRunSpec(mode="continue", ...))` call with:

```python
async def _run_continuation(self) -> None:
    async def executor(signal: AbortSignal) -> None:
        await run_agent_loop_continue(
            self._create_context_snapshot(),
            self._create_loop_config(),
            self._process_event,
            signal=signal,
            stream_fn=self.stream_fn,
        )

    await self._run_with_lifecycle(executor)
```

- [ ] **Step 6: Run focused runtime tests**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/agent/test_agent_runtime.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/agent/agent.py tests/agent/test_agent_runtime.py
git commit -m "refactor(agent): decouple Agent from harness runner"
```

---

### Task 3: Lock Import Boundaries

**Files:**
- Modify: `tests/architecture/test_import_boundaries.py`
- Test: `tests/architecture/test_import_boundaries.py`

- [ ] **Step 1: Write import boundary tests**

Extend the existing `tests/architecture/test_import_boundaries.py`. Do not create a parallel boundary-test file.

Update the `agent` boundary to forbid `loushang.harness` while allowing only the temporary legacy shim files:

```python
ImportBoundary(
    name="agent",
    root=Path("src/loushang/agent"),
    forbidden_prefixes=(
        "loushang.coding",
        "loushang.harness",
        "loushang.method",
        "loushang.tui",
        "loushang.work",
    ),
    allowed_paths=frozenset(
        {
            "src/loushang/agent/harness/__init__.py",
            "src/loushang/agent/harness/runner.py",
            "src/loushang/agent/harness/types.py",
        }
    ),
)
```

Keep or update the existing `agent.harness` boundary so it only acts as a compatibility exception and still forbids product packages.

Add a new top-level harness boundary:

```python
ImportBoundary(
    name="harness",
    root=Path("src/loushang/harness"),
    forbidden_prefixes=(
        "loushang.ai",
        "loushang.agent.agent",
        "loushang.agent.harness",
        "loushang.coding",
        "loushang.method",
        "loushang.tui",
        "loushang.work",
    ),
)
```

This makes the compatibility rule explicit: `src/loushang/agent/harness/*` is the only allowed `loushang.agent -> loushang.harness` import path during the deprecation window. It also keeps `loushang.harness` from depending directly on `loushang.ai`, the high-level `Agent` facade, or the legacy shim package; harness should use `loushang.agent.agent_loop` and `loushang.agent.types` instead.

- [ ] **Step 2: Run boundary tests**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/architecture/test_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/architecture/test_import_boundaries.py
git commit -m "test: lock agent and harness import boundaries"
```

---

### Task 4: Update Architecture Docs

**Files:**
- Modify: `docs/internals/architecture/agent/ARD-001-agent-harness-and-product-adapters.md`
- Modify: `docs/internals/architecture/agent/README.md`
- Modify: `docs/internals/architecture/agent/agent-harness-module-ownership-inventory.md`
- Optional modify:
  - `docs/internals/architecture/subsystem.md`
  - `docs/internals/architecture/coding/ARD-001-coding-product-boundaries.md`
  - `docs/internals/architecture/method/README.md`
- Test: documentation grep / boundary tests

- [ ] **Step 1: Update ARD terminology**

Change the accepted architecture to say:

```text
`loushang.harness` owns the prepared agent run contract shared by product
adapters. It depends on `loushang.agent`; `loushang.agent` must not depend on
`loushang.harness`.
```

Also explain that:

```text
`AgentRunSpec`, `AgentRunResult`, and `run_agent()` are not duplicated as a
second HarnessRunSpec layer. They are the single prepared-run contract.
```

- [ ] **Step 2: Update module ownership inventory**

Document:

```text
src/loushang/agent/harness is a deprecated temporary compatibility re-export.
New code should import from loushang.harness.
```

- [ ] **Step 3: Update references from `loushang.agent.harness` to `loushang.harness`**

Use `rg` to find references:

```bash
rg --type md -n "loushang\\.agent\\.harness|agent\\.harness" docs/internals/architecture
```

Update active architecture docs. Draft documents may either be updated or explicitly marked historical if the project keeps them as snapshots.

- [ ] **Step 4: Run doc-focused grep**

Run:

```bash
rg --type md -n "loushang\\.agent\\.harness|agent\\.harness" docs/internals/architecture/agent docs/internals/architecture/coding docs/internals/architecture/method docs/internals/architecture/subsystem.md
```

Expected: no active-doc references except explicit compatibility or historical notes.

- [ ] **Step 5: Commit**

```bash
git add docs/internals/architecture
git commit -m "docs: align harness ownership boundary"
```

---

### Task 5: Final Verification

**Files:**
- No source edits unless failures reveal missed references.

- [ ] **Step 1: Run focused agent and harness tests**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/harness/test_agent_run.py tests/agent/test_agent_runtime.py tests/agent/test_agent_harness_compat.py tests/architecture/test_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 2: Run coding session smoke tests**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests/coding/test_agent_session.py tests/coding/test_agent_session_runtime.py -q
```

Expected: PASS. These guard that keeping `Agent` in `loushang.agent` did not regress coding.

- [ ] **Step 3: Run lint for touched areas**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev ruff check src/loushang/agent src/loushang/harness tests/agent tests/harness tests/architecture/test_import_boundaries.py
```

Expected: PASS.

- [ ] **Step 4: Run broader tests if focused checks pass**

Run:

```bash
uv --cache-dir /tmp/uv-cache run --extra dev pytest tests -q
```

Expected: PASS. If failures remain, only call them pre-existing after reproducing them on unchanged `origin/main` or from a captured baseline before this branch's edits; otherwise treat them as regressions until proven unrelated. Report any unrelated pre-existing failures with exact failing tests.

- [ ] **Step 5: Commit any final fixes**

```bash
git add src/loushang/agent src/loushang/harness tests docs
git commit -m "refactor: finalize top-level harness boundary"
```

---

## Follow-Up PRs

Do not include these in the first migration PR:

- Delete the temporary `loushang.agent.harness` compatibility package after all internal imports and tests have moved to `loushang.harness`, downstream compatibility risk has been accepted for the next release, and `rg -n "loushang\\.agent\\.harness|agent\\.harness" src tests docs` only finds historical/deletion notes.
- Add `HarnessSession` protocol.
- Add resource contracts for skills, prompt templates, and context resources.
- Add product-neutral hook objects for before-agent-start, context transform, provider request/response, and tool gate.
- Start coding adapter migration from `AgentSession(agent=Agent(...))` to a harness-backed path.

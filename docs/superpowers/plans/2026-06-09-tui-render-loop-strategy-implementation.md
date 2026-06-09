# TUI RenderLoop Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `RenderLoop.plan()` into an explicit, stateless strategy pipeline while preserving existing terminal behavior and diagnostics.

**Architecture:** Build an eager `RenderPlanContext` with frame facts, expose loop state through a narrow `RenderPlanRuntime`, and migrate existing render-path branches into stateless strategies ordered by `DEFAULT_STRATEGY_ORDER`. Existing operation helpers stay in `render_loop.py` unless moving them clearly reduces coupling.

**Tech Stack:** Python 3.11+, dataclasses, pytest, existing `loushang.tui` fake terminal/playback tests, `uv --cache-dir .uv-cache run --extra dev pytest`.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-09-tui-render-loop-strategy-design.md`
- Current implementation: `src/loushang/tui/render_loop.py`
- Core render tests: `tests/tui/test_render_loop.py`
- Long-session perf probes: `tests/coding/test_native_coding_tui_perf_probe.py`

## File Structure

- Modify `src/loushang/tui/render_loop.py`
  - Owns `RenderLoop`, `RenderPlanContext`, `RenderPlanRuntime`, strategy kinds, strategy registry, and extracted strategies.
  - Keep this in one file for the first refactor to minimize import churn. Split later only if the strategy section becomes difficult to navigate.
- Modify `tests/tui/test_render_loop.py`
  - Add strategy order and priority regression tests.
  - Keep existing operation-class tests as behavior coverage.
- Modify `tests/coding/test_native_coding_tui_perf_probe.py`
  - Tighten active-window bounded render-loop assertions.
- Create `docs/internals/architecture/tui/native-terminal-core/render-framework/render-loop.md`
  - Product-neutral render-loop strategy and operation-class documentation.
- Create `docs/internals/architecture/tui/native-terminal-core/render-framework/managed-viewport.md`
  - Managed viewport repaint, shrink, and protected append admission documentation.

## Task 1: Extract RenderPlanContext Without Strategy Dispatch

**Files:**
- Modify: `src/loushang/tui/render_loop.py`
- Test: `tests/tui/test_render_loop.py`

- [ ] **Step 1: Add a failing context contract test**

Add a test near the render-loop diagnostics tests:

```python
def test_render_plan_context_carries_cursor_and_diff_facts() -> None:
    root = StaticRoot(("alpha",))
    loop = RenderLoop(root)
    size = TerminalSize(columns=20, rows=5)
    first = loop.plan(size)
    loop.commit(first, size=size)

    root.lines = ("alpha", "beta" + CURSOR_MARKER)
    context = loop._build_plan_context(size)

    assert context.raw_current_lines == ("alpha", "beta")
    assert context.current_lines == ("alpha", "beta")
    assert context.declared_cursor == CursorDeclaration(row=1, column=4)
    assert context.cursor == CursorDeclaration(row=1, column=4)
    assert context.changed_range == (1, 1)
    assert context.first_changed == 1
    assert context.last_changed == 1
    assert context.appended_lines == 1
    assert context.append_start == 1
```

Add `CursorDeclaration` to the existing `loushang.tui` imports in
`tests/tui/test_render_loop.py`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py::test_render_plan_context_carries_cursor_and_diff_facts -q
```

Expected: FAIL because `RenderLoop._build_plan_context` does not exist yet.

- [ ] **Step 3: Add internal dataclasses**

In `src/loushang/tui/render_loop.py`, add:

```python
@dataclass(frozen=True, slots=True)
class RenderPlanContext:
    size: TerminalSize
    result: RenderResult
    raw_current_lines: tuple[str, ...]
    current_lines: tuple[str, ...]
    previous_lines: tuple[str, ...]
    previous_size: TerminalSize | None
    declared_cursor: CursorDeclaration | None
    cursor: CursorDeclaration
    changed_range: tuple[int, int] | None
    first_changed: int | None
    last_changed: int | None
    appended_lines: int
    append_start: int | None
    viewport_top: int
    differential_viewport_top: int
    width_changed: bool
    height_changed: bool
    previous_kitty_delete_sequences: tuple[str, ...]
```

Add `RenderLoop._build_plan_context(size)` and move current local frame fact construction from `plan()` into it. Preserve `self._planned_raw_lines = raw_current_lines`.

Use `first_changed = None`, `last_changed = None`, and `append_start = None` when `changed_range is None`. Compute `differential_viewport_top` eagerly using the existing `_differential_viewport_top()` helper.

- [ ] **Step 4: Rewrite `plan()` to use context fields only**

Keep all existing branch logic in `plan()`, but replace local variables with `context.<field>`. Do not introduce strategy dispatch yet.

- [ ] **Step 5: Run focused render-loop tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/loushang/tui/render_loop.py tests/tui/test_render_loop.py
git commit -m "refactor(tui): extract render plan context"
```

## Task 2: Add Strategy Kind, Runtime Facade, and Order Tests

**Files:**
- Modify: `src/loushang/tui/render_loop.py`
- Modify: `tests/tui/test_render_loop.py`

- [ ] **Step 1: Write failing strategy order test**

Add:

```python
def test_default_render_strategy_order_matches_design() -> None:
    assert DEFAULT_STRATEGY_ORDER == (
        RenderPlanStrategyKind.FIRST_RENDER,
        RenderPlanStrategyKind.TRANSCRIPT_WINDOW_TRIMMED_RESET,
        RenderPlanStrategyKind.BASELINE_RESET,
        RenderPlanStrategyKind.RESIZE_REPAINT,
        RenderPlanStrategyKind.UNSAFE_VIEWPORT,
        RenderPlanStrategyKind.NO_CHANGE,
        RenderPlanStrategyKind.APPEND,
        RenderPlanStrategyKind.PROTECTED_APPEND,
        RenderPlanStrategyKind.SHRINK_VIEWPORT_REPAINT,
        RenderPlanStrategyKind.SHRINK_CLEAR,
        RenderPlanStrategyKind.CHANGED_ABOVE_VIEWPORT,
        RenderPlanStrategyKind.CHANGED_RANGE,
    )
```

- [ ] **Step 2: Run order test and verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py::test_default_render_strategy_order_matches_design -q
```

Expected: FAIL because `RenderPlanStrategyKind` and `DEFAULT_STRATEGY_ORDER` do not exist.

- [ ] **Step 3: Add enum, protocol, runtime facade, and registry skeleton**

In `render_loop.py`:

```python
class RenderPlanStrategyKind(Enum): ...

DEFAULT_STRATEGY_ORDER = (...)

class RenderPlanStrategy(Protocol): ...

@dataclass(frozen=True, slots=True)
class RenderPlanRuntime:
    previous_viewport_top: int
    previous_cursor_row: int
    previous_cursor_column: int
    hardware_cursor_row: int
    hardware_cursor_column: int
    working_area_high_water_mark: int
    termux_session: bool
    clear_scrollback_policy: ClearScrollbackPolicy
    baseline_reset_reason: str | None
    unsafe_viewport_reason: str | None
```

Add `RenderLoop._plan_runtime()`.

Do not change `plan()` dispatch yet.

- [ ] **Step 4: Run order test and full render-loop tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/loushang/tui/render_loop.py tests/tui/test_render_loop.py
git commit -m "refactor(tui): declare render plan strategy order"
```

## Task 3: Extract Simple Strategies

**Files:**
- Modify: `src/loushang/tui/render_loop.py`
- Modify: `tests/tui/test_render_loop.py`

- [ ] **Step 1: Write priority tests for simple strategies**

Add tests:

```python
def test_resize_repaint_precedes_changed_range_strategy() -> None:
    root = MutableRoot(["one"])
    loop = RenderLoop(root)
    first = loop.plan(TerminalSize(columns=20, rows=5))
    loop.commit(first, size=TerminalSize(columns=20, rows=5))

    root.lines = ["two"]
    step = loop.plan(TerminalSize(columns=30, rows=5))

    assert step.operation_class == "resize_repaint"


def test_unsafe_viewport_precedes_append_strategy() -> None:
    root = MutableRoot(["one"])
    loop = RenderLoop(root)
    first = loop.plan(TerminalSize(columns=20, rows=5))
    loop.commit(first, size=TerminalSize(columns=20, rows=5))

    root.lines = ["one", "two"]
    loop.mark_viewport_unsafe("external_stdout")
    step = loop.plan(TerminalSize(columns=20, rows=5))

    assert step.operation_class == "recovery_repaint"
    assert step.repaint_reason == "external_stdout"
```

Use existing mutable renderable helpers if present.

- [ ] **Step 2: Run priority tests and verify RED or existing PASS**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py::test_resize_repaint_precedes_changed_range_strategy tests/tui/test_render_loop.py::test_unsafe_viewport_precedes_append_strategy -q
```

Expected: These may PASS on existing code. If they pass, keep them as characterization tests before refactor.

- [ ] **Step 3: Implement simple strategy classes**

Extract these classes:

- `FirstRenderStrategy`
- `ResizeRepaintStrategy`
- `UnsafeViewportStrategy`
- `NoChangeStrategy`

Each class must be stateless and call existing operation/diagnostic helpers through minimal runtime/loop builder methods. If passing builders through `RenderPlanRuntime` becomes awkward, keep private helper calls in `RenderLoop` and make strategy `plan()` return an internal `RenderPlanDecision` for the loop to materialize. Choose the smaller implementation that preserves the spec boundary.

- [ ] **Step 4: Add dispatch for extracted strategies only**

`RenderLoop.plan()` should:

1. Build context and runtime.
2. Try extracted strategies in order.
3. Fall through to the existing inline baseline reset and complex diff code.

Do not extract baseline reset in this task.

- [ ] **Step 5: Run render-loop tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/loushang/tui/render_loop.py tests/tui/test_render_loop.py
git commit -m "refactor(tui): extract simple render plan strategies"
```

## Task 4: Extract Baseline Reset and Complex Diff Strategies

**Files:**
- Modify: `src/loushang/tui/render_loop.py`
- Modify: `tests/tui/test_render_loop.py`

- [ ] **Step 1: Write baseline reset priority tests**

Add:

```python
def test_transcript_window_trimmed_reset_precedes_resize_repaint() -> None:
    root = MutableRoot(["one"])
    loop = RenderLoop(root)
    first = loop.plan(TerminalSize(columns=20, rows=5))
    loop.commit(first, size=TerminalSize(columns=20, rows=5))

    root.lines = ["one", "two"]
    loop.reset_baseline("transcript_window_trimmed:active_line_budget")
    step = loop.plan(TerminalSize(columns=30, rows=5))

    assert step.operation_class == "managed_viewport_repaint"
    assert step.repaint_reason == "transcript_window_trimmed:active_line_budget"


def test_ordinary_baseline_reset_precedes_resize_repaint() -> None:
    root = MutableRoot(["one"])
    loop = RenderLoop(root)
    first = loop.plan(TerminalSize(columns=20, rows=5))
    loop.commit(first, size=TerminalSize(columns=20, rows=5))

    root.lines = ["one", "two"]
    loop.reset_baseline("transcript_window_replaced:resume")
    step = loop.plan(TerminalSize(columns=30, rows=5))

    assert step.operation_class == "baseline_repaint"
    assert step.repaint_reason == "transcript_window_replaced:resume"
```

- [ ] **Step 2: Run tests and verify characterization**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py::test_transcript_window_trimmed_reset_precedes_resize_repaint tests/tui/test_render_loop.py::test_ordinary_baseline_reset_precedes_resize_repaint -q
```

Expected: PASS on existing code or after minor helper setup.

- [ ] **Step 3: Extract remaining strategies**

Extract:

- `TranscriptWindowTrimmedResetStrategy`
- `BaselineResetStrategy`
- `AppendStrategy`
- `ProtectedAppendStrategy`
- `ShrinkViewportRepaintStrategy`
- `ShrinkClearStrategy`
- `ChangedAboveViewportStrategy`
- `ChangedRangeStrategy`

Then make `RenderLoop.plan()` dispatch through `DEFAULT_STRATEGY_ORDER` without inline branch leftovers.

Do not include `FallbackRepaintStrategy` in default order.

- [ ] **Step 4: Run full render-loop tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/loushang/tui/render_loop.py tests/tui/test_render_loop.py
git commit -m "refactor(tui): route render planning through strategies"
```

## Task 5: Tighten Long-Session Performance Guards

**Files:**
- Modify: `tests/coding/test_native_coding_tui_perf_probe.py`

- [ ] **Step 1: Write bounded active-window assertion**

In `test_long_transcript_probe_stays_bounded_after_active_window_trim`, add:

```python
assert second_metrics.render_loop_logical_line_count == first_metrics.render_loop_logical_line_count
```

If current bottom-frame behavior makes exact equality too brittle, assert:

```python
assert second_metrics.render_loop_logical_line_count <= first_metrics.render_loop_logical_line_count + 5
```

Prefer equality unless the test shows a legitimate small bottom-frame growth.

- [ ] **Step 2: Run perf probe**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_native_coding_tui_perf_probe.py -q
```

Expected: PASS.

- [ ] **Step 3: Run focused TUI and perf tests together**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py tests/coding/test_native_coding_tui_perf_probe.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 5**

```bash
git add tests/coding/test_native_coding_tui_perf_probe.py
git commit -m "test(tui): tighten active window render planning guard"
```

## Task 6: Add Render Framework Docs

**Files:**
- Create: `docs/internals/architecture/tui/native-terminal-core/render-framework/render-loop.md`
- Create: `docs/internals/architecture/tui/native-terminal-core/render-framework/managed-viewport.md`
- Modify: `docs/internals/architecture/tui/native-terminal-core/render-framework/README.md`

- [ ] **Step 1: Create `render-loop.md`**

Include:

- RenderLoop responsibilities
- frame construction
- strategy ordering table
- Decision Cheat Sheet from the spec
- commit/failure semantics
- cursor positioning model
- Kitty image cleanup interaction

- [ ] **Step 2: Create `managed-viewport.md`**

Include:

- viewport top and previous viewport top
- unsafe partial diff cases
- protected append admission rules
- managed viewport repaint triggers
- shrink clear behavior
- resize repaint versus recovery repaint policy
- internal versus external repaint triggers

- [ ] **Step 3: Update render framework README**

Change `render-loop.md` and `managed-viewport.md` entries from inventory-only to available specs if the README format supports it. Keep unrelated inventory entries unchanged.

- [ ] **Step 4: Run documentation sanity checks**

Run:

```bash
rg -n "TO""DO|TB""D|FIX""ME|XX""X" docs/internals/architecture/tui/native-terminal-core/render-framework docs/superpowers/specs/2026-06-09-tui-render-loop-strategy-design.md
git diff --check
```

Expected: no placeholder matches and no whitespace errors.

- [ ] **Step 5: Commit Task 6**

```bash
git add docs/internals/architecture/tui/native-terminal-core/render-framework/render-loop.md docs/internals/architecture/tui/native-terminal-core/render-framework/managed-viewport.md docs/internals/architecture/tui/native-terminal-core/render-framework/README.md
git commit -m "docs(tui): document render planning strategies"
```

## Task 7: Final Verification

**Files:**
- No planned edits unless verification exposes issues.

- [ ] **Step 1: Run focused verification**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_loop.py tests/coding/test_native_coding_tui_perf_probe.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader TUI tests if focused tests pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git status --short --branch
git log --oneline -8
```

Expected: working tree clean after commits; branch contains the spec, plan, and implementation commits.

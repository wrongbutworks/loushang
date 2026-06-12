# TUI Widget Examples UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish TUI widget examples `44-50` into clearer, scenario-based mini applications with deterministic playback-like tests for initial, navigation, and state-change frames.

**Architecture:** Keep all behavior local to examples and tests. Add a small private playback snapshot helper in tests to drive each example through `TuiRuntime + FakeTerminalPort`; then update each example's layout and input handling to match the approved spec without introducing new public layout APIs or runtime changes.

**Tech Stack:** Python 3.11+, dataclasses with slots, existing `loushang.tui` widgets, `RenderConstraints`, `TuiRuntime`, `FakeTerminalPort`, `RenderLoop`, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-12-tui-widget-examples-ux-polish-design.md`
- Existing example baseline:
  - `examples/tui/43_widgets_foundation.py`
  - `tests/tui/test_widgets_foundation.py`
- Examples to polish:
  - `examples/tui/44_widgets_small_controls.py`
  - `examples/tui/45_widgets_light_controls.py`
  - `examples/tui/46_widgets_table.py`
  - `examples/tui/47_widgets_textarea.py`
  - `examples/tui/48_widgets_question_dialog.py`
  - `examples/tui/49_widgets_tree.py`
  - `examples/tui/50_widgets_toast.py`
- Existing widget tests:
  - `tests/tui/test_widgets_small_controls.py`
  - `tests/tui/test_widgets_light_controls.py`
  - `tests/tui/test_widgets_table.py`
  - `tests/tui/test_widgets_textarea.py`
  - `tests/tui/test_widgets_question_dialog.py`
  - `tests/tui/test_widgets_tree.py`
  - `tests/tui/test_widgets_toast.py`

## File Structure

Create:

- `tests/tui/widget_example_playback.py`
  - Private test helper for loading examples with `runpy`, rendering with
    `TuiRuntime + FakeTerminalPort`, sending `InputEvent` values through the
    example `Tui`, and returning stripped visible lines plus cursor/operation
    metadata.

Modify:

- `examples/tui/44_widgets_small_controls.py`
  - Scenario: Indexing Job.
  - Keep `Toolbar` as the only focusable region.
- `tests/tui/test_widgets_small_controls.py`
  - Add playback-like example snapshots for initial, toolbar navigation, and
    activation.
- `examples/tui/45_widgets_light_controls.py`
  - Scenario: View Switcher.
  - Add local two-region focus state for `views` and `actions`.
- `tests/tui/test_widgets_light_controls.py`
  - Add playback-like snapshots proving only one focus marker is visible.
- `examples/tui/46_widgets_table.py`
  - Scenario: Job Queue.
  - Add selected row detail.
- `tests/tui/test_widgets_table.py`
  - Add playback-like snapshots for row navigation and activation.
- `examples/tui/47_widgets_textarea.py`
  - Scenario: Release Note Draft.
  - Add title metadata and line-count status.
- `tests/tui/test_widgets_textarea.py`
  - Add playback-like snapshots for initial, edit, newline, and second edit.
- `examples/tui/48_widgets_question_dialog.py`
  - Scenario: Notes Inbox.
  - Add Recent context and Status row.
- `tests/tui/test_widgets_question_dialog.py`
  - Add playback-like snapshots for typing, tabbing to actions, and submit/cancel
    state changes.
- `examples/tui/49_widgets_tree.py`
  - Scenario: Project Explorer.
  - Add details projection for active/selected node.
- `tests/tui/test_widgets_tree.py`
  - Add playback-like snapshots for navigation and selection/toggle.
- `examples/tui/50_widgets_toast.py`
  - Scenario: Deploy Console.
  - Render toasts as notifications below stable console context.
- `tests/tui/test_widgets_toast.py`
  - Add playback-like snapshots for adding, dismissing, and clearing
    notifications.

Do not modify:

- `src/loushang/tui/render_loop.py`
- `src/loushang/tui/framework.py`
- `src/loushang/tui/input.py`
- `src/loushang/tui/runtime.py`
- Public widget APIs, unless a test exposes a real widget bug. Example polish
  should remain example-local.

---

### Task 1: Add Shared Playback Snapshot Helper

**Files:**
- Create: `tests/tui/widget_example_playback.py`
- Test indirectly through: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Write a failing playback test for example 44 using the future helper**

Add to `tests/tui/test_widgets_small_controls.py`:

```python
from tests.tui.widget_example_playback import ExampleFrame, play_example


def test_widgets_small_controls_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/44_widgets_small_controls.py",
        events=(
            ("right", InputEvent(kind="key", key="right")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert [frame.label for frame in frames] == ["initial", "right", "enter"]
    assert all(isinstance(frame, ExampleFrame) for frame in frames)
    assert frames[0].lines[:11] == (
        "Indexing Job  [beta]  (ready)",
        "",
        "Progress      Indexing [#####-------] 42%",
        "",
        "Details",
        "Model         Kimi",
        "Mode          safe  current",
        "Queue         3 pending",
        "",
        "Actions       > [Refresh]  [Cancel]",
        "Status        Ready",
    )
    assert "Actions       [Refresh]  > [Cancel]" in frames[1].lines
    assert "Status        Cancelled" in frames[2].lines
```

The `ExampleFrame` import is intentionally referenced so the helper exposes a
stable data shape.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py::test_widgets_small_controls_example_playback_snapshots -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tests.tui.widget_example_playback'`.

- [ ] **Step 3: Create `tests/tui/widget_example_playback.py`**

Implementation:

```python
from __future__ import annotations

import runpy
from dataclasses import dataclass
from typing import Any

from loushang.tui import (
    FakeTerminalPort,
    InputEvent,
    RenderLoop,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)


@dataclass(frozen=True, slots=True)
class ExampleFrame:
    label: str
    lines: tuple[str, ...]
    cursor: tuple[int, int]
    operation_class: str | None


def play_example(
    path: str,
    *,
    events: tuple[tuple[str, InputEvent], ...] = (),
    width: int = 80,
    height: int = 20,
) -> tuple[ExampleFrame, ...]:
    namespace = runpy.run_path(path, run_name="__test__")
    tui = namespace["build_app"]()
    port = FakeTerminalPort(size=TerminalSize(columns=width, rows=height))
    runtime = TuiRuntime(render_loop=RenderLoop(tui._screen_root), terminal=port)
    frames = [_render_frame("initial", runtime)]
    for label, event in events:
        tui.handle_input(event)
        frames.append(_render_frame(label, runtime))
    return tuple(frames)


def _render_frame(label: str, runtime: TuiRuntime) -> ExampleFrame:
    step = runtime.render_now()
    return ExampleFrame(
        label=label,
        lines=tuple(
            strip_control_sequences(line).rstrip()
            for line in step.diagnostics.current_logical_lines
        ),
        cursor=(
            step.diagnostics.logical_cursor_row,
            step.diagnostics.logical_cursor_column,
        ),
        operation_class=step.diagnostics.operation_class,
    )
```

- [ ] **Step 4: Run the focused test and verify it now fails on expected screen content**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py::test_widgets_small_controls_example_playback_snapshots -q
```

Expected: FAIL because `44_widgets_small_controls.py` still renders
`Small Controls` and old layout.

- [ ] **Step 5: Commit the helper and failing test**

```bash
git add tests/tui/widget_example_playback.py tests/tui/test_widgets_small_controls.py
git commit -m "test(tui): add widget example playback helper"
```

---

### Task 2: Polish Example 44 - Indexing Job

**Files:**
- Modify: `examples/tui/44_widgets_small_controls.py`
- Modify: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Implement example-local row helper**

Add near the top of `examples/tui/44_widgets_small_controls.py`:

```python
LABEL_WIDTH = 14


def _field(label: str, value: str, *, width: int) -> RenderLine:
    return RenderLine(truncate_to_width(f"{label:<{LABEL_WIDTH}}{value}", max_width=width, ellipsis=""))
```

- [ ] **Step 2: Rewrite `SmallControlsApp.render()` to the spec layout**

Use this shape:

```python
def render(self, constraints: RenderConstraints) -> RenderResult:
    progress = ProgressBar(value=self.progress, total=100, label="Indexing", width=12)
    progress_line = progress.render(RenderConstraints(width=max(1, constraints.width - LABEL_WIDTH), max_height=1)).lines[0].text
    toolbar_line = self.toolbar.render(RenderConstraints(width=max(1, constraints.width - LABEL_WIDTH), max_height=1)).lines
    rows = [
        RenderLine(_header(constraints.width)),
        RenderLine(""),
        _field("Progress", progress_line, width=constraints.width),
        RenderLine(""),
        RenderLine("Details"),
        _field("Model", "Kimi", width=constraints.width),
        _field("Mode", "safe  current", width=constraints.width),
        _field("Queue", "3 pending", width=constraints.width),
        RenderLine(""),
        _field("Actions", toolbar_line[0].text if toolbar_line else "", width=constraints.width),
        _field("Status", self.message, width=constraints.width),
        RenderLine(""),
        RenderLine(truncate_to_width("[left/right] action  [enter] run  [q] quit", max_width=constraints.width, ellipsis="")),
    ]
    return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)
```

Keep `_header()` rendering `Indexing Job  [beta]  (ready)`.

- [ ] **Step 3: Run the focused playback test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py::test_widgets_small_controls_example_playback_snapshots -q
```

Expected: PASS.

- [ ] **Step 4: Run all small controls tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit example 44**

```bash
git add examples/tui/44_widgets_small_controls.py tests/tui/test_widgets_small_controls.py
git commit -m "feat(tui): polish small controls example"
```

---

### Task 3: Polish Example 45 - View Switcher

**Files:**
- Modify: `examples/tui/45_widgets_light_controls.py`
- Modify: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Write failing playback test for region focus**

Add to `tests/tui/test_widgets_light_controls.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_light_controls_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/45_widgets_light_controls.py",
        events=(
            ("right", InputEvent(kind="key", key="right")),
            ("tab", InputEvent(kind="key", key="tab")),
            ("down", InputEvent(kind="key", key="down")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:12] == (
        "View Switcher",
        "",
        "Views         > [Overview]    [Logs 3]    [Settings]",
        "Activity      | Syncing",
        "",
        "Actions",
        "                Open  current view",
        "                Refresh",
        "                Archive",
        "",
        "Status        Ready",
        "",
    )
    assert "Views           [Overview]  > [Logs 3]    [Settings]" in frames[1].lines
    assert "              > Open  current view" in frames[2].lines
    assert "              > Refresh" in frames[3].lines
    assert "Status        Refreshed" in frames[4].lines
    assert sum(line.count(">") for line in frames[0].lines) == 1
    assert sum(line.count(">") for line in frames[2].lines) == 1
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py::test_widgets_light_controls_example_playback_snapshots -q
```

Expected: FAIL because current example title/layout/focus region behavior still
uses the old screen and double focus.

- [ ] **Step 3: Add region focus state to `LightControlsApp`**

Modify the dataclass:

```python
focus_region: str = "views"
```

Update `__post_init__()`:

```python
def __post_init__(self) -> None:
    FocusableMixin.__init__(self)
    self._sync_region_focus()
```

Add:

```python
def _sync_region_focus(self) -> None:
    if self.focus_region == "views":
        self.tabs.focus()
        self.menu.blur()
    else:
        self.tabs.blur()
        self.menu.focus()
```

- [ ] **Step 4: Rewrite `LightControlsApp.handle_input()`**

```python
def handle_input(self, event: Any) -> object:
    if getattr(event, "kind", "") == "key" and getattr(event, "key", "") == "tab":
        self.focus_region = "actions" if self.focus_region == "views" else "views"
        self._sync_region_focus()
        return True
    if self.focus_region == "views":
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"left", "right"}:
            result = self.tabs.handle_input(event)
            if result is not None:
                self.message = f"View: {self.tabs.value}"
                return True
        return None
    result = self.menu.handle_input(event)
    if result == "refresh":
        self.spinner_frame += 1
        self.message = "Refreshed"
        return True
    if result == "open":
        self.message = f"Opened {self.tabs.value}"
        return True
    return result
```

- [ ] **Step 5: Rewrite `render()` with labeled regions**

Use `LABEL_WIDTH = 14` and a `_field()` helper like Task 2. Render:

```text
View Switcher

Views         > [Overview]    [Logs 3]    [Settings]
Activity      | Syncing

Actions
                Open  current view
                Refresh
                Archive

Status        Ready

[tab] region  [left/right] view  [up/down] action  [enter] run  [q] quit
```

When actions are focused, `Tabs.render()` must not show a `>` and `Menu.render()`
must show a single focused action row.

- [ ] **Step 6: Run light controls tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit example 45**

```bash
git add examples/tui/45_widgets_light_controls.py tests/tui/test_widgets_light_controls.py
git commit -m "feat(tui): polish light controls example"
```

---

### Task 4: Polish Example 46 - Job Queue

**Files:**
- Modify: `examples/tui/46_widgets_table.py`
- Modify: `tests/tui/test_widgets_table.py`

- [ ] **Step 1: Write failing playback test**

Add to `tests/tui/test_widgets_table.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_table_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/46_widgets_table.py",
        events=(
            ("down", InputEvent(kind="key", key="down")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:8] == (
        "Job Queue  (3 jobs)",
        "",
        "  Job           Status                                                     Runs",
        "> Build         ready                                                        12",
        "  Deploy        blocked                                                       3",
        "  Archive       disabled                                                      0",
        "",
        "Selected      Build is ready, 12 runs",
    )
    assert "> Deploy        blocked" in "\n".join(frames[1].lines)
    assert "Selected      Deploy is blocked, 3 runs" in frames[2].lines
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py::test_widgets_table_example_playback_snapshots -q
```

Expected: FAIL because current example title/detail layout differs.

- [ ] **Step 3: Add row metadata helper to example**

Add:

```python
JOB_DETAILS = {
    "build": "Build is ready, 12 runs",
    "deploy": "Deploy is blocked, 3 runs",
    "archive": "Archive is disabled, 0 runs",
}
```

Add helper:

```python
def _selected_detail(table: Table) -> str:
    value = table.active_value
    return JOB_DETAILS.get(value, "Select a job")
```

If `Table` does not expose `active_value`, inspect `src/loushang/tui/ui_parts/widgets/table.py`
and use the existing public value/selection attribute. Do not add public API
unless necessary.

- [ ] **Step 4: Rewrite render and activation message**

Render title `Job Queue  (3 jobs)`, table, selected detail, blank row, and
footer:

```text
[up/down] row  [enter] select  [q] quit
```

On Enter result `deploy`, set selected detail to `Deploy is blocked, 3 runs`.

- [ ] **Step 5: Run table tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit example 46**

```bash
git add examples/tui/46_widgets_table.py tests/tui/test_widgets_table.py
git commit -m "feat(tui): polish table example"
```

---

### Task 5: Polish Example 47 - Release Note Draft

**Files:**
- Modify: `examples/tui/47_widgets_textarea.py`
- Modify: `tests/tui/test_widgets_textarea.py`

- [ ] **Step 1: Write failing playback test**

Add to `tests/tui/test_widgets_textarea.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_textarea_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/47_widgets_textarea.py",
        events=(
            ("type note", InputEvent(kind="text", text="Plan release")),
            ("enter", InputEvent(kind="key", key="enter")),
            ("type next", InputEvent(kind="text", text="Ship docs")),
        ),
    )

    assert frames[0].lines[:11] == (
        "Release Note Draft",
        "",
        "Title         Weekly deploy notes",
        "",
        "Notes",
        "Write notes",
        "",
        "",
        "",
        "",
        "Status        0 lines / unsaved",
    )
    assert "Status        1 line / unsaved" in frames[1].lines
    assert "Status        2 lines / unsaved" in frames[3].lines
    assert frames[0].cursor == (5, 0)
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py::test_widgets_textarea_example_playback_snapshots -q
```

Expected: FAIL because current example title/layout/status differ.

- [ ] **Step 3: Update `TextAreaApp` fields and render**

Set:

```python
notes: TextArea = field(default_factory=lambda: TextArea(placeholder="Write notes", height=5))
message: str = ""
```

Add:

```python
def _line_count(value: str) -> int:
    if not value:
        return 0
    return value.count("\n") + 1


def _line_count_label(count: int) -> str:
    return f"{count} line / unsaved" if count == 1 else f"{count} lines / unsaved"
```

Render:

```text
Release Note Draft

Title         Weekly deploy notes

Notes
textarea rows render here
Status        line count renders here

[enter] newline  [type] edit  [q] quit
```

Cursor must be offset by the rows before the textarea. Preserve the textarea
cursor from `body.cursor`.

- [ ] **Step 4: Run textarea tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit example 47**

```bash
git add examples/tui/47_widgets_textarea.py tests/tui/test_widgets_textarea.py
git commit -m "feat(tui): polish textarea example"
```

---

### Task 6: Verify Slice 1 Together

**Files:**
- No new files expected.

- [ ] **Step 1: Run targeted Slice 1 tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Ruff on Slice 1 files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/widget_example_playback.py examples/tui/44_widgets_small_controls.py examples/tui/45_widgets_light_controls.py examples/tui/46_widgets_table.py examples/tui/47_widgets_textarea.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Commit any lint-only cleanup**

Only if Step 2 required edits:

```bash
git add exact files that changed
git commit -m "style(tui): clean up widget example slice one"
```

---

### Task 7: Polish Example 48 - Notes Inbox

**Files:**
- Modify: `examples/tui/48_widgets_question_dialog.py`
- Modify: `tests/tui/test_widgets_question_dialog.py`

- [ ] **Step 1: Write failing playback test**

Add to `tests/tui/test_widgets_question_dialog.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_question_dialog_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/48_widgets_question_dialog.py",
        events=(
            ("type answer", InputEvent(kind="text", text="Cache warmup before deploy")),
            ("tab", InputEvent(kind="key", key="tab")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:15] == (
        "Notes Inbox",
        "",
        "Recent",
        "  Cache deploy checklist",
        "  Follow up on flaky test",
        "",
        "New Note",
        "Add note",
        "What should be remembered?",
        "Write a multi-line answer",
        "",
        "",
        "",
        "Enter adds a line. Ctrl+Enter submits.",
        "  [Submit]  [Cancel]",
    )
    assert "Status        Drafting" in frames[0].lines
    assert "> [Submit]  [Cancel]" in frames[2].lines
    assert "Status        Submitted: Cache warmup before deploy" in frames[3].lines
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py::test_widgets_question_dialog_example_playback_snapshots -q
```

Expected: FAIL because current example lacks inbox context and status row.

- [ ] **Step 3: Update `QuestionDialogApp` state**

Add fields:

```python
recent_notes: tuple[str, ...] = (
    "Cache deploy checklist",
    "Follow up on flaky test",
)
status: str = "Drafting"
```

Keep `dialog` focused in `__post_init__()`.

- [ ] **Step 4: Rewrite render with inbox context**

Render:

```text
Notes Inbox

Recent
  Cache deploy checklist
  Follow up on flaky test

New Note
question dialog lines render here

Status        Drafting

Escape cancels. [tab] actions  [ctrl+enter] submit  [q] quit
```

Offset `body.cursor` by the rows preceding the dialog. If cursor row would be
truncated, return `cursor=None`.

- [ ] **Step 5: Update submit/cancel handling**

In `handle_input()`:

- for `question_submit`, append submitted text to the front of `recent_notes`
  or otherwise include it in the visible recent list, set
  `status = f"Submitted: {text}"`;
- for `question_cancel`, keep recent notes unchanged and set
  `status = "Cancelled"`;
- return the original result.

- [ ] **Step 6: Run question dialog tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit example 48**

```bash
git add examples/tui/48_widgets_question_dialog.py tests/tui/test_widgets_question_dialog.py
git commit -m "feat(tui): polish question dialog example"
```

---

### Task 8: Polish Example 49 - Project Explorer

**Files:**
- Modify: `examples/tui/49_widgets_tree.py`
- Modify: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Write failing playback test**

Add to `tests/tui/test_widgets_tree.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_tree_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/49_widgets_tree.py",
        events=(
            ("down", InputEvent(kind="key", key="down")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:12] == (
        "Project Explorer",
        "",
        "Tree",
        "> - src",
        "      widgets",
        "      runtime",
        "  + tests",
        "",
        "Details",
        "Path          src",
        "Kind          folder",
        "Status        expanded",
    )
    assert "Path          src/widgets" in frames[1].lines
    assert "Status        Selected: src/widgets" in frames[2].lines
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py::test_widgets_tree_example_playback_snapshots -q
```

Expected: FAIL because current example lacks title/details layout.

- [ ] **Step 3: Inspect `TreeView` public active/selected API**

Run:

```bash
rg -n "active_value|selected|def handle_input|class TreeView" src/loushang/tui/ui_parts/widgets/tree.py
```

Use existing public API if available. If no public active value exists, keep a
private value in the example by updating it from `TreeView` results and initial
known nodes. Do not add public TreeView API for example polish.

- [ ] **Step 4: Add example-local metadata**

Add mappings:

```python
NODE_DETAILS = {
    "src": ("src", "folder", "expanded"),
    "widgets": ("src/widgets", "folder", "leaf"),
    "runtime": ("src/runtime", "folder", "leaf"),
    "tests": ("tests", "folder", "collapsed"),
    "unit": ("tests/unit", "folder", "leaf"),
    "integration": ("tests/integration", "folder", "leaf"),
}
```

- [ ] **Step 5: Rewrite render with Tree and Details sections**

Render title, Tree section, tree lines, Details section, detail rows, blank row,
and footer:

```text
[up/down] node  [enter] select/toggle  [q] quit
```

Details should reflect the current active node if available; after selection,
`Status` may show `Selected: selected path`.

- [ ] **Step 6: Run tree tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit example 49**

```bash
git add examples/tui/49_widgets_tree.py tests/tui/test_widgets_tree.py
git commit -m "feat(tui): polish tree example"
```

---

### Task 9: Polish Example 50 - Deploy Console Toasts

**Files:**
- Modify: `examples/tui/50_widgets_toast.py`
- Modify: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Write failing playback test**

Add to `tests/tui/test_widgets_toast.py`:

```python
from tests.tui.widget_example_playback import play_example


def test_widgets_toast_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/50_widgets_toast.py",
        events=(
            ("warning", InputEvent(kind="text", text="w")),
            ("success", InputEvent(kind="text", text="s")),
            ("dismiss", InputEvent(kind="text", text="x")),
            ("clear", InputEvent(kind="text", text="c")),
        ),
    )

    assert frames[0].lines[:9] == (
        "Deploy Console",
        "",
        "Pipeline      api-server",
        "Status        waiting",
        "Last event    none",
        "",
        "Notifications",
        "[success] Changes saved",
        "[info] Loushang: Welcome",
    )
    assert "Last event    warning toast added" in frames[1].lines
    assert "[warning] Toast 1" in frames[1].lines
    assert "Last event    success toast added" in frames[2].lines
    assert "Last event    dismissed oldest" in frames[3].lines
    assert "Last event    cleared notifications" in frames[4].lines
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py::test_widgets_toast_example_playback_snapshots -q
```

Expected: FAIL because current example title/layout/last event text differs.

- [ ] **Step 3: Add console state**

Modify `ToastApp`:

```python
counter: int = 0
last_event: str = "none"
pipeline_status: str = "waiting"
```

- [ ] **Step 4: Rewrite render with console context**

Render:

```text
Deploy Console

Pipeline      api-server
Status        waiting
Last event    none

Notifications
toast notification rows render here

[i] info  [s] success  [w] warning  [d] danger  [x] dismiss  [c] clear  [q] quit
```

Use `truncate_to_width()` for footer and field rows.

- [ ] **Step 5: Update input handling for last event**

Rules:

- `i/s/w/d`: push toast, increment counter, set
  `last_event = f"{kind} toast added"`.
- `x`: call `dismiss_oldest()`, set `last_event = "dismissed oldest"` when
  `True`, otherwise `"nothing to dismiss"`.
- `c`: clear stack, set `last_event = "cleared notifications"`.

- [ ] **Step 6: Run toast tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit example 50**

```bash
git add examples/tui/50_widgets_toast.py tests/tui/test_widgets_toast.py
git commit -m "feat(tui): polish toast example"
```

---

### Task 10: Verify Slice 2 Together

**Files:**
- No new files expected.

- [ ] **Step 1: Run targeted Slice 2 tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Ruff on Slice 2 files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check examples/tui/48_widgets_question_dialog.py examples/tui/49_widgets_tree.py examples/tui/50_widgets_toast.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Commit any lint-only cleanup**

Only if Step 2 required edits:

```bash
git add exact files that changed
git commit -m "style(tui): clean up widget example slice two"
```

---

### Task 11: Final Verification

**Files:**
- All changed files from previous tasks.

- [ ] **Step 1: Run all polished example tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 3: Run Ruff on all touched files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/widget_example_playback.py examples/tui/44_widgets_small_controls.py examples/tui/45_widgets_light_controls.py examples/tui/46_widgets_table.py examples/tui/47_widgets_textarea.py examples/tui/48_widgets_question_dialog.py examples/tui/49_widgets_tree.py examples/tui/50_widgets_toast.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Check whitespace and git state**

Run:

```bash
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` prints nothing.
- `git status --short --branch` shows only expected branch information and no
  unstaged/untracked files.

- [ ] **Step 5: Manual playback spot-check command**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev python - <<'PY'
from tests.tui.widget_example_playback import play_example
from loushang.tui import InputEvent

for path, events in {
    "examples/tui/44_widgets_small_controls.py": (("right", InputEvent(kind="key", key="right")),),
    "examples/tui/45_widgets_light_controls.py": (("tab", InputEvent(kind="key", key="tab")),),
    "examples/tui/46_widgets_table.py": (("down", InputEvent(kind="key", key="down")),),
    "examples/tui/47_widgets_textarea.py": (("type", InputEvent(kind="text", text="Plan release")),),
    "examples/tui/48_widgets_question_dialog.py": (("tab", InputEvent(kind="key", key="tab")),),
    "examples/tui/49_widgets_tree.py": (("down", InputEvent(kind="key", key="down")),),
    "examples/tui/50_widgets_toast.py": (("warning", InputEvent(kind="text", text="w")),),
}.items():
    frames = play_example(path, events=events)
    print(f"\n== {path} ==")
    for line in frames[-1].lines[:12]:
        print(line)
PY
```

Expected: Each printed final frame has a task-oriented title and at most one
visible `>` focus marker in a single focus region.

- [ ] **Step 6: Commit final verification note only if files changed**

Do not create an empty commit. If final cleanup changed files:

```bash
git add exact files that changed
git commit -m "test(tui): verify polished widget examples"
```

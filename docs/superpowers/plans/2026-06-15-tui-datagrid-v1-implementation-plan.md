# TUI DataGrid V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable `DataGrid` widget described in `docs/superpowers/specs/2026-06-15-tui-datagrid-v1-design.md`, including public API exports, focused tests, internal docs, and a rich generic example.

**Architecture:** Implement `DataGrid` as a stateful widget in `loushang.tui.ui_parts.widgets.data_grid`, following the existing `TreeView`, `SearchableList`, and `DirectoryTree` pattern of a public constructor plus private normalized state. The widget owns grid navigation, viewport repair, formatting, editing, sorting, selection, and rendering; product pages continue to own data loading, persistence, domain actions, and page-level composition.

**Tech Stack:** Python 3.11+, dataclasses with slots, `Decimal`, existing TUI `RenderConstraints` / `RenderResult`, `InputEvent`, `ThemeResolver`, `cell_width` helpers, `callback_result`, pytest, widget playback helpers, Ruff.

---

## Prerequisites

- Work in `.worktrees/tui` on the DataGrid branch.
- Keep `Table` unchanged. DataGrid is a new widget, not a retrofit of `Table`.
- Use TDD for production behavior: write the failing test, verify failure, implement the minimum code, verify green, then commit.
- Keep V1 ASCII by default. Examples may use visual separators already common in TUI examples, but widget fallback text should be ASCII.
- Do not migrate real product pages in this plan.
- Do not add mouse, drag resize, variable row height, Rich cell renderables, async loaders, or a domain-specific stock widget.
- Future input adapters should be a separate adapter layer, not implicit constructor guessing. Likely entry points are explicit helpers such as `from_records`, `from_json`, `from_csv`, and later a Pandas/DataFrame adapter. Keep the core widget contract on normalized columns and rows.

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-15-tui-datagrid-v1-design.md`
- Existing widgets:
  - `src/loushang/tui/ui_parts/widgets/table.py`
  - `src/loushang/tui/ui_parts/widgets/tree.py`
  - `src/loushang/tui/ui_parts/widgets/searchable_list.py`
  - `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Existing tests:
  - `tests/tui/test_widgets_table.py`
  - `tests/tui/test_widgets_tree.py`
  - `tests/tui/test_widgets_searchable_list.py`
  - `tests/tui/test_widgets_directory_tree.py`
  - `tests/tui/test_widgets_reference_docs.py`
- Export files:
  - `src/loushang/tui/ui_parts/widgets/__init__.py`
  - `src/loushang/tui/ui_parts/__init__.py`
  - `src/loushang/tui/__init__.py`
- Internal docs:
  - `docs/internals/architecture/tui/native-terminal-core/ui-parts/table.md`
  - `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
- Example/playback patterns:
  - `examples/tui/57_widgets_directory_tree.py`
  - `tests/tui/widget_example_playback.py`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/data_grid.py`
  - Owns public DataGrid dataclasses, formatter classes, normalized row/cell state, render layout, navigation, selection, editing, sorting, and mutation APIs.
- `tests/tui/test_widgets_data_grid.py`
  - Focused tests for public exports, formatters, normalization, navigation, rendering, selection, editing, sorting, mutation, pinned rows, viewport, theme tokens, and example playback.
- `examples/tui/58_widgets_datagrid.py`
  - Split-view generic example. Left pane switches between at least five scenarios; right pane renders the active DataGrid. Include quit handling.
- `docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`
  - Durable DataGrid contract after implementation.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export DataGrid public names.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export DataGrid public names.
- `src/loushang/tui/__init__.py`
  - Re-export DataGrid public names.
- `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
  - Add DataGrid to the Lists inventory.
- `docs/en/reference/tui-widgets.md`
  - Add public DataGrid summary and theme token notes.
- `docs/zh-CN/reference/tui-widgets.md`
  - Add matching public DataGrid summary and theme token notes.

Do not modify:

- `src/loushang/coding/**`
- real settings/config/status pages
- existing `Table` behavior unless a failing shared-helper test proves a generic bug

## Implementation Notes

Use these implementation conventions:

- Define `DataGrid` as `@dataclass(init=False, slots=True)` with an explicit constructor. This keeps the widget mutable and long-lived without exposing runtime fields as constructor arguments.
- Keep normalized private state separate from public input rows and columns:

```python
@dataclass(frozen=True, slots=True)
class _NormalizedCell:
    value: object
    disabled: bool
    editable: bool | None
    theme_token: str | None


@dataclass(frozen=True, slots=True)
class _NormalizedRow:
    key: str
    cells: dict[str, _NormalizedCell]
    label: str | None
    disabled: bool
    pinned: Literal["top", "bottom"] | None
    theme_token: str | None
    on_select: Callable[[], object] | None
    insertion_order: int
```

- Reject duplicate column keys and row keys with `ValueError`.
- Accept row cells only as mapping, list, tuple, or `DataGridRow`. Reject `str` and `bytes` shorthand rows with `TypeError`.
- Generate shorthand keys as `row-<n>` with a monotonic counter that never reuses keys during the grid lifetime.
- Keep pinned rows visible but non-interactive in V1.
- Keep hidden columns in the data model but exclude them from render and navigation.
- Format only visible cells during render. The 10k-row test should prove this.
- Use existing helpers:
  - `autowrap_safe_width`
  - `truncate_to_width`
  - `visible_width`
  - `style_text`
  - `callback_result`
  - `is_activation_event`
  - `normalize_key_id`

---

### Task 1: Public API, Exports, Normalization, And Formatters

**Files:**
- Create: `tests/tui/test_widgets_data_grid.py`
- Create: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`

- [ ] **Step 1: Write failing API and formatter tests**

Create `tests/tui/test_widgets_data_grid.py` with helper functions and these first behaviors:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from loushang.tui import (
    CompactNumberFormatter,
    DataGrid,
    DataGridCell,
    DataGridColumn,
    DataGridFormatResult,
    DataGridRow,
    DeltaFormatter,
    NumberFormatter,
    PercentFormatter,
    RenderConstraints,
    TextFormatter,
    strip_control_sequences,
)
from loushang.tui.ui_parts import DataGrid as UiDataGrid
from loushang.tui.ui_parts.widgets import DataGrid as WidgetDataGrid


def plain_lines(part: Any, *, width: int = 80, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def test_data_grid_is_reexported_from_public_modules() -> None:
    assert DataGrid is UiDataGrid
    assert DataGrid is WidgetDataGrid
    assert DataGridColumn("code", "Code").key == "code"
    assert DataGridCell("AAPL").value == "AAPL"
    assert DataGridRow("row-1", {"code": "AAPL"}).key == "row-1"


def test_data_grid_formatters_cover_text_number_percent_delta_and_compact_values() -> None:
    assert TextFormatter()(None) == ""
    assert TextFormatter(none_text="N/A")(None) == "N/A"
    assert NumberFormatter(precision=2)(Decimal("1234.5")) == "1234.50"
    assert NumberFormatter(precision=2, thousands=True, sign=True)(1234.5) == "+1,234.50"
    assert PercentFormatter(precision=2, sign=True)(0.0345) == "+3.45%"
    assert DeltaFormatter(precision=2)(-1.2) == "-1.20"
    assert CompactNumberFormatter(precision=1)(1250000) == "1.3M"
    assert NumberFormatter(precision=2, invalid_text="bad")(float("nan")) == "bad"


def test_data_grid_normalizes_mapping_list_tuple_rows_and_cell_metadata() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code"),
            DataGridColumn("qty", "Qty", formatter=NumberFormatter(precision=0)),
            DataGridColumn("hidden", "Hidden", hidden=True),
        ],
        [
            {"code": "AAPL", "qty": 5},
            ["MSFT", DataGridCell(3, disabled=True), "secret"],
            DataGridRow("explicit", {"code": "NVDA", "qty": None}, label="Nvidia"),
        ],
    )

    assert grid.row_keys == ("row-0", "row-1", "explicit")
    assert grid.active_row_key == "row-0"
    assert grid.active_column_key == "code"
    assert plain_lines(grid, width=32, height=5) == (
        "  Code          Qty",
        "  AAPL            5",
        "  MSFT            3",
        "  NVDA",
    )


def test_data_grid_rejects_duplicate_keys_and_string_rows() -> None:
    with pytest.raises(ValueError, match="duplicate column"):
        DataGrid([DataGridColumn("code", "Code"), DataGridColumn("code", "Other")], [])

    with pytest.raises(ValueError, match="duplicate row"):
        DataGrid([DataGridColumn("code", "Code")], [DataGridRow("same", {"code": "A"}), DataGridRow("same", {"code": "B"})])

    with pytest.raises(TypeError, match="mapping, list, tuple, or DataGridRow"):
        DataGrid([DataGridColumn("code", "Code")], ["AAPL"])  # type: ignore[list-item]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

Expected: import failure for `DataGrid` public names.

- [ ] **Step 3: Implement the minimum API, formatter, normalization, simple render, and exports**

Implement:

- public dataclasses and type aliases from the spec
- formatter classes
- `DataGrid.__init__`
- normalization and row key generation
- `row_keys`, `active_row_key`, `active_column_key`, `selected_row_keys`, `selected_cell_keys`, `sort_state`, `editing_error` properties
- a minimal header/body renderer with visible columns only
- public exports through the three `__init__.py` files

- [ ] **Step 4: Run Task 1 tests and verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

Expected: Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "feat(tui): add datagrid api and formatters"
```

---

### Task 2: Row, Cell, And Column Navigation

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`

- [ ] **Step 1: Write failing navigation tests**

Add tests for:

- row mode up/down/home/end skips disabled and pinned rows
- row wrap and no-wrap boundaries
- cell mode left/right/up/down skips disabled cells and hidden columns
- column mode left/right/home/end changes only the active column
- `cursor_mode="none"` consumes no navigation
- active row/column repairs when the preferred active key is disabled, hidden, pinned, or missing

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

Expected: navigation assertions fail because `handle_input()` is not complete.

- [ ] **Step 3: Implement navigation and active-state repair**

Implement:

- `focus()` and `blur()`
- `handle_input()` dispatch for row, cell, column, and none cursor modes
- enabled target discovery helpers
- row and column wrapping
- active row/column repair after construction and after movement

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 2**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py
git commit -m "feat(tui): add datagrid keyboard navigation"
```

---

### Task 3: Rendering Layout, Viewports, Fixed Columns, And Theme Tokens

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`

- [ ] **Step 1: Write failing rendering tests**

Add tests for:

- width allocation with fixed width, flexible width, min width, max width, and right-to-left shrinking
- left fixed columns remain visible while horizontal viewport scrolls
- row labels render between prefix and cells when enabled
- row, cell, and column cursor declarations use the correct visible position
- column mode focuses the header and does not draw a body `> ` prefix
- pinned top and bottom rows render in order but remain non-interactive
- header plus pinned overflow truncates from the bottom
- zebra stripes and theme-token composition apply without changing visible text
- disabled rows and disabled cells use disabled tokens and are visible
- every rendered line fits the requested width

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 3: Implement layout and rendering**

Implement:

- visible column window calculation
- fixed column window handling
- column width allocation and shrinking
- row label width
- prefix, header, body, pinned, and empty row rendering
- cursor declarations
- style token layering with `style_text`
- `first_visible_row_index`, `first_visible_column_index`, `more_rows_above`, `more_rows_below`, and horizontal viewport properties if useful for tests and examples

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 3**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py
git commit -m "feat(tui): render datagrid viewports"
```

---

### Task 4: Activation, Selection, And Structured Results

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`

- [ ] **Step 1: Write failing activation and selection tests**

Add tests for:

- Enter activation returns `DataGridSelect` in row, cell, and column modes
- row-mode activation delegates `DataGridRow.on_select` through `callback_result()`
- Space toggles single row selection in row mode
- Space toggles single cell selection in cell mode
- Space toggles multi row/cell selection without clearing other selections
- column mode plus `selection_mode="single"` returns `False`
- column mode plus `selection_mode="multi"` selects enabled cells in the active visible column
- `select_all()`, `clear_selection()`, and selected key properties are key-based
- disabled and pinned targets are never selected

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 3: Implement activation and selection APIs**

Implement:

- `DataGridSelect`
- `DataGridSelectionChange`
- activation target helpers
- row/cell/column selection mutation
- `select_all()`
- `clear_selection()`
- stable selection repair when targets disappear

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 4**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py
git commit -m "feat(tui): add datagrid activation and selection"
```

---

### Task 5: Inline Editing And Data Entry Flows

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`

- [ ] **Step 1: Write failing editing tests**

Add tests for:

- `e` starts editing the active editable cell
- Enter starts editing when the column uses `enter_behavior="edit"`
- Enter on a non-editable cell falls back to activation
- printable input replaces the initially selected edit buffer
- Backspace clears the initially selected edit buffer
- commit returns `DataGridEdit` and updates the raw value
- parser and validator errors keep editing open and set `editing_error`
- Escape cancels editing
- successful commit preserves `DataGridCell` metadata while replacing value
- `edit_next_column_key` moves and starts editing the next editable cell when possible
- default values can be accepted unchanged when `edit_accepts_unchanged=True`
- `start_edit(row_key, column_key)` repairs cursor and viewport even when editing cannot start
- product-side update of other cells after a `DataGridEdit` does not cancel completed edit state

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 3: Implement editing**

Implement:

- edit buffer state
- `start_edit()`, `cancel_edit()`, and `commit_edit()`
- text and editing-key input handling
- parser, validator, and error handling
- editing render token
- `DataGridEdit`
- edit-next flow

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 5**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py
git commit -m "feat(tui): support datagrid inline editing"
```

---

### Task 6: Sorting, Mutation APIs, And Refresh Semantics

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`

- [ ] **Step 1: Write failing sorting and mutation tests**

Add tests for:

- `sort_by(column_key, direction="asc"|"desc")` is stable and ignores hidden/non-sortable columns
- `clear_sort()` restores insertion order
- sorting excludes pinned rows
- `replace_rows()` reapplies active sort and repairs active key in post-sort order
- shorthand rows in `replace_rows()` receive fresh generated keys and do not preserve selection
- explicit keys in `replace_rows()` preserve active and selection when still present
- `add_row()` returns generated or explicit key and can activate/edit a new row
- `remove_row()` repairs active state and selection
- `update_cell()` updates raw value and metadata
- `add_column()` accepts `object | DataGridCell` default
- `remove_column()` removes selected cells for that column
- `clear()` clears data, selection, editing state, and sort state while preserving columns and configuration
- pinned bottom total row can be replaced after product-side recomputation

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 3: Implement sorting and mutation**

Implement:

- stable sort state
- `sort_by()`
- `clear_sort()`
- `add_row()`
- `replace_rows()`
- `remove_row()`
- `add_column()`
- `remove_column()`
- `update_cell()`
- `clear()`
- repair hooks after every mutation

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 6**

```bash
git add tests/tui/test_widgets_data_grid.py src/loushang/tui/ui_parts/widgets/data_grid.py
git commit -m "feat(tui): add datagrid sorting and mutation"
```

---

### Task 7: Large Data, Public Docs, And Reference Tests

**Files:**
- Modify: `tests/tui/test_widgets_data_grid.py`
- Create: `docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Modify: `tests/tui/test_widgets_reference_docs.py`

- [ ] **Step 1: Write failing docs and large-data tests**

Add tests for:

- rendering a 10k-row grid formats only the visible row window
- docs mention `DataGrid` and keep legacy settings primitives absent
- reference docs include key public names and theme tokens

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py tests/tui/test_widgets_reference_docs.py -q
```

- [ ] **Step 3: Add docs and optimize render path if needed**

Implement:

- 10k-row render should not pre-format all rows
- internal DataGrid doc with API, rendering, input, editing, mutation, theme tokens, and testing expectations
- README inventory entry
- English and Chinese reference entries

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py tests/tui/test_widgets_reference_docs.py -q
```

- [ ] **Step 5: Commit Task 7**

```bash
git add tests/tui/test_widgets_data_grid.py tests/tui/test_widgets_reference_docs.py docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document datagrid widget"
```

---

### Task 8: Split-View Example And Playback

**Files:**
- Create: `examples/tui/58_widgets_datagrid.py`
- Modify: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing example playback tests**

Add tests that import and play `examples/tui/58_widgets_datagrid.py` and verify:

- the example exposes `build_app()`
- `q` exits cleanly
- left scenario list can switch at least five scenarios
- right pane renders a DataGrid in each scenario
- stock-like watchlist shows right-aligned price, delta, percent, and compact volume
- order-entry scenario can edit code and quantity and has a pinned total row
- read-only jobs scenario supports selection/activation without editing
- usage/model metrics scenario uses percent/compact number formatting
- diagnostics/results scenario uses semantic warning/error tokens

- [ ] **Step 2: Verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 3: Implement the example**

Use a compact split layout:

- left pane: `SearchableList` or simple selectable scenario rows
- right pane: one active `DataGrid`
- footer: concise keys, including `q quit`
- theme: example-specific tokens plus `widget.dataGrid.*`
- scenarios:
  - Market watchlist
  - Order entry with total
  - Read-only jobs
  - Usage metrics
  - Diagnostics

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

- [ ] **Step 5: Commit Task 8**

```bash
git add tests/tui/test_widgets_data_grid.py examples/tui/58_widgets_datagrid.py
git commit -m "test(tui): add datagrid example playback"
```

---

### Task 9: Full Validation And Cleanup

**Files:**
- Modify as needed from validation findings only.

- [ ] **Step 1: Run focused lint**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py examples/tui/58_widgets_datagrid.py
```

Expected: pass.

- [ ] **Step 2: Run focused TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py tests/tui/test_widgets_reference_docs.py -q
```

Expected: pass.

- [ ] **Step 3: Run broader TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: pass, or document any unrelated existing failure with exact command and failure.

- [ ] **Step 4: Manual example smoke test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev python examples/tui/58_widgets_datagrid.py
```

Manual checks:

- `q` exits cleanly.
- Scenario switching is visible.
- Row/cell/column focus is not visually confused.
- Watchlist numeric alignment is stable.
- Order entry can accept default quantity by pressing Enter and replace it by typing.
- Pinned total row updates in the example flow.
- Read-only jobs activation reports a detail-like status.

- [ ] **Step 5: Final status**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected: branch contains focused task commits and no unintended dirty files.

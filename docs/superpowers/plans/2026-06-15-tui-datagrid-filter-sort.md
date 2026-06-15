# TUI DataGrid Filter And Sort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add DataGrid filtering/search, view-aware navigation, and sort UX in two phases, with a large-data filter/sort example.

**Architecture:** Keep `DataGrid` as the owner of row-view semantics and keep filter controls outside the widget. Phase 1 adds filter query/predicate state, `view_row_keys`, body-view helpers, active repair, selection scoping, and a filtered large-data example. Phase 2 adds `cycle_sort()`, header sort markers, and expands the example into a multi-control filter/sort demo.

**Tech Stack:** Python 3.11, dataclasses, existing `loushang.tui` render/input primitives, pytest, TUI playback helpers.

---

## Spec

Implement from:

- `docs/superpowers/specs/2026-06-15-tui-datagrid-filter-sort-design.md`

Keep the spec decisions intact unless a later human review changes them.

## File Map

- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
  - Add filter public types and state.
  - Add `DataGridColumn.searchable`.
  - Add body-view helpers.
  - Make render/navigation/selection/activation use body view.
  - Add `cycle_sort()` and header markers.
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `DataGridFilterMode`, `DataGridFilterPredicate`, and `DataGridRowView`.
- Modify: `src/loushang/tui/ui_parts/__init__.py`
  - Re-export the same public DataGrid filter types.
- Modify: `src/loushang/tui/__init__.py`
  - Re-export the same public DataGrid filter types.
- Modify: `tests/tui/test_widgets_data_grid.py`
  - Add focused unit tests for filter APIs, repair, activation, selection, sorting, and examples.
- Modify: `examples/tui/60_widgets_datagrid_large_dataset.py`
  - Phase 1: add search input and filtered page navigation.
  - Phase 2: add multi-control filter bar and sort keybinding.
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`
  - Update durable internal docs after implementation.
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
  - Link or summarize the new filter/sort contract if this README lists widgets.

## Commands

Use these commands throughout:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py examples/tui/60_widgets_datagrid_large_dataset.py
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py tests/tui/test_widgets_reference_docs.py tests/tui/test_import_boundaries.py -q
```

---

## Phase 1: Filtering Core

### Task 1: Public Filter Types And Default State

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing API/export tests**

Add imports to `tests/tui/test_widgets_data_grid.py`:

```python
from loushang.tui import (
    DataGridFilterMode,
    DataGridRowView,
)
```

Extend `test_data_grid_is_reexported_from_public_modules()`:

```python
    assert DataGridRowView("row-1", {"code": "AAPL"}).key == "row-1"
    mode: DataGridFilterMode = "contains"
    assert mode == "contains"
```

Add:

```python
def test_data_grid_filter_state_defaults_and_column_searchable_flag() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code"), DataGridColumn("secret", "Secret", searchable=False)],
        [DataGridRow("a", {"code": "AAPL", "secret": "hidden"})],
    )

    assert grid.filter_query == ""
    assert grid.filter_query_columns is None
    assert grid.filter_mode == "contains"
    assert grid.filter_case_sensitive is False
    assert grid.has_filter is False
    assert grid.view_row_keys == ("a",)
    assert grid.filtered_row_count == 1
    assert grid.total_body_row_count == 1
    assert grid.columns[1].searchable is False
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py::test_data_grid_is_reexported_from_public_modules tests/tui/test_widgets_data_grid.py::test_data_grid_filter_state_defaults_and_column_searchable_flag -q
```

Expected: FAIL because filter types/properties do not exist.

- [ ] **Step 3: Add public types and default state**

In `data_grid.py`:

```python
from types import MappingProxyType

DataGridFilterMode = Literal["contains", "prefix"]

@dataclass(frozen=True, slots=True)
class DataGridRowView:
    key: str
    values: Mapping[str, object]
    label: str | None = None
    disabled: bool = False

DataGridFilterPredicate = Callable[[DataGridRowView], bool]
```

Add to `__all__`:

```python
"DataGridFilterMode",
"DataGridFilterPredicate",
"DataGridRowView",
```

Add to `DataGridColumn`:

```python
searchable: bool = True
```

Add `DataGrid` runtime fields:

```python
_filter_query: str = field(default="", init=False, repr=False)
_filter_query_columns: tuple[str, ...] | None = field(default=None, init=False, repr=False)
_filter_mode: DataGridFilterMode = field(default="contains", init=False, repr=False)
_filter_case_sensitive: bool = field(default=False, init=False, repr=False)
_filter_predicate: DataGridFilterPredicate | None = field(default=None, init=False, repr=False)
```

Initialize them in `__init__`.

Add properties:

```python
@property
def filter_query(self) -> str:
    return self._filter_query

@property
def filter_query_columns(self) -> tuple[str, ...] | None:
    return self._filter_query_columns

@property
def filter_mode(self) -> DataGridFilterMode:
    return self._filter_mode

@property
def filter_case_sensitive(self) -> bool:
    return self._filter_case_sensitive

@property
def has_filter(self) -> bool:
    return bool(self._filter_query) or self._filter_predicate is not None

@property
def view_row_keys(self) -> tuple[str, ...]:
    return tuple(row.key for row in self._view_body_rows())

@property
def filtered_row_count(self) -> int:
    return len(self.view_row_keys)

@property
def total_body_row_count(self) -> int:
    return len(self._body_rows())
```

Add private helpers:

```python
def _body_rows(self) -> tuple[_NormalizedRow, ...]:
    return tuple(row for row in self._rows if row.pinned is None)

def _pinned_top_rows(self) -> tuple[_NormalizedRow, ...]:
    return tuple(row for row in self._rows if row.pinned == "top")

def _pinned_bottom_rows(self) -> tuple[_NormalizedRow, ...]:
    return tuple(row for row in self._rows if row.pinned == "bottom")

def _view_body_rows(self) -> tuple[_NormalizedRow, ...]:
    return self._body_rows()
```

Update exports in the three `__init__.py` files.

- [ ] **Step 4: Run tests and verify pass**

Run the same focused pytest command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/data_grid.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): add datagrid filter API state"
```

### Task 2: Query Filtering And Predicate Matching

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing query/predicate tests**

Add tests:

```python
def test_data_grid_filter_query_matches_visible_searchable_raw_values() -> None:
    grid = DataGrid(
        [
            DataGridColumn("symbol", "Symbol"),
            DataGridColumn("sector", "Sector"),
            DataGridColumn("hidden", "Hidden", hidden=True),
            DataGridColumn("secret", "Secret", searchable=False),
        ],
        [
            DataGridRow("a", {"symbol": "AAPL", "sector": "AI", "hidden": "ghost", "secret": "private"}),
            DataGridRow("m", {"symbol": "MSFT", "sector": "Cloud", "hidden": "x", "secret": "AAPL"}),
            DataGridRow("n", {"symbol": "NVDA", "sector": None, "hidden": "aapl", "secret": "x"}),
        ],
    )

    assert grid.set_filter_query("aap") is True
    assert grid.view_row_keys == ("a",)
    assert grid.row_keys == ("a", "m", "n")

    assert grid.set_filter_query("A", columns=("sector",), mode="prefix") is True
    assert grid.filter_query_columns == ("sector",)
    assert grid.view_row_keys == ("a",)

    assert grid.set_filter_query("a", columns=("hidden", "secret", "missing")) is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()
```

```python
def test_data_grid_filter_query_case_sensitive_and_none_normalization() -> None:
    grid = DataGrid(
        [DataGridColumn("value", "Value")],
        [DataGridRow("upper", {"value": "AAPL"}), DataGridRow("none", {"value": None})],
    )

    assert grid.set_filter_query("aapl", case_sensitive=True) is True
    assert grid.view_row_keys == ()

    assert grid.set_filter_query("", case_sensitive=True) is True
    assert grid.filter_query == ""
    assert grid.filter_case_sensitive is False

    assert grid.set_filter_query("none") is True
    assert grid.view_row_keys == ()
```

```python
def test_data_grid_filter_predicate_combines_with_query_and_uses_row_view() -> None:
    seen: list[tuple[str, dict[str, object], bool]] = []
    grid = DataGrid(
        [
            DataGridColumn("symbol", "Symbol"),
            DataGridColumn("price", "Price"),
            DataGridColumn("hidden", "Hidden", hidden=True),
        ],
        [
            DataGridRow("a", {"symbol": "AAPL", "price": 210, "hidden": "visible-to-predicate"}),
            DataGridRow("m", {"symbol": "MSFT", "price": 420, "hidden": "x"}, disabled=True),
            DataGridRow("n", {"symbol": "NVDA", "price": 120, "hidden": "x"}),
        ],
    )

    def predicate(row: DataGridRowView) -> bool:
        seen.append((row.key, dict(row.values), row.disabled))
        return float(row.values["price"]) >= 200

    assert grid.set_filter_query("a") is True
    assert grid.set_filter_predicate(predicate) is True

    assert grid.view_row_keys == ("a",)
    assert ("m", {"symbol": "MSFT", "price": 420, "hidden": "x"}, True) in seen
```

```python
def test_data_grid_filter_predicate_exceptions_propagate() -> None:
    grid = DataGrid([DataGridColumn("name", "Name")], [DataGridRow("a", {"name": "A"})])

    with pytest.raises(RuntimeError, match="bad predicate"):
        grid.set_filter_predicate(lambda row: (_ for _ in ()).throw(RuntimeError("bad predicate")))
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_query or filter_predicate" -q
```

Expected: FAIL because setters/filter matching are missing.

- [ ] **Step 3: Implement query and predicate filtering**

Add methods:

```python
def set_filter_query(
    self,
    query: str,
    *,
    columns: Sequence[str] | None = None,
    mode: DataGridFilterMode = "contains",
    case_sensitive: bool = False,
) -> bool:
    if mode not in {"contains", "prefix"}:
        return False
    effective_query = str(query).strip()
    accepted_columns = None if columns is None else self._accepted_query_columns(columns)
    if not effective_query:
        next_query = ""
        accepted_columns = None
        mode = "contains"
        case_sensitive = False
    old_keys = self.view_row_keys
    old_state = (self._filter_query, self._filter_query_columns, self._filter_mode, self._filter_case_sensitive)
    self._filter_query = effective_query
    self._filter_query_columns = accepted_columns
    self._filter_mode = mode
    self._filter_case_sensitive = bool(case_sensitive)
    self._repair_state_after_view_change()
    return old_state != (self._filter_query, self._filter_query_columns, self._filter_mode, self._filter_case_sensitive) or old_keys != self.view_row_keys

def set_filter_predicate(self, predicate: DataGridFilterPredicate | None) -> bool:
    old_keys = self.view_row_keys
    old_predicate = self._filter_predicate
    self._filter_predicate = predicate
    self._repair_state_after_view_change()
    return old_predicate is not predicate or old_keys != self.view_row_keys

def clear_filter(self) -> bool:
    old_keys = self.view_row_keys
    had_filter = self.has_filter
    self._filter_query = ""
    self._filter_query_columns = None
    self._filter_mode = "contains"
    self._filter_case_sensitive = False
    self._filter_predicate = None
    self._repair_state_after_view_change()
    return had_filter or old_keys != self.view_row_keys
```

Add helpers:

```python
def _accepted_query_columns(self, columns: Sequence[str]) -> tuple[str, ...]:
    accepted: list[str] = []
    seen: set[str] = set()
    for key in columns:
        column = self._column_by_key(str(key))
        if column is None or column.hidden or not column.searchable or column.key in seen:
            continue
        accepted.append(column.key)
        seen.add(column.key)
    return tuple(accepted)

def _query_columns(self) -> tuple[DataGridColumn, ...]:
    if self._filter_query_columns is not None:
        keys = set(self._filter_query_columns)
        return tuple(column for column in self._columns if column.key in keys and not column.hidden and column.searchable)
    return tuple(column for column in self._visible_columns() if column.searchable)

def _row_view(self, row: _NormalizedRow) -> DataGridRowView:
    values = {key: cell.value for key, cell in row.cells.items()}
    return DataGridRowView(row.key, MappingProxyType(values), row.label, row.disabled)

def _view_body_rows(self) -> tuple[_NormalizedRow, ...]:
    return tuple(row for row in self._body_rows() if self._row_matches_filters(row))

def _row_matches_filters(self, row: _NormalizedRow) -> bool:
    if self._filter_query and not self._row_matches_query(row):
        return False
    if self._filter_predicate is not None and not self._filter_predicate(self._row_view(row)):
        return False
    return True

def _row_matches_query(self, row: _NormalizedRow) -> bool:
    columns = self._query_columns()
    if not columns:
        return False
    query = self._filter_query
    needle = query if self._filter_case_sensitive else query.casefold()
    for column in columns:
        value = row.cells[column.key].value
        cell_text = "" if value is None else str(value)
        haystack = cell_text if self._filter_case_sensitive else cell_text.casefold()
        if self._filter_mode == "prefix" and haystack.startswith(needle):
            return True
        if self._filter_mode == "contains" and needle in haystack:
            return True
    return False
```

Add `_repair_state_after_view_change()` initially as:

```python
def _repair_state_after_view_change(self) -> None:
    self._active_row_key = self._repair_row_key(self._active_row_key)
    self._first_visible_row_index = 0 if not self._view_body_rows() else self._first_visible_row_index
```

This gets expanded in later tasks.

- [ ] **Step 4: Run tests and verify pass**

Run the focused pytest command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): filter datagrid rows by query and predicate"
```

### Task 3: Make Render And Navigation Use Body View

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing view/render/navigation tests**

Add:

```python
def test_data_grid_filter_render_navigation_and_empty_body_view() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("top", {"job": "Pinned top"}, pinned="top"),
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("deploy", {"job": "Deploy"}),
            DataGridRow("bottom", {"job": "Pinned bottom"}, pinned="bottom"),
        ],
        active_row_key="deploy",
        empty_text="No matches",
        wrap_rows=False,
    )

    assert grid.set_filter_query("build") is True
    assert grid.active_row_key == "build"
    assert grid.view_row_keys == ("build",)
    assert grid.handle_input(InputEvent(kind="key", key="down")) is False

    lines = plain_lines(grid, width=32, height=6)
    assert any("Pinned top" in line for line in lines)
    assert any("Build" in line for line in lines)
    assert any("Pinned bottom" in line for line in lines)
    assert not any("Deploy" in line for line in lines)

    assert grid.set_filter_query("missing") is True
    assert grid.active_row_key is None
    lines = plain_lines(grid, width=32, height=6)
    assert any("Pinned top" in line for line in lines)
    assert any("No matches" in line for line in lines)
```

Add a 10k visible-format test extension:

```python
def test_data_grid_filtered_large_viewport_formats_only_visible_rows() -> None:
    formatted: list[int] = []

    def counted_formatter(value: object) -> str:
        formatted.append(int(value))
        return f"Item {value}"

    grid = DataGrid(
        [DataGridColumn("name", "Name", formatter=counted_formatter)],
        [DataGridRow(str(index), {"name": index}) for index in range(10_000)],
        active_row_key="9999",
    )

    assert grid.set_filter_predicate(lambda row: int(row.values["name"]) >= 9_997) is True
    lines = plain_lines(grid, width=24, height=4)

    assert any("Item 9999" in line for line in lines)
    assert formatted == [9997, 9998, 9999]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_render_navigation or filtered_large_viewport" -q
```

Expected: FAIL because render/navigation still use `_rows`.

- [ ] **Step 3: Switch render/navigation helpers to body view**

Change:

- `render()` to use:
  - `top_rows = self._pinned_top_rows()`
  - `body_rows = self._view_body_rows()`
  - `bottom_rows = self._pinned_bottom_rows()`
  - empty body view line when `not body_rows`
- `_enabled_rows()` to return enabled rows from `_view_body_rows()`.
- `_active_row()` to require the row key in current body view.
- `_repair_row_key()` to choose from `_enabled_rows()`.
- `_ensure_active_body_visible()` call to receive body view.

The empty body line can be implemented by extracting the existing empty row code:

```python
def _empty_row_line(
    self,
    columns: Sequence[DataGridColumn],
    widths: Sequence[int],
    target_width: int,
    *,
    label_width: int,
) -> RenderLine:
    empty_cells = (self.empty_text,) + tuple("" for _ in columns[1:])
    text = _grid_line(empty_cells, columns, widths, target_width, label_width=label_width)
    return RenderLine(style_text(text, self.theme, "widget.dataGrid.empty"))
```

- [ ] **Step 4: Expand repair after view changes**

Implement `_repair_state_after_view_change()`:

```python
def _repair_state_after_view_change(self) -> None:
    if self._editing_cell_key is not None and self._editing_cell_key[0] not in self.view_row_keys:
        self.cancel_edit()
    self._active_row_key = self._repair_row_key(self._active_row_key)
    self._active_column_key = self._repair_column_key(self._active_column_key)
    if self.cursor_mode == "cell":
        self._repair_active_cell()
    body_rows = self._view_body_rows()
    if not body_rows:
        self._first_visible_row_index = 0
    else:
        self._first_visible_row_index = max(0, min(self._first_visible_row_index, max(0, len(body_rows) - 1)))
```

Call `_repair_state_after_view_change()` from `_repair_state_after_data_change()` after pruning missing rows/columns.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_render_navigation or filtered_large_viewport or large_viewport_formats_only_visible_rows" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): render and navigate datagrid body views"
```

### Task 4: Activation, Selection, Editing, And Column Changes Under Filters

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing behavior-table tests**

Add:

```python
def test_data_grid_filter_blocks_activation_for_filtered_disabled_and_pinned_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [
            DataGridRow("top", {"job": "Top", "runs": 0}, pinned="top"),
            DataGridRow("build", {"job": "Build", "runs": 12}),
            DataGridRow("skip", {"job": "Skip", "runs": 0}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy", "runs": 3}),
        ],
        cursor_mode="cell",
    )

    assert grid.set_filter_query("build") is True
    assert grid.activate_row("deploy") is False
    assert grid.activate_cell("deploy", "job") is False
    assert grid.activate_row("skip") is False
    assert grid.activate_row("top") is False
    assert grid.activate_row("build") is False  # already active after repair
```

Add selection/editing/column tests:

```python
def test_data_grid_filter_scopes_selection_and_preserves_hidden_selection_keys() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [DataGridRow("build", {"job": "Build"}), DataGridRow("deploy", {"job": "Deploy"})],
        selection_mode="multi",
    )

    assert grid.select_row("deploy") is True
    assert grid.set_filter_query("build") is True
    assert grid.selected_row_keys == frozenset({"deploy"})
    assert grid.select_all() is True
    assert grid.selected_row_keys == frozenset({"build"})
```

```python
def test_data_grid_filter_cancels_edit_when_editing_row_is_filtered_out() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code", editable=True)],
        [DataGridRow("a", {"code": "AAPL"}), DataGridRow("m", {"code": "MSFT"})],
        cursor_mode="cell",
    )

    assert grid.start_edit("m", "code") is True
    assert grid.set_filter_query("AAPL") is True
    assert grid.editing_cell_key is None
```

```python
def test_data_grid_filter_query_columns_repair_when_columns_hidden_or_removed() -> None:
    grid = DataGrid(
        [DataGridColumn("symbol", "Symbol"), DataGridColumn("sector", "Sector")],
        [DataGridRow("a", {"symbol": "AAPL", "sector": "AI"})],
    )

    assert grid.set_filter_query("AI", columns=("sector",)) is True
    assert grid.view_row_keys == ("a",)
    assert grid.set_column_hidden("sector") is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()

    assert grid.set_filter_query("AAPL", columns=("symbol",)) is True
    assert grid.remove_column("symbol") is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_blocks_activation or filter_scopes_selection or filter_cancels_edit or filter_query_columns_repair" -q
```

Expected: FAIL until activation/selection/column repair are view-aware.

- [ ] **Step 3: Make activation and selection view-aware**

Change:

- `activate_row()` must require row key in `view_row_keys`.
- `activate_cell()` and `_is_enabled_cell()` must require row key in `view_row_keys`.
- `select_row()`, `toggle_row()`, `select_cell()`, `toggle_cell()` must return `False` for filtered-out rows.
- `select_all()`, `_enabled_cell_keys()`, `_enabled_cell_keys_for_column()`, and `_editable_cell_keys()` should use `_enabled_rows()` after Task 3.

Important: do not prune existing selected keys solely because a row is filtered out. Only mutation/removal should prune.

- [ ] **Step 4: Repair explicit query columns on column changes**

Add:

```python
def _repair_filter_query_columns(self) -> None:
    if self._filter_query_columns is None:
        return
    self._filter_query_columns = self._accepted_query_columns(self._filter_query_columns)
```

Call it after `remove_column()` and `set_column_hidden()`, before `_repair_state_after_data_change()`.

Update `_repair_state_after_data_change()` so selection pruning uses source enabled rows/cells for mutation removals, not filtered view. Add private helpers if needed:

```python
def _source_enabled_rows(self) -> tuple[_NormalizedRow, ...]:
    return tuple(row for row in self._body_rows() if not row.disabled)
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_blocks_activation or filter_scopes_selection or filter_cancels_edit or filter_query_columns_repair" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): scope datagrid actions to filtered rows"
```

### Task 5: Phase 1 Large Dataset Search Example

**Files:**
- Modify: `examples/tui/60_widgets_datagrid_large_dataset.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing example tests**

Update existing example tests to expect a search control:

```python
def test_widgets_datagrid_large_dataset_search_filters_pages() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")
    app = namespace["LargeDataGridExampleApp"]()

    app.render(RenderConstraints(width=110, max_height=24))
    assert app.handle_input(InputEvent(kind="key", key="tab")) is True
    assert app.focus_region == "search"
    assert app.handle_input(InputEvent(kind="text", text="STK199")) is True

    assert app.grid.filtered_row_count < namespace["ROW_COUNT"]
    assert app.grid.view_row_keys
    assert app.grid.active_row_key == app.grid.view_row_keys[0]

    lines = plain_lines(app, width=110, height=24)
    assert any("filtered from 2,000" in line for line in lines)
```

Add:

```python
def test_widgets_datagrid_large_dataset_page_uses_filtered_view_keys() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")
    app = namespace["LargeDataGridExampleApp"]()

    app.render(RenderConstraints(width=110, max_height=24))
    app._apply_search("STK19")
    app.render(RenderConstraints(width=110, max_height=8))
    assert app.handle_input(InputEvent(kind="key", key="ctrl+g")) is True
    assert app.handle_input(InputEvent(kind="text", text="2")) is True
    assert app.handle_input(InputEvent(kind="key", key="enter")) is True

    assert app.grid.active_row_key in app.grid.view_row_keys
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "large_dataset_search or large_dataset_page_uses_filtered" -q
```

Expected: FAIL because search is not implemented.

- [ ] **Step 3: Add search input focus region**

In `LargeDataGridExampleApp`:

- Add `search_input: TextInput`.
- Add focus region `"search"`.
- Render a control line before page line:

```text
> Search: [cloud        ]    Matches 327/2,000
  Go to page: [1   ] / 17    Row 41/327    Ready
```

- Update focus order:

```text
grid -> search -> goto -> grid
```

for Phase 1, using Tab/Shift+Tab.

- Focused inputs own text, Backspace, Enter, Escape.
- `q` quits only when focus is grid.

- [ ] **Step 4: Apply search live and page over `view_row_keys`**

Add helper:

```python
def _apply_search(self, value: str) -> None:
    self.search_input.set_text(value)
    self.grid.set_filter_query(value, columns=("id", "symbol", "sector", "status"))
    self._repair_filtered_page()
    self.status = _page_status(self)
```

Update:

- `_active_row_index()` to use `grid.view_row_keys.index(active_row_key)`.
- `_active_row_number()` to be 1-based within filtered view.
- `_total_pages()` to use `grid.filtered_row_count`.
- `_go_to_page()` to activate first enabled key in filtered page.
- `_footer()` to show filtered count.

- [ ] **Step 5: Run example tests and focused DataGrid tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "large_dataset" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add examples/tui/60_widgets_datagrid_large_dataset.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): add datagrid large search example"
```

---

## Phase 2: Sort UX And Multi-Control Filter Bar

### Task 6: `cycle_sort()` And Header Markers

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/data_grid.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing sort UX tests**

Add:

```python
def test_data_grid_cycle_sort_cycles_column_state_and_preserves_filters() -> None:
    grid = DataGrid(
        [DataGridColumn("symbol", "Symbol"), DataGridColumn("price", "Price", align="right")],
        [
            DataGridRow("b", {"symbol": "B", "price": 2}),
            DataGridRow("a", {"symbol": "A", "price": 1}),
        ],
        cursor_mode="cell",
        active_column_key="price",
    )
    assert grid.set_filter_query("A", columns=("symbol",)) is True

    assert grid.cycle_sort() is True
    assert grid.sort_state == ("price", "asc")
    assert grid.view_row_keys == ("a",)

    assert grid.cycle_sort() is True
    assert grid.sort_state == ("price", "desc")

    assert grid.cycle_sort() is True
    assert grid.sort_state is None
    assert grid.has_filter is True
```

Add:

```python
def test_data_grid_sort_header_markers_render_and_pinned_rows_stay_pinned() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job", width=8), DataGridColumn("runs", "Runs", width=5, align="right")],
        [
            DataGridRow("top", {"job": "Top", "runs": 0}, pinned="top"),
            DataGridRow("b", {"job": "Build", "runs": 12}),
            DataGridRow("d", {"job": "Deploy", "runs": 3}),
            DataGridRow("bottom", {"job": "Bottom", "runs": 0}, pinned="bottom"),
        ],
    )

    assert grid.sort_by("runs", "asc") is True
    assert grid.row_keys == ("top", "d", "b", "bottom")
    assert "Runs ^" in plain_lines(grid, width=32, height=6)[0]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "cycle_sort or sort_header_markers" -q
```

Expected: FAIL because `cycle_sort()` and header markers are missing.

- [ ] **Step 3: Implement `cycle_sort()`**

Add:

```python
def cycle_sort(self, column_key: str | None = None) -> bool:
    key = column_key if column_key is not None else self._active_column_key
    if key is None:
        return False
    column = self._column_by_key(str(key))
    if column is None or column.hidden or not column.sortable:
        return False
    if self._sort_state is None or self._sort_state[0] != column.key:
        return self.sort_by(column.key, "asc")
    if self._sort_state[1] == "asc":
        return self.sort_by(column.key, "desc")
    return self.clear_sort()
```

Update `sort_by()`, `clear_sort()`, and `cycle_sort()` to call the view-aware repair path.

- [ ] **Step 4: Render header sort markers**

In `render()`, replace:

```python
headers = tuple(column.header for column in render_columns)
```

with:

```python
headers = tuple(self._header_text(column) for column in render_columns)
```

Add:

```python
def _header_text(self, column: DataGridColumn) -> str:
    if self._sort_state is None or self._sort_state[0] != column.key:
        return column.header
    marker = "^" if self._sort_state[1] == "asc" else "v"
    return f"{column.header} {marker}"
```

The existing `_grid_line()` width handling should truncate marker text naturally.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "cycle_sort or sort_header_markers" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): add datagrid sort cycling"
```

### Task 7: Multi-Control Filter/Sort Example

**Files:**
- Modify: `examples/tui/60_widgets_datagrid_large_dataset.py`
- Test: `tests/tui/test_widgets_data_grid.py`

- [ ] **Step 1: Write failing example tests**

Add:

```python
def test_widgets_datagrid_large_dataset_filter_bar_and_sort() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")
    app = namespace["LargeDataGridExampleApp"]()
    app.render(RenderConstraints(width=120, max_height=24))

    app._apply_filters(search="STK01", sector="AI", status="active", min_price_text="50")
    assert app.grid.filtered_row_count < namespace["ROW_COUNT"]

    app.grid.activate_cell(str(app.grid.active_row_key), "price")
    assert app.handle_input(InputEvent(kind="key", key="s")) is True
    assert app.grid.sort_state == ("price", "asc")

    lines = plain_lines(app, width=120, height=24)
    assert any("Search:" in line and "Sector:" in line for line in lines)
    assert any("Sort Price asc" in line for line in lines)
```

Add invalid numeric behavior:

```python
def test_widgets_datagrid_large_dataset_invalid_min_price_preserves_last_valid_filter() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")
    app = namespace["LargeDataGridExampleApp"]()

    app._apply_filters(min_price_text="100")
    before = app.grid.view_row_keys
    app._apply_filters(min_price_text="abc")

    assert app.grid.view_row_keys == before
    assert "Min price" in app.status
    assert "filters unchanged" in app.status
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "filter_bar_and_sort or invalid_min_price" -q
```

Expected: FAIL.

- [ ] **Step 3: Add filter controls and focus order**

Add `TextInput` fields:

- `search_input`
- `sector_input`
- `status_input`
- `min_price_input`
- existing `goto_input`

Focus order:

```python
FOCUS_ORDER = ("grid", "search", "sector", "status", "min_price", "goto")
```

Input behavior:

- `Tab` / `Shift+Tab` move among controls.
- `Ctrl+G` focuses `goto`.
- `Esc` from inputs returns to grid without clearing values.
- focused inputs own printable text and Backspace.
- `q` quits only from grid focus.
- `s` sorts only from grid focus.

- [ ] **Step 4: Add combined predicate builder**

Implement:

```python
def _apply_filters(
    self,
    *,
    search: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    min_price_text: str | None = None,
) -> None:
    if search is not None:
        self.search_input.set_text(search)
    if sector is not None:
        self.sector_input.set_text(sector)
    if status is not None:
        self.status_input.set_text(status)
    if min_price_text is not None:
        self.min_price_input.set_text(min_price_text)
    # Then parse/filter using the current input values.
```

Use `set_filter_query(search, columns=("id", "symbol", "sector", "status"))`.

Build predicate from sector/status/min price:

```python
def predicate(row: DataGridRowView) -> bool:
    values = row.values
    if sector_value and sector_value.casefold() not in str(values["sector"]).casefold():
        return False
    if status_value and status_value.casefold() not in str(values["status"]).casefold():
        return False
    if min_price is not None and float(values["price"]) < min_price:
        return False
    return True
```

For invalid min price:

- preserve last valid numeric value
- set red error status text
- do not change the numeric clause

- [ ] **Step 5: Add sort footer/status**

Footer should include:

```text
Rows X-Y of N filtered from 2,000 | Page P/T | Sort Price asc | Tab filters | s sort | q quit
```

Use helper:

```python
def _sort_status(app: LargeDataGridExampleApp) -> str:
    if app.grid.sort_state is None:
        return "Sort none"
    column_key, direction = app.grid.sort_state
    column = _column_by_key(app.grid, column_key)
    label = column.header if column is not None else column_key
    return f"Sort {label} {direction}"
```

- [ ] **Step 6: Run focused example tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -k "large_dataset" -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add examples/tui/60_widgets_datagrid_large_dataset.py tests/tui/test_widgets_data_grid.py
git commit -m "feat(tui): demonstrate datagrid filter and sort controls"
```

### Task 8: Docs And Reference Coverage

**Files:**
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
- Test: `tests/tui/test_widgets_reference_docs.py`

- [ ] **Step 1: Inspect existing docs layout**

Run:

```bash
rg -n "DataGrid|data-grid|ui-parts" docs/internals/architecture/tui/native-terminal-core/ui-parts tests/tui/test_widgets_reference_docs.py
```

- [ ] **Step 2: Write or update docs**

Document:

- `row_keys` vs `view_row_keys`
- query filter and predicate filter
- 1-n filter controls are page composition
- case sensitivity
- `DataGridRowView`
- activation under filtering
- pinned row behavior
- sort cycle and header markers
- large-data example command

- [ ] **Step 3: Run docs/reference tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_reference_docs.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md tests/tui/test_widgets_reference_docs.py
git commit -m "docs(tui): document datagrid filtering"
```

### Task 9: Final Verification And PR

**Files:**
- No direct code edits unless verification finds a defect.

- [ ] **Step 1: Run focused full DataGrid suite**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
```

Expected: PASS.

- [ ] **Step 2: Run import/reference tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_reference_docs.py tests/tui/test_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 3: Run Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py examples/tui/60_widgets_datagrid_large_dataset.py
```

Expected: PASS.

- [ ] **Step 4: Optional manual example check**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev python examples/tui/60_widgets_datagrid_large_dataset.py
```

Manual checks:

- Tab reaches each filter control and page input.
- Typing search filters rows and updates counts.
- Ctrl-G focuses page input.
- Page jumps stay inside filtered rows.
- `s` cycles sort when grid owns focus.
- Invalid Min price is red and preserves last valid filter.
- `q` does not quit while an input owns text.

- [ ] **Step 5: Push and create PR**

Do not prefix the PR title with `[codex]`.

```bash
git status --short --branch
git push -u origin HEAD
gh pr create --title "Add DataGrid filtering and sort controls" --body "Summary:
- add DataGrid query/predicate filtering
- add filtered large-data controls
- add sort cycling and header markers

Validation:
- uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_data_grid.py -q
- uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_reference_docs.py tests/tui/test_import_boundaries.py -q
- uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/data_grid.py tests/tui/test_widgets_data_grid.py examples/tui/60_widgets_datagrid_large_dataset.py"
```

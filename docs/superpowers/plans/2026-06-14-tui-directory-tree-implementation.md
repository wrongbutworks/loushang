# TUI DirectoryTree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `DirectoryTree` widget that adapts filesystem paths into the existing `TreeView` navigation/rendering model without introducing workspace, git, or coding-product assumptions.

**Architecture:** Implement `DirectoryTree` as a generic widget in `loushang.tui.ui_parts.widgets.directory_tree`. It validates explicit lexical absolute paths, synchronously scans a bounded admitted tree model, maps real and synthetic filesystem rows into `TreeNode` values, delegates navigation/rendering to `TreeView`, and translates activation into `DirectoryTreeSelect`. Product pages later choose workspace roots and ignore rules; this slice stays entirely in the TUI package.

**Tech Stack:** Python 3.11+, `pathlib.Path`, dataclasses with slots, existing `TreeNode` / `TreeView`, `InputEvent`, `InputIntent`, `RenderConstraints`, `ThemeResolver`, pytest, widget playback helpers, Ruff.

---

## Prerequisites

- Base the implementation branch on `main` after PR #196, or another branch that contains `docs/superpowers/specs/2026-06-14-tui-directory-tree-design.md` with the resolved lexical-path and symlink decisions.
- Do not migrate coding pages or settings pages in this plan.
- Do not add workspace defaults, git-root discovery, or `.gitignore` parsing to `loushang.tui`.

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-14-tui-directory-tree-design.md`
- Existing widget to compose:
  - `src/loushang/tui/ui_parts/widgets/tree.py`
  - `tests/tui/test_widgets_tree.py`
- Export patterns:
  - `src/loushang/tui/ui_parts/widgets/__init__.py`
  - `src/loushang/tui/ui_parts/__init__.py`
  - `src/loushang/tui/__init__.py`
- Example/playback patterns:
  - `examples/tui/49_widgets_tree.py`
  - `tests/tui/widget_example_playback.py`
- UI part inventory:
  - `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/directory_tree.py`
  - Owns `DirectoryTreeEntry`, `DirectoryTreeSelect`, `DirectoryTree`, path normalization, scan model, TreeView adaptation, reload, expansion methods, input translation, and rendering delegation.
- `tests/tui/test_widgets_directory_tree.py`
  - Focused unit tests for API exports, path contracts, scanning, filters, expansion, selection, reload, max-entry sentinels, symlinks, errors, theme reuse, and example playback.
- `examples/tui/57_widgets_directory_tree.py`
  - Generic example with a deterministic temporary directory, explicit root, selection status, hidden toggle, reload, and `q` quit support.
- `docs/internals/architecture/tui/native-terminal-core/ui-parts/directory-tree.md`
  - Long-term internal UI part documentation after implementation.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `DirectoryTree`, `DirectoryTreeEntry`, `DirectoryTreeSelect`, `DirectoryTreeRealKind`, `DirectoryTreeEntryKind`, `PathFilter`, and `PathSortKey`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export the same public names.
- `src/loushang/tui/__init__.py`
  - Re-export the same public names.
- `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
  - Add DirectoryTree to the Lists inventory.

Do not modify:

- `src/loushang/coding/**`
- `TreeView` behavior unless a failing DirectoryTree test exposes a genuine reusable bug.
- Theme token definitions beyond using existing `widget.tree.*` tokens.

## Implementation Notes

Use these internal conventions so the implementation stays aligned with the spec:

- Store public paths as normalized absolute lexical `Path` objects. Reject relative paths and any public path input whose parts contain `".."`.
- Validate under-root membership with `path.relative_to(root_path)` against lexical paths. Do not expose or compare public values through `Path.resolve()`.
- The only symlink traversal exception is the root itself. Descendant symlink directories are selectable directory leaves and must not be scanned for children.
- Build a private admitted model before creating `TreeNode` objects. A practical shape is:

```python
@dataclass(frozen=True, slots=True)
class _DirectoryModelNode:
    entry: DirectoryTreeEntry
    tree_value: str
    children: tuple["_DirectoryModelNode", ...] = ()
    traversable_directory: bool = False
```

- Use deterministic, collision-free private `TreeView` values. POSIX filenames
  cannot contain NUL, so prefix generated values with `"\0"`:
  - real rows: `f"\0real:{path.as_posix()}"`
  - synthetic rows: `f"\0synthetic:{parent.as_posix()}:{kind}:{index}"`
- Keep these private indexes:
  - `_value_to_entry: dict[str, DirectoryTreeEntry]`
  - `_path_to_value: dict[Path, str]`
  - `_traversable_paths: set[Path]`
  - `_tree: TreeView`
- Derive public properties from `self._tree.visible_values` and `self._tree.expanded_value_set`, not from stale cached flattening.
- Treat root unreadability differently from missing/non-directory construction:
  - missing/non-directory root raises during construction
  - unreadable root construction creates the single disabled root error model
  - reload root invalidation always creates the single disabled root error model without raising

---

### Task 1: Public API, Exports, And Lexical Path Contracts

**Files:**
- Create: `tests/tui/test_widgets_directory_tree.py`
- Create: `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`

- [ ] **Step 1: Write failing API/export/path tests**

Create `tests/tui/test_widgets_directory_tree.py` with shared helpers and these initial tests:

```python
from __future__ import annotations

import ast
import inspect
import runpy
import shutil
from pathlib import Path
from typing import Any

import pytest

from loushang.tui import (
    CursorDeclaration,
    DirectoryTree,
    DirectoryTreeEntry,
    DirectoryTreeEntryKind,
    DirectoryTreeRealKind,
    DirectoryTreeSelect,
    InputEvent,
    PathFilter,
    PathSortKey,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
)
from loushang.tui.ui_parts import DirectoryTree as UiDirectoryTree
from loushang.tui.ui_parts.widgets import DirectoryTree as WidgetDirectoryTree
from tests.tui.widget_example_playback import play_example


def render_plain(part: Any, *, width: int = 50, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def test_directory_tree_is_reexported_from_public_modules(tmp_path: Path) -> None:
    tree = DirectoryTree(root=tmp_path)

    assert DirectoryTree is UiDirectoryTree
    assert DirectoryTree is WidgetDirectoryTree
    assert DirectoryTreeEntry(path=tmp_path, kind="directory", label=tmp_path.name).path == tmp_path
    assert DirectoryTreeSelect(path=tmp_path, kind="directory").kind == "directory"
    assert DirectoryTreeRealKind is not None
    assert DirectoryTreeEntryKind is not None
    assert PathFilter is not None
    assert PathSortKey is not None
    assert tree.root_path == tmp_path


def test_directory_tree_requires_explicit_absolute_root(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        DirectoryTree()  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="absolute"):
        DirectoryTree(root=Path("relative"))

    with pytest.raises(ValueError, match=r"\.\."):
        DirectoryTree(root=tmp_path / ".." / tmp_path.name)


def test_directory_tree_rejects_missing_and_file_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        DirectoryTree(root=tmp_path / "missing")

    file_root = tmp_path / "file.txt"
    file_root.write_text("data", encoding="utf-8")

    with pytest.raises(ValueError, match="directory"):
        DirectoryTree(root=file_root)


def test_directory_tree_rejects_relative_outside_and_dotdot_public_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=Path("relative"))
    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=tmp_path / "outside")
    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=root / ".." / "root")
    with pytest.raises(ValueError):
        DirectoryTree(root=root, expanded_paths=(Path("relative"),))


def test_directory_tree_tui_widget_has_no_coding_imports() -> None:
    import loushang.tui.ui_parts.widgets.directory_tree as module

    source = ast.parse(inspect.getsource(module))
    imports: list[str] = []
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not any(name == "loushang.coding" or name.startswith("loushang.coding.") for name in imports)
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL on import because `DirectoryTree` is not exported yet.

- [ ] **Step 3: Implement public dataclasses, constructor validation, root properties, and exports**

Create `directory_tree.py` with the public API and minimal renderable skeleton:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver

DirectoryTreeRealKind = Literal["directory", "file"]
DirectoryTreeEntryKind = Literal["directory", "file", "empty", "error", "sentinel"]


@dataclass(frozen=True, slots=True)
class DirectoryTreeEntry:
    path: Path | None
    kind: DirectoryTreeEntryKind
    label: str
    disabled: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class DirectoryTreeSelect:
    path: Path
    kind: DirectoryTreeRealKind


PathFilter = Callable[[Path], bool]
PathSortKey = Callable[[Path], object]


@dataclass(init=False, slots=True)
class DirectoryTree:
    root: str | Path
    show_hidden: bool = False
    path_filter: PathFilter | None = None
    ignore_matcher: PathFilter | None = None
    sort_key: PathSortKey | None = None
    empty_text: str = "No files"
    max_entries: int = 2000
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _root_path: Path = field(init=False, repr=False)
    _active_path: Path | None = field(default=None, init=False, repr=False)
    _initial_expanded_paths: tuple[Path, ...] = field(default=(), init=False, repr=False)

    def __init__(
        self,
        root: str | Path,
        active_path: str | Path | None = None,
        expanded_paths: Sequence[str | Path] = (),
        show_hidden: bool = False,
        path_filter: PathFilter | None = None,
        ignore_matcher: PathFilter | None = None,
        sort_key: PathSortKey | None = None,
        empty_text: str = "No files",
        max_entries: int = 2000,
        wrap: bool = True,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self.root = root
        self.show_hidden = show_hidden
        self.path_filter = path_filter
        self.ignore_matcher = ignore_matcher
        self.sort_key = sort_key
        self.empty_text = empty_text
        self.max_entries = max(1, max_entries)
        self.wrap = wrap
        self.theme = theme
        self.focused = focused
        self._root_path = _normalize_absolute_lexical(Path(root), label="root")
        if not self._root_path.exists():
            raise ValueError(f"DirectoryTree root is missing: {self._root_path}")
        if not self._root_path.is_dir():
            raise ValueError(f"DirectoryTree root is not a directory: {self._root_path}")
        self._active_path = (
            None if active_path is None else self._normalize_under_root(Path(active_path), label="active_path")
        )
        self._initial_expanded_paths = tuple(
            self._normalize_under_root(Path(path), label="expanded_paths")
            for path in expanded_paths
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def active_path(self) -> Path | None:
        return self._active_path

    def _normalize_under_root(self, path: Path, *, label: str) -> Path:
        normalized = _normalize_absolute_lexical(path, label=label)
        try:
            normalized.relative_to(self._root_path)
        except ValueError as exc:
            raise ValueError(f"{label} must be under DirectoryTree root") from exc
        return normalized

    def render(self, constraints: RenderConstraints) -> RenderResult:
        label = self._root_path.name or str(self._root_path)
        return RenderResult.from_lines([RenderLine(label)][: constraints.max_height], constraints=constraints)
```

Also add `_normalize_absolute_lexical()` and update the three export modules.

- [ ] **Step 4: Run tests and verify Task 1 passes**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS for the initial tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/loushang/tui/ui_parts/widgets/directory_tree.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_directory_tree.py
git commit -m "feat(tui): add directory tree api skeleton"
```

---

### Task 2: Scan Model, Sorting, Filtering, And Visible Entries

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add failing scan and filtering tests**

Append tests that build a small filesystem fixture:

```python
def build_tree_fixture(root: Path) -> None:
    (root / "src" / "widgets").mkdir(parents=True)
    (root / "src" / "main.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text("", encoding="utf-8")
    (root / ".env").write_text("", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "artifact.bin").write_text("", encoding="utf-8")
    (root / "empty").mkdir()


def test_directory_tree_scans_root_directory_first_and_exposes_visible_entries(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)

    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "src", tmp_path / "empty"))

    assert [entry.label for entry in tree.visible_entries] == [
        tmp_path.name,
        "build",
        "empty",
        "No files",
        "src",
        "widgets",
        "main.py",
        "README.md",
    ]
    assert tree.visible_paths == (
        tmp_path,
        tmp_path / "build",
        tmp_path / "empty",
        tmp_path / "src",
        tmp_path / "src" / "widgets",
        tmp_path / "src" / "main.py",
        tmp_path / "README.md",
    )


def test_directory_tree_hides_hidden_paths_by_default_and_can_show_them(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)

    hidden = DirectoryTree(root=tmp_path)
    shown = DirectoryTree(root=tmp_path, show_hidden=True)

    assert tmp_path / ".env" not in hidden.visible_paths
    assert tmp_path / ".env" in shown.visible_paths


def test_directory_tree_filter_ignore_and_sort_callbacks_receive_absolute_lexical_paths(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    seen_filter: list[Path] = []
    seen_ignore: list[Path] = []
    seen_sort: list[Path] = []

    def include(path: Path) -> bool:
        seen_filter.append(path)
        return path.name != "build"

    def ignore(path: Path) -> bool:
        seen_ignore.append(path)
        return path.name == "README.md"

    def sort_key(path: Path) -> object:
        seen_sort.append(path)
        return path.name

    tree = DirectoryTree(root=tmp_path, path_filter=include, ignore_matcher=ignore, sort_key=sort_key)

    assert tmp_path / "build" not in tree.visible_paths
    assert tmp_path / "README.md" not in tree.visible_paths
    assert all(path.is_absolute() and path.is_relative_to(tmp_path) for path in seen_filter)
    assert all(path.is_absolute() and path.is_relative_to(tmp_path) for path in seen_ignore)
    assert all(path.is_absolute() and path.is_relative_to(tmp_path) for path in seen_sort)


def test_directory_tree_does_not_descend_into_filtered_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_tree_fixture(tmp_path)
    original_iterdir = Path.iterdir

    def fail_if_build_is_traversed(path: Path):
        if path == tmp_path / "build":
            raise AssertionError("filtered directory was traversed")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_if_build_is_traversed)

    tree = DirectoryTree(root=tmp_path, path_filter=lambda path: path.name != "build")

    assert tmp_path / "build" not in tree.visible_paths
```

- [ ] **Step 2: Run tests and verify the expected scan failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL because `visible_entries`, `visible_paths`, filtering, sorting, and child scanning are not implemented.

- [ ] **Step 3: Implement admitted scan model and visible properties**

Implement:

- `_DirectoryModelNode`
- `_ScanBudget(remaining: int)`
- `_real_value(path: Path) -> str`
- `_synthetic_value(parent: Path, kind: str, index: int) -> str`
- `_build_model()`
- `_scan_children(parent: Path, budget: _ScanBudget, *, is_root: bool = False)`
- `_passes_filters(path: Path) -> bool`
- `_entry_kind(path: Path) -> DirectoryTreeRealKind`
- `visible_entries`
- `visible_paths`

Core scan rules:

```python
children = tuple(parent.iterdir())
visible = [child for child in children if self._passes_filters(child)]
directories = [path for path in visible if path.is_dir()]
files = [path for path in visible if not path.is_dir()]
groups = (sorted(directories, key=self._sort_tuple), sorted(files, key=self._sort_tuple))
for child in (*groups[0], *groups[1]):
    if budget.remaining <= 0:
        synthetic.append(_sentinel(parent))
        break
    budget.remaining -= 1
    if child.is_dir() and not _is_descendant_symlink_directory(child):
        child_children = self._scan_children(child, budget)
    else:
        child_children = ()
```

After scanning, create `TreeNode` values from the model and instantiate `TreeView` with root expanded by default. Keep root outside the `max_entries` budget.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS for Task 1 and Task 2 tests.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/loushang/tui/ui_parts/widgets/directory_tree.py tests/tui/test_widgets_directory_tree.py
git commit -m "feat(tui): scan directory tree entries"
```

---

### Task 3: Expansion, Active Path, Reload, And Error Models

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add failing state and reload tests**

Append tests:

```python
def assert_root_error_model(tree: DirectoryTree, root: Path) -> None:
    assert len(tree.visible_entries) == 1
    assert tree.visible_entries[0].kind == "error"
    assert tree.visible_entries[0].path == root
    assert tree.visible_entries[0].disabled is True
    assert tree.visible_paths == ()
    assert tree.active_path is None
    assert tree.expanded_path_set == frozenset()


def test_directory_tree_initial_active_and_expanded_paths_repair(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)

    tree = DirectoryTree(
        root=tmp_path,
        active_path=tmp_path / "missing.py",
        expanded_paths=(tmp_path / "src", tmp_path / "README.md", tmp_path / "missing"),
    )

    assert tree.active_path == tmp_path
    assert tree.expanded_path_set == frozenset({tmp_path, tmp_path / "src"})


def test_directory_tree_expansion_methods_validate_paths_and_repair_active(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(
        root=tmp_path,
        active_path=tmp_path / "src" / "widgets",
        expanded_paths=(tmp_path / "src",),
    )

    assert tree.is_expanded(tmp_path / "src") is True
    assert tree.expand_path(tmp_path / "src") is False
    assert tree.collapse_path(tmp_path / "src") is True
    assert tree.active_path == tmp_path / "src"
    assert tree.toggle_path(tmp_path / "src") is True
    assert tree.toggle_path(tmp_path / "src") is True
    assert tree.expand_path(tmp_path / "README.md") is False

    for method_name in ("expand_path", "collapse_path", "toggle_path", "is_expanded"):
        method = getattr(tree, method_name)
        with pytest.raises(ValueError):
            method(Path("relative"))
        with pytest.raises(ValueError):
            method(tmp_path.parent / "outside")
        with pytest.raises(ValueError):
            method(tmp_path / ".." / tmp_path.name)


def test_directory_tree_reload_preserves_valid_state_and_repairs_removed_paths(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path, active_path=tmp_path / "src" / "main.py", expanded_paths=(tmp_path / "src",))

    assert tree.active_path == tmp_path / "src" / "main.py"
    (tmp_path / "src" / "main.py").unlink()
    tree.reload()

    assert tree.active_path in tree.visible_paths
    assert tmp_path / "src" in tree.expanded_path_set
    assert tmp_path / "src" / "main.py" not in tree.visible_paths


def test_directory_tree_reload_root_invalidation_uses_disabled_error_model(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path)

    shutil.rmtree(tmp_path)
    tree.reload()

    assert_root_error_model(tree, tmp_path)


def test_directory_tree_reload_root_becomes_file_uses_disabled_error_model(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path)

    shutil.rmtree(tmp_path)
    tmp_path.write_text("now a file", encoding="utf-8")
    tree.reload()

    assert_root_error_model(tree, tmp_path)


def test_directory_tree_reload_unreadable_root_uses_disabled_error_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path)
    original_iterdir = Path.iterdir

    def fail_root(path: Path):
        if path == tmp_path:
            raise PermissionError("blocked")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_root)

    tree.reload()

    assert_root_error_model(tree, tmp_path)


def test_directory_tree_unreadable_root_construction_uses_disabled_error_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_iterdir = Path.iterdir

    def fail_root(path: Path):
        if path == tmp_path:
            raise PermissionError("blocked")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_root)

    tree = DirectoryTree(root=tmp_path)

    assert_root_error_model(tree, tmp_path)
```

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL around state repair, expansion methods, reload, or error models.

- [ ] **Step 3: Implement state synchronization**

Implement:

- `active_path` property backed by `_active_path: Path | None`
- `expanded_path_set`
- `focus()` / `blur()` forwarding to the internal `TreeView`
- `expand_path(path)`, `collapse_path(path)`, `toggle_path(path)`, `is_expanded(path)`
- `reload()`
- `_rebuild_tree(preferred_active: Path | None, preferred_expanded: Iterable[Path])`
- `_sync_public_state_from_tree()`
- `_root_error_model(message: str)`

Important details:

- Root is always included in desired expanded paths for valid roots.
- Filter initial expanded paths through `_path_to_value` and `_traversable_paths`.
- Filter active path through `_path_to_value`; otherwise let `TreeView` fall back.
- After every `TreeView` input or expansion call, call `_sync_public_state_from_tree()`.
- For method paths under root but missing/filtered/hidden/omitted/files, return `False` instead of raising.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS for Tasks 1-3.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/loushang/tui/ui_parts/widgets/directory_tree.py tests/tui/test_widgets_directory_tree.py
git commit -m "feat(tui): manage directory tree state"
```

---

### Task 4: Input Translation, Rendering Delegation, And Theme Reuse

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add failing input/render/theme tests**

Append tests:

```python
def test_directory_tree_activation_returns_structured_file_and_directory_selection(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "src",), active_path=tmp_path / "src")
    tree.focus()

    assert tree.handle_input(InputEvent(kind="key", key="enter")) == DirectoryTreeSelect(
        path=tmp_path / "src",
        kind="directory",
    )
    assert tree.handle_input(InputEvent(kind="key", key="down")) is True
    assert tree.handle_input(InputEvent(kind="key", key="down")) is True
    assert tree.handle_input(InputEvent(kind="key", key="space")) == DirectoryTreeSelect(
        path=tmp_path / "src" / "main.py",
        kind="file",
    )
    assert tree.handle_input(InputEvent(kind="text", text=" ")) == DirectoryTreeSelect(
        path=tmp_path / "src" / "main.py",
        kind="file",
    )


def test_directory_tree_does_not_leak_treeview_input_intent(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path)
    tree.focus()

    result = tree.handle_input(InputEvent(kind="key", key="enter"))

    assert isinstance(result, DirectoryTreeSelect)
    assert getattr(result, "kind", "") == "directory"


def test_directory_tree_renders_through_treeview_and_declares_cursor(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    tree = DirectoryTree(root=tmp_path, active_path=tmp_path / "src")
    tree.focus()

    lines = render_plain(tree, width=40, height=5)
    result = tree.render(RenderConstraints(width=40, max_height=5))

    assert lines[0].startswith("  - ")
    assert any("> " in line and "src" in line for line in lines)
    assert result.cursor == CursorDeclaration(row=3, column=0)


def test_directory_tree_reuses_tree_theme_tokens(tmp_path: Path) -> None:
    build_tree_fixture(tmp_path)
    theme = ThemeResolver(
        defaults={
            "widget.tree.row": {"color": "white"},
            "widget.tree.focus": {"bold": True, "color": "green"},
            "widget.tree.disabled": {"dim": True},
        }
    )
    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "empty",), active_path=tmp_path / "empty", theme=theme)
    tree.focus()

    raw = tuple(line.text for line in tree.render(RenderConstraints(width=60, max_height=8)).lines)

    assert any(line.startswith("\x1b[1;32m> ") and "empty" in line for line in raw)
    assert any(line.startswith("\x1b[2m") and "No files" in line for line in raw)
```

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL until `handle_input()` translates select intents and `render()` delegates to `TreeView`.

- [ ] **Step 3: Implement input and render delegation**

Implement:

```python
def handle_input(self, event: object) -> DirectoryTreeSelect | bool | None:
    result = self._tree.handle_input(event)
    self._sync_public_state_from_tree()
    if getattr(result, "kind", "") != "select":
        return result if result in (True, False, None) else None
    entry = self._entry_for_value(getattr(result, "text", ""))
    if entry is None or entry.disabled or entry.path is None or entry.kind not in ("directory", "file"):
        return None
    return DirectoryTreeSelect(path=entry.path, kind=entry.kind)


def render(self, constraints: RenderConstraints) -> RenderResult:
    return self._tree.render(constraints)
```

Ensure `DirectoryTree.focus()` sets both `self.focused` and `self._tree.focused`; `blur()` clears both.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS for Tasks 1-4.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/loushang/tui/ui_parts/widgets/directory_tree.py tests/tui/test_widgets_directory_tree.py
git commit -m "feat(tui): translate directory tree input"
```

---

### Task 5: Max-Entry Sentinels, Symlinks, And Runtime Scan Errors

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add failing edge-case tests**

Append tests:

```python
def test_directory_tree_max_entries_inserts_sentinels_and_counts_collapsed_descendants(tmp_path: Path) -> None:
    (tmp_path / "alpha" / "nested").mkdir(parents=True)
    (tmp_path / "alpha" / "nested" / "deep.txt").write_text("", encoding="utf-8")
    (tmp_path / "beta").mkdir()
    (tmp_path / "gamma.txt").write_text("", encoding="utf-8")

    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "alpha", tmp_path / "alpha" / "nested"), max_entries=2)

    assert tmp_path in tree.visible_paths
    assert tmp_path / "alpha" in tree.visible_paths
    assert tmp_path / "alpha" / "nested" in tree.visible_paths
    assert tmp_path / "alpha" / "nested" / "deep.txt" not in tree.visible_paths
    assert any(entry.kind == "sentinel" and entry.disabled for entry in tree.visible_entries)


def test_directory_tree_max_entries_below_one_normalizes_to_one(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()

    tree = DirectoryTree(root=tmp_path, max_entries=0)

    assert tmp_path in tree.visible_paths
    assert tmp_path / "alpha" in tree.visible_paths
    assert tmp_path / "beta" not in tree.visible_paths
    assert any(entry.kind == "sentinel" for entry in tree.visible_entries)


def test_directory_tree_nested_sentinel_can_exist_with_parent_sentinel(tmp_path: Path) -> None:
    (tmp_path / "alpha" / "a").mkdir(parents=True)
    (tmp_path / "alpha" / "b").mkdir()
    (tmp_path / "omega").mkdir()

    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "alpha",), max_entries=2)

    sentinels = [entry for entry in tree.visible_entries if entry.kind == "sentinel"]
    assert len(sentinels) == 2
    assert all(entry.path is None for entry in sentinels)
    assert all(entry.disabled for entry in sentinels)
    assert all(entry.path not in tree.visible_paths for entry in sentinels)


def test_directory_tree_root_symlink_is_traversed_but_public_paths_stay_lexical(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "child.txt").write_text("", encoding="utf-8")
    link = tmp_path / "link-root"
    link.symlink_to(target, target_is_directory=True)

    tree = DirectoryTree(root=link)

    assert tree.root_path == link
    assert link / "child.txt" in tree.visible_paths
    assert target / "child.txt" not in tree.visible_paths


def test_directory_tree_descendant_symlink_directory_is_selectable_leaf(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "inside.txt").write_text("", encoding="utf-8")
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)

    tree = DirectoryTree(root=tmp_path, expanded_paths=(link,), active_path=link)
    tree.focus()

    assert link in tree.visible_paths
    assert link / "inside.txt" not in tree.visible_paths
    assert tree.expand_path(link) is False
    assert tree.handle_input(InputEvent(kind="key", key="enter")) == DirectoryTreeSelect(path=link, kind="directory")


def test_directory_tree_runtime_scan_error_renders_disabled_error_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_tree_fixture(tmp_path)
    original_iterdir = Path.iterdir

    def fail_src(path: Path):
        if path == tmp_path / "src":
            raise PermissionError("blocked")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_src)

    tree = DirectoryTree(root=tmp_path, expanded_paths=(tmp_path / "src",))

    assert any(entry.kind == "error" and entry.disabled and entry.path == tmp_path / "src" for entry in tree.visible_entries)
```

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL until sentinel placement, symlink policy, and runtime error rows are complete.

- [ ] **Step 3: Implement edge semantics**

Add or tighten:

- global `max_entries` budget below root, normalized to at least 1
- per-directory sentinel insertion when a child list still has candidates but budget is exhausted
- recursive eager scan of collapsed descendants
- root symlink traversal while preserving lexical root paths
- descendant symlink directory as non-traversable directory leaf
- non-root `PermissionError`, `FileNotFoundError`, and `OSError` as disabled error child rows
- root unreadability as the single root-level disabled error model

Use lexical child paths when scanning a root symlink. Do not replace them with resolved target paths.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS for all focused DirectoryTree tests.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/loushang/tui/ui_parts/widgets/directory_tree.py tests/tui/test_widgets_directory_tree.py
git commit -m "feat(tui): handle directory tree edge cases"
```

---

### Task 6: Example 57 And Playback Coverage

**Files:**
- Create: `examples/tui/57_widgets_directory_tree.py`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add failing example import/playback tests**

Append tests:

```python
def test_widgets_directory_tree_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/57_widgets_directory_tree.py", run_name="__test__")

    build_app = namespace["build_app"]
    app = build_app()
    result = app.render(RenderConstraints(width=90, max_height=24))

    assert callable(build_app)
    assert result.lines


def test_widgets_directory_tree_example_playback_selects_and_toggles_hidden_files() -> None:
    frames = play_example(
        "examples/tui/57_widgets_directory_tree.py",
        events=(
            ("down", InputEvent(kind="key", key="down")),
            ("enter select", InputEvent(kind="key", key="enter")),
            ("hidden toggle", InputEvent(kind="text", text="h")),
            ("reload", InputEvent(kind="text", text="r")),
        ),
        width=90,
        height=24,
    )

    assert "Directory Tree" in frames[0].lines[0]
    assert any("Selected:" in line for line in frames[2].lines)
    assert any(".env" in line for line in frames[3].lines)
    assert any("Reloaded" in line for line in frames[4].lines)
```

- [ ] **Step 2: Run tests and verify example is missing**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: FAIL because `examples/tui/57_widgets_directory_tree.py` does not exist.

- [ ] **Step 3: Implement the example**

Create an example app that:

- builds a deterministic temporary root with directories, files, hidden file, and empty directory
- stores the temporary directory object on the app instance so files remain alive during playback
- constructs `DirectoryTree(root=self.root, show_hidden=self.show_hidden, expanded_paths=(self.root, self.root / "src"))`
- renders title, tree, selected status, root path, and footer controls
- handles:
  - `q`: quit in `main()`
  - `h`: toggle `show_hidden` and rebuild tree
  - `r`: call `reload()` and show "Reloaded"
  - all other input: delegate to `DirectoryTree.handle_input()`

Keep the example generic. Do not use the repository root, process cwd, workspace state, or coding session state.

- [ ] **Step 4: Run example tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS including playback tests.

- [ ] **Step 5: Manually smoke the example**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev python examples/tui/57_widgets_directory_tree.py
```

Manual checks:

- initial screen shows a tree rooted at a temporary directory
- up/down moves row focus
- left/right collapse and expand directories
- enter/space selects a file or directory and updates status
- `h` shows/hides `.env`
- `r` reloads
- `q` exits

- [ ] **Step 6: Commit Task 6**

```bash
git add examples/tui/57_widgets_directory_tree.py tests/tui/test_widgets_directory_tree.py
git commit -m "test(tui): cover directory tree example playback"
```

---

### Task 7: Internal Docs, Public Inventory, And Final Verification

**Files:**
- Create: `docs/internals/architecture/tui/native-terminal-core/ui-parts/directory-tree.md`
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
- Modify: `tests/tui/test_widgets_directory_tree.py`

- [ ] **Step 1: Add focused docs assertions if this repo has doc smoke tests for UI parts**

Check current doc tests:

```bash
rg -n "ui-parts|tui-widgets|directory-tree" tests docs
```

If no local doc smoke test pattern exists for UI part inventory, skip adding a test and document the manual check in the PR body.

- [ ] **Step 2: Write internal docs**

Create `directory-tree.md` covering:

- purpose and non-goals
- explicit root contract
- lexical public paths
- filtering and ignore matcher ownership
- sorting and scan budget
- root symlink and descendant symlink behavior
- selection result
- reload behavior
- theme tokens reused from `TreeView`
- product integration boundary

- [ ] **Step 3: Update UI part inventory**

Modify `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`:

```markdown
| Lists | SelectList, [SearchableList](./searchable-list.md), [Table](./table.md), [TreeView](./tree.md), [DirectoryTree](./directory-tree.md) |
```

- [ ] **Step 4: Run focused verification**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS.

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/directory_tree.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_directory_tree.py examples/tui/57_widgets_directory_tree.py
```

Expected: PASS.

- [ ] **Step 5: Run nearby regression tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py tests/tui/test_widgets_directory_tree.py -q
```

Expected: PASS.

- [ ] **Step 6: Run broader TUI tests if time permits**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS. If unrelated failures exist, capture exact failing tests and why they are unrelated before PR.

- [ ] **Step 7: Commit Task 7**

```bash
git add docs/internals/architecture/tui/native-terminal-core/ui-parts/directory-tree.md docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md tests/tui/test_widgets_directory_tree.py
git commit -m "docs(tui): document directory tree widget"
```

---

## Completion Checklist

- [ ] `DirectoryTree` is exported from `loushang.tui`, `loushang.tui.ui_parts`, and `loushang.tui.ui_parts.widgets`.
- [ ] `DirectoryTreeRealKind`, `DirectoryTreeEntryKind`, `DirectoryTreeEntry`, `DirectoryTreeSelect`, `PathFilter`, and `PathSortKey` are exported from the same public modules.
- [ ] Public path values are absolute lexical `Path` objects under the explicit root.
- [ ] Relative paths, outside-root paths, and `..` public path inputs are rejected.
- [ ] Root is always rendered and expanded for valid roots.
- [ ] Synthetic empty/error/sentinel rows appear in `visible_entries` and never in `visible_paths`.
- [ ] Activation returns `DirectoryTreeSelect | bool | None`, never internal `InputIntent`.
- [ ] `max_entries` applies to admitted real entries below root and inserts deterministic sentinels.
- [ ] Root symlinks are traversed while preserving lexical root paths.
- [ ] Descendant symlink directories are selectable leaves.
- [ ] No code under `loushang.tui` imports `loushang.coding` for this feature.
- [ ] Example 57 can be imported, played back, and manually exited with `q`.
- [ ] Focused and nearby regression tests pass.

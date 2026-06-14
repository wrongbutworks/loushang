# TUI DirectoryTree Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a stable generic `TreeView` for static hierarchical
data. It owns row focus, expand/collapse state, active-row repair, viewport
windowing, cursor declaration, theme tokens, and `InputIntent(kind="select")`
activation.

The next useful file-navigation slice should not make `TreeView` know about
files. Textual's prior art follows the same split: it has a generic `Tree` and
a filesystem-specific `DirectoryTree` that presents files and directories,
supports path filtering, and emits file/directory selection messages.
Reference: <https://textual.textualize.io/widgets/directory_tree/>.

For loushang, the generic TUI layer must also stay independent from the coding
product. A directory tree widget should not guess the workspace, current
session, git root, or ignore rules. Product code such as `loushang.coding.ui`
should pass those choices in.

## Problem

Callers can manually build `TreeNode` values from a filesystem, but each caller
would need to repeat:

- root path validation
- deterministic directory scanning
- directory-first sorting
- hidden file filtering
- path-to-tree-node value mapping
- file-vs-directory activation results
- refresh/reload behavior after filesystem changes
- guardrails for missing roots and permission errors

That repeated logic belongs in a small filesystem adapter widget/page layer.
It should reuse `TreeView` rather than fork tree navigation.

## Goals

- Add a generic TUI `DirectoryTree` capability on top of `TreeView`.
- Require callers to pass an explicit `root`.
- Keep workspace, coding session, git root, and `.gitignore` semantics out of
  `loushang.tui`.
- Support deterministic directory-first display of files and directories.
- Support optional hidden-path filtering.
- Support caller-provided path filtering and ignore matching.
- Return structured file/directory selection results with paths.
- Provide a refresh/reload hook for the whole tree.
- Keep the first implementation synchronous and bounded.
- Add focused tests, internal docs, and a small generic example.

## Non-Goals

- Do not default to `Path.cwd()`.
- Do not read coding session state.
- Do not find or assume a workspace.
- Do not find a git root.
- Do not parse `.gitignore` in `loushang.tui`.
- Do not add git status badges or file decorations in P0.
- Do not add async scanning, background workers, or incremental lazy loading in
  P0.
- Do not add search, multi-select, checkbox selection, inline rename, delete,
  copy, or drag/drop.
- Do not replace `TreeView`; `DirectoryTree` composes it.
- Do not migrate product coding pages in this slice.

## Package Scope

Generic reusable TUI code:

- `src/loushang/tui/ui_parts/widgets/directory_tree.py`
- public exports from:
  - `src/loushang/tui/ui_parts/widgets/__init__.py`
  - `src/loushang/tui/ui_parts/__init__.py`
  - `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_directory_tree.py`

Example:

- `examples/tui/57_widgets_directory_tree.py`

Long-term internal documentation after implementation:

- `docs/internals/architecture/tui/native-terminal-core/ui-parts/directory-tree.md`

Coding product integration is explicitly out of this TUI slice. A later code
lane or product slice can add a `FileExplorerPage` that chooses the workspace
root and passes ignore rules into the generic widget.

## Naming

Use `DirectoryTree`, not `FileTreeView`.

Reasons:

- The widget presents directories and files, not only files.
- It mirrors Textual's useful terminology.
- It makes the layer clear: this is a filesystem-specialized tree, while
  `TreeView` remains the generic tree widget.
- It avoids implying that this is a separate visual tree implementation.

Possible product pages may still use names such as `FileExplorerPage` or
`WorkspaceFilesPage`, but those should live outside `loushang.tui`.

## Public API

First slice:

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DirectoryTreeEntryKind = Literal["directory", "file"]

@dataclass(frozen=True, slots=True)
class DirectoryTreeEntry:
    path: Path
    kind: DirectoryTreeEntryKind
    label: str

@dataclass(frozen=True, slots=True)
class DirectoryTreeSelect:
    path: Path
    kind: DirectoryTreeEntryKind

PathFilter = Callable[[Path], bool]
PathSortKey = Callable[[Path], object]

@dataclass(slots=True)
class DirectoryTree:
    root: str | Path
    active_path: str | Path | None = None
    expanded_paths: Sequence[str | Path] = ()
    show_root: bool = True
    show_hidden: bool = False
    path_filter: PathFilter | None = None
    ignore_matcher: PathFilter | None = None
    sort_key: PathSortKey | None = None
    empty_text: str = "No files"
    max_entries: int = 2000
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
```

Required public methods and properties:

- `focus()` / `blur()`
- `handle_input(event)`
- `render(constraints)`
- `editor_input_target()` is not needed in P0
- `root_path: Path`
- `active_path: Path | None`
- `expanded_path_set: frozenset[Path]`
- `visible_paths: tuple[Path, ...]`
- `reload()`
- `expand_path(path)`, `collapse_path(path)`, `toggle_path(path)`
- `is_expanded(path)`

`DirectoryTree` may internally create `TreeNode` values from normalized path
strings, but the public API should expose `Path` objects rather than string node
values.

## Root Contract

`root` is required. It is normalized to an absolute `Path` during
construction.

Root behavior:

- missing root raises `ValueError`
- non-directory root raises `ValueError`
- unreadable root does not crash render; it produces an empty/error row in the
  tree body and records the error for selection/refresh tests

The widget never defaults to:

- `Path.cwd()`
- repository root
- workspace root
- coding session root

If product code wants workspace semantics, it passes `DirectoryTree(root=...)`
from the product layer.

## Filtering And Ignore Contract

Filtering is caller-controlled:

- `show_hidden=False` hides paths whose basename starts with `"."`.
- `path_filter(path)` is an inclusion predicate. `False` hides the path.
- `ignore_matcher(path)` is an exclusion predicate. `True` hides the path.

Evaluation order:

1. never filter out the required root itself
2. apply hidden filtering
3. apply `path_filter`
4. apply `ignore_matcher`

Directory traversal should not descend into directories hidden by any filter.

`.gitignore` support is intentionally not built into `DirectoryTree`. A coding
integration may build an ignore matcher from gitignore rules and pass it in:

```python
DirectoryTree(root=workspace_root, ignore_matcher=workspace_ignore_matcher)
```

This keeps TUI reusable for non-git and non-coding contexts.

## Sorting

Default sorting:

1. directories before files
2. case-insensitive name
3. original name as tie breaker

If `sort_key` is provided, it sorts within the directory/file groups. Directory
grouping remains stable unless a later spec explicitly allows callers to opt
out.

Sorting must be deterministic across platforms for tests. Symlinks should be
classified using `Path.is_dir()` with normal Python semantics in P0.

## Scan Model

P0 scan model is synchronous and eager for the visible model:

- Construct or reload scans the root subtree up to a conservative limit.
- The default limit should prevent pathological huge trees from blocking tests
  or demos.
- When the limit is reached, insert a disabled sentinel row such as
  `"more entries omitted"` under the affected directory.

This is intentionally simpler than lazy loading. Lazy loading can be a P1
extension once we have product usage.

`max_entries` is part of the P0 public API. Values below 1 are normalized to 1.
The count applies to scanned entries below the root; the required root itself
does not consume the limit.

## Selection Semantics

Activation should return a structured object:

```python
DirectoryTreeSelect(path=path, kind="file" | "directory")
```

`enter` and `space` activate the active visible path. Expand/collapse remains
owned by left/right keys through the underlying tree behavior.

Selection result rules:

- file rows return `kind="file"`
- directory rows return `kind="directory"`
- disabled sentinel/error rows return `None`

Directory activation does not implicitly expand/collapse in P0. This keeps
activation distinct from navigation and matches current `TreeView` behavior.

## Refresh Semantics

`reload()` rescans the whole root and repairs state:

- preserve expanded paths that still exist and are directories
- preserve active path if it still exists and remains visible/enabled
- otherwise fall back to the first visible enabled path

P0 does not watch the filesystem. Product code or examples call reload
explicitly.

Per-directory reload is deferred. `reload_path(path)` can be added later if a
product page needs it and tests can show a meaningful benefit over full reload.

## Error Handling

Expected filesystem errors should render as disabled rows rather than crashing:

- `PermissionError`
- `FileNotFoundError` for paths removed during scan
- `OSError` while reading directory entries

Root validation errors still fail fast during construction when the root itself
is invalid. Runtime errors under a valid root should be localized to the
affected directory.

## Theme Tokens

P0 should reuse underlying `TreeView` tokens:

| Token | Applies to |
| --- | --- |
| `widget.tree.row` | Normal enabled rows |
| `widget.tree.focus` | Active row while focused |
| `widget.tree.disabled` | Error/sentinel rows and other disabled rows |
| `widget.tree.empty` | Empty directory tree row |

Directory/file-specific styling is deferred. Adding tokens such as
`widget.directoryTree.directory`, `widget.directoryTree.file`, or
`widget.directoryTree.hidden` would require a clear row-style composition rule
with `TreeView` focus styling, so it should wait until product usage justifies
that complexity.

## Example Shape

`examples/tui/57_widgets_directory_tree.py` should build a temporary sample
directory under `/tmp` or use a deterministic fixture builder inside the
example. It should not default to the repository workspace.

The example should demonstrate:

- explicit root passed to `DirectoryTree`
- visible directory and file rows
- hidden-file toggle or filtering in a small static way
- selection status below the tree
- `q` quit support

If the example creates temporary files, it should do so in a safe temporary
directory and avoid modifying the repository.

## Product Integration Boundary

Future coding-layer integration should live outside this widget. For example:

```python
DirectoryTree(
    root=session.workspace_root,
    ignore_matcher=coding_ignore_matcher,
    show_hidden=settings.show_hidden_files,
)
```

The coding page owns:

- choosing the root
- deriving ignore rules
- git status decoration
- opening files
- copying paths
- displaying file details
- surfacing product-specific status messages

The generic TUI widget owns only filesystem tree presentation and selection.

## Testing

Focused TUI tests should cover:

- root is required and invalid roots fail fast
- no default workspace/current-directory behavior
- deterministic directory-first sorting
- hidden filtering
- `path_filter` inclusion
- `ignore_matcher` exclusion
- traversal does not descend into filtered directories
- file vs directory selection result
- expand/collapse and active repair through `TreeView`
- reload preserves valid expanded/active paths
- runtime scan errors render disabled error rows
- max-entry sentinel behavior
- public exports
- example import and playback

Coding-layer tests should not be added in this TUI slice. A later coding slice
should test workspace root passing and gitignore matcher construction.

## Open Decisions

1. Should P0 labels be plain names, marker-prefixed names, or caller-formatted
   labels?
2. Should `show_root=False` flatten root children as top-level rows while still
   keeping root expansion state internal?
3. Should symlink directories be traversed, shown as files, or shown as
   non-descending directory rows?

## Recommended P0 Decisions

- Expose `max_entries: int = 2000`; it is a practical guardrail and easy to
  test.
- Render plain labels first, with no icons required. Let callers customize
  labels in a later slice if needed.
- Keep `show_root=True` as the default and cover `show_root=False` in tests.
- Treat symlink directories according to `Path.is_dir()` in P0, but rely on
  `max_entries` and visited-path tracking to prevent cycles.
- Defer path-kind styling; correctness and generic boundaries matter more than
  icon/color polish.
- Include only `reload()` in P0 and defer `reload_path(path)`.

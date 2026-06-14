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

@dataclass(slots=True)
class DirectoryTree:
    root: str | Path
    active_path: str | Path | None = None
    expanded_paths: Sequence[str | Path] = ()
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
- `handle_input(event) -> DirectoryTreeSelect | bool | None`
- `render(constraints)`
- `editor_input_target()` is not needed in P0
- `root_path: Path`
- `active_path: Path | None`
- `expanded_path_set: frozenset[Path]`
- `visible_paths: tuple[Path, ...]`
- `visible_entries: tuple[DirectoryTreeEntry, ...]`
- `reload()`
- `expand_path(path)`, `collapse_path(path)`, `toggle_path(path)`
- `is_expanded(path)`

`DirectoryTree` may internally create `TreeNode` values from normalized path
strings, but the public API exposes `Path` objects and `DirectoryTreeEntry`
objects rather than string node values. `visible_paths` includes only real file
and directory rows. `visible_entries` includes real rows plus disabled
synthetic empty/error/sentinel rows.

Both `visible_entries` and `visible_paths` expose the expansion-aware flattened
visible projection before render viewport clipping. When the root is valid,
`visible_entries` starts with the root directory entry and
`visible_paths[0] == root_path`. Synthetic entries never appear in
`visible_paths`.

## Root Contract

`root` is required and must be absolute. Relative roots raise `ValueError`
rather than being resolved through process `cwd`. This preserves the rule that
generic TUI code never guesses current-directory, workspace, git-root, or
session semantics.

The stored `root_path` is a normalized absolute lexical `Path` supplied by the
caller. P0 should not expose root-relative paths and should not expose
symlink-resolved paths as public values.

Lexical normalization is symlink-preserving:

- reject roots and public path inputs containing `..` path segments
- normalize redundant `.` path segments and separators
- validate under-root membership against the normalized lexical `root_path`
- do not use resolved paths to reject a normalized lexical child path

Internal implementation may use resolved paths only to avoid unsafe descent or
cycle traversal.

Root behavior:

- relative root raises `ValueError`
- root containing `..` segments raises `ValueError`
- missing root raises `ValueError`
- non-directory root raises `ValueError`
- a root symlink to a directory is allowed; `root_path` remains the lexical
  symlink path supplied by the caller, and root symlink traversal is the P0
  exception to the descendant-symlink rule
- unreadable root does not crash render; construction creates the same
  root-level error model that `reload()` uses for root invalidation

The widget never defaults to:

- `Path.cwd()`
- repository root
- workspace root
- coding session root

If product code wants workspace semantics, it passes `DirectoryTree(root=...)`
from the product layer.

All other public path inputs (`active_path`, `expanded_paths`, and path methods)
must also be absolute paths under `root_path`. Relative paths and paths outside
root raise `ValueError`. Inputs containing `..` path segments also raise
`ValueError`. Paths under root that are currently missing, filtered, hidden,
omitted by `max_entries`, or files when a directory is required do not raise for
normal state methods; they repair or return `False` as specified below.

## Filtering And Ignore Contract

Filtering is caller-controlled:

- `show_hidden=False` hides paths whose basename starts with `"."`.
- `path_filter(path)` is an inclusion predicate. `False` hides the path.
- `ignore_matcher(path)` is an exclusion predicate. `True` hides the path.

Both callbacks receive the same public path form used everywhere else:
absolute lexical `Path` objects under `root_path`. They do not receive
root-relative paths or symlink-resolved paths. A product layer that wants
root-relative matching should wrap its matcher:

```python
DirectoryTree(root=root, ignore_matcher=lambda path: matcher(path.relative_to(root)))
```

`sort_key(path)` receives the same absolute lexical `Path` form after hidden,
filter, and ignore rules are applied.

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

## Display And Expansion

P0 always renders the root row. There is no `show_root=False` option in the
first slice. If callers need a rootless presentation later, that behavior should
get a separate design because it changes active fallback, selection, expansion,
and visible-entry semantics.

Root display:

- root row label is `root_path.name`, falling back to `str(root_path)` when the
  name is empty
- child row labels are plain `path.name`
- an expanded directory with no visible child rows receives one disabled
  synthetic empty row labeled with `empty_text`
- empty rows have `kind="empty"`, `path=None`, `disabled=True`, and are excluded
  from `visible_paths`
- no file/folder icons or marker-prefixed labels are required in P0
- root is expanded by default
- `expanded_path_set` includes `root_path` while root is expanded

Initial active state:

- relative or outside-root `active_path` raises `ValueError`
- an active path under root is used only when it exists, is visible, is enabled,
  and is not omitted by `max_entries`
- otherwise active falls back to the first visible enabled real entry
- disabled error/sentinel rows are never active

Initial expanded state:

- root is always included when the root is valid
- relative or outside-root entries in `expanded_paths` raise `ValueError`
- under-root entries are preserved only when they exist, are visible, are
  traversable directories, and are not omitted by `max_entries`
- under-root missing paths, files, filtered paths, hidden paths, omitted paths,
  and symlink directory leaves are silently dropped from the initial expanded
  set

Expansion methods:

- relative or outside-root method paths raise `ValueError`
- `expand_path(path)` returns `True` when a visible directory changes from
  collapsed to expanded
- `expand_path(path)` returns `False` for files, missing paths, filtered paths,
  hidden paths, omitted paths, symlink directories that are not traversed,
  already-expanded directories, and disabled synthetic rows
- `collapse_path(path)` returns `True` when a visible expanded directory changes
  to collapsed
- `collapse_path(path)` returns `False` for files, missing paths, filtered
  paths, hidden paths, omitted paths, already-collapsed directories, and
  disabled synthetic rows
- `toggle_path(path)` delegates to collapse when expanded and expand when
  collapsed
- `is_expanded(path)` returns `True` only for visible expanded directories and
  `False` for all other valid-under-root paths

Collapsing a directory that hides the active path should use the same repair
rules as `TreeView`: prefer the collapsed directory when enabled, otherwise
fall back to the nearest visible enabled real entry.

## Scan Model

P0 scan model is synchronous and eager for the admitted tree model.

Terms:

- admitted tree model: the bounded tree of real and synthetic entries produced
  by scanning
- flattened visible projection: expansion-aware preorder rows exposed by
  `visible_entries`, `visible_paths`, and render

`max_entries` applies to the admitted tree model, not only to expanded rows.
Collapsed descendants that are admitted still consume the global real-entry
budget.

- Construct or reload scans the root subtree into a bounded model.
- Traversal order is deterministic preorder depth-first search. Each
  directory's child list is filtered, grouped, sorted, and then scanned in that
  order before moving to the next sibling.
- `max_entries` is a global cap on admitted real entries below the root.
- The root row itself does not consume the limit.
- Disabled synthetic empty/error/sentinel rows do not consume the limit.
- Filtered and ignored paths do not consume the limit.
- When a directory's child scan still has candidate children but no remaining
  real-entry budget, insert one disabled sentinel row such as
  `"more entries omitted"` under that directory and stop that directory's child
  scan.
- Sentinel insertion is per truncated child list. It is valid for both a child
  directory and its parent directory to receive sentinels when the global limit
  is reached during nested scanning.
- Sentinels under collapsed directories are hidden until that directory is
  expanded, matching normal tree visibility.
- Sentinel rows have `kind="sentinel"`, `path=None`, `disabled=True`, and are
  excluded from `visible_paths`.

This is intentionally simpler than lazy loading. Lazy loading can be a P1
extension once we have product usage.

`max_entries` is part of the P0 public API. Values below 1 are normalized to 1.
The count applies to scanned entries below the root; the required root itself
does not consume the limit.

The bound is on the rendered in-memory model, not a hard cap on filesystem I/O.
For deterministic sorting, P0 may still enumerate a single large directory
before choosing which admitted entries fit under `max_entries`.

Symlink handling in P0:

- a root symlink to a directory is traversed as the root while preserving the
  lexical `root_path`
- symlink files are treated as file rows
- symlink directories may report `kind="directory"` for selection
- symlink directories are not traversed for children in P0
- a symlink directory is therefore a leaf for expand/collapse purposes

## Selection Semantics

Activation should return a structured object:

```python
DirectoryTreeSelect(path=path, kind="file" | "directory")
```

`enter`, `space` key events, and exact printable text event `text == " "`
activate the active visible path. Expand/collapse remains owned by left/right
keys through the underlying tree behavior.

Selection result rules:

- file rows return `kind="file"`
- directory rows return `kind="directory"`
- disabled empty/sentinel/error rows return `None`
- navigation and expand/collapse inputs return `True`, `False`, or `None`
  following the underlying `TreeView` state-change contract
- raw `InputIntent` values from the internal `TreeView` must not leak out of
  `DirectoryTree`

Directory activation does not implicitly expand/collapse in P0. This keeps
activation distinct from navigation and matches current `TreeView` behavior.

## Refresh Semantics

`reload()` rescans the whole root and repairs state:

- preserve expanded paths that still exist, are under root, are real directory
  entries, are visible under the current filters, and are not omitted by
  `max_entries`
- preserve active path if it still exists, is under root, is a real file or
  directory entry, is enabled, is visible under the current filters, and is not
  omitted by `max_entries`
- otherwise fall back to the first visible enabled real entry

P0 does not watch the filesystem. Product code or examples call reload
explicitly.

Per-directory reload is deferred. `reload_path(path)` can be added later if a
product page needs it and tests can show a meaningful benefit over full reload.

If construction finds that `root_path` is unreadable, or if `reload()` finds
that `root_path` is now missing, no longer a directory, or unreadable, it does
not raise. It replaces the admitted tree model and flattened visible projection
with a single disabled root-level error entry:

- `DirectoryTreeEntry(path=root_path, kind="error", disabled=True, ...)`
- `visible_entries == (root_error_entry,)`
- `visible_paths == ()`
- `active_path is None`
- `expanded_path_set == frozenset()`

Construction still raises for missing or non-directory roots. The non-raising
construction case is limited to unreadable roots because permission can be
environment-dependent and should remain renderable for diagnostics.

## Error Handling

Expected filesystem errors should render as disabled rows rather than crashing:

- `PermissionError`
- `FileNotFoundError` for paths removed during scan
- `OSError` while reading directory entries

Root validation errors still fail fast during construction when the root itself
is missing or not a directory. Runtime errors under a valid root should be
localized to the affected directory. Error rows have `kind="error"`, are
disabled, and are excluded from `visible_paths`.

## Theme Tokens

P0 should reuse underlying `TreeView` tokens:

| Token | Applies to |
| --- | --- |
| `widget.tree.row` | Normal enabled rows |
| `widget.tree.focus` | Active row while focused |
| `widget.tree.disabled` | Synthetic empty/error/sentinel rows and other disabled rows |
| `widget.tree.empty` | Reserved fallback if the internal TreeView has no nodes |

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
- relative root is rejected and never resolved through process cwd
- roots and public path inputs containing `..` segments raise `ValueError`
- no default workspace/current-directory behavior
- deterministic directory-first sorting
- hidden filtering
- `path_filter` inclusion
- `ignore_matcher` exclusion
- filter and ignore callbacks receive absolute lexical paths
- `sort_key` receives absolute lexical paths
- traversal does not descend into filtered directories
- outside-root `active_path`, `expanded_paths`, and method paths raise
  `ValueError`
- under-root non-expandable `expanded_paths` entries are dropped
- root is included in `visible_entries` and `visible_paths` when valid
- `visible_entries` includes disabled synthetic rows while `visible_paths`
  excludes them
- empty directories render a disabled synthetic empty row
- file vs directory selection result
- `enter`, `space` key, and exact text `" "` activation parity
- `handle_input` returns `DirectoryTreeSelect | bool | None` and does not leak
  internal `InputIntent`
- expand/collapse and active repair through `TreeView`
- reload preserves valid expanded/active paths
- reload root invalidation produces a disabled error model without raising
- unreadable-root construction produces the same disabled root error model
- runtime scan errors render disabled error rows
- max-entry sentinel behavior
- collapsed descendants count against `max_entries` after admission
- nested max-entry sentinel placement
- root symlink to a directory preserves lexical public root path and shows child
  rows through that lexical path
- symlink directories under root are selectable directory rows but not traversed
- public TUI implementation does not import from `loushang.coding`
- public exports
- example import and playback

Coding-layer tests should not be added in this TUI slice. A later coding slice
should test workspace root passing and gitignore matcher construction.

## P0 Decisions

- `root` must be absolute and explicit.
- Public path validation is lexical against `root_path`; symlink-resolved paths
  are never exposed.
- Path inputs containing `..` segments are rejected.
- Root is always rendered and expanded by default.
- A root symlink to a directory is traversed as the root while preserving the
  lexical `root_path`.
- Descendant symlink directories are selectable leaves and are not traversed.
- Labels are plain names with no icon requirement.
- `visible_entries` is the authoritative rendered model inspection API.
- `visible_paths` includes only real file/directory paths and excludes
  empty/error/sentinel rows.
- `max_entries: int = 2000` is public and normalized to at least 1.
- `reload()` degrades root invalidation to a disabled error model instead of
  raising.
- Styling reuses `widget.tree.*`.
- P0 includes `reload()` only.

## Post-P0 Extensions

- rootless display, equivalent to a future `show_root=False`
- caller-provided label formatting or icons
- directory/file-specific theme tokens
- per-directory `reload_path(path)`
- lazy loading or async scanning
- symlink traversal policy beyond non-descending leaf rows

# DirectoryTree

`DirectoryTree` is a reusable filesystem-specific tree widget layered on top of
`TreeView`. It adapts an explicit directory root into tree rows for files,
directories, empty states, scan errors, and truncation sentinels.

It belongs to `loushang.tui.ui_parts.widgets`. Product layers such as coding
pages choose workspace roots, ignore rules, file-opening behavior, git status,
and details panes. The generic TUI widget does not infer current directory,
workspace, repository root, session state, or `.gitignore` semantics.

## Inputs And State

- `root`: required absolute path. Relative roots and paths containing `..`
  fail early.
- `active_path`: optional initial active file or directory path.
- `expanded_paths`: optional initial expanded directories.
- `show_hidden`: whether basenames starting with `.` are included.
- `path_filter(path)`: inclusion predicate for absolute lexical paths.
- `ignore_matcher(path)`: exclusion predicate for absolute lexical paths.
- `sort_key(path)`: optional sort key within directory and file groups.
- `empty_text`: label for empty expanded directories. `None` or `""` hides the
  synthetic empty row.
- `max_entries`: global cap on admitted real entries below root, normalized to
  at least 1.
- `wrap`, `theme`, and `focused`: passed through to the composed `TreeView`.

Public paths are normalized absolute lexical `Path` objects under `root_path`.
`DirectoryTree` never exposes symlink-resolved paths or root-relative strings.

## Rendering Model

The root row is always rendered for valid roots and expanded by default.
Children are grouped directories-first, then files, with deterministic
case-insensitive name ordering unless `sort_key` is supplied.

`visible_entries` is the expansion-aware flattened projection before viewport
clipping. It includes real rows plus disabled synthetic rows:

- `empty`: expanded directory has no visible children
- `error`: filesystem scan error for a root or child directory
- `sentinel`: more real entries were omitted by `max_entries`

Synthetic labels are prefixed so they are visually distinct even without theme
color: `· No files`, `· more entries omitted`, and `! <error>`.

`visible_paths` includes only real file and directory paths, excluding all
synthetic rows.

## Focus And Selection

`DirectoryTree` delegates row focus, expand/collapse navigation, viewport
windowing, cursor declaration, and theme tokens to `TreeView`.

Activation with `enter`, `space`, or text `" "` returns
`DirectoryTreeSelect(path=..., kind="file" | "directory")` for real active
rows. Disabled synthetic rows return `None`. Internal `InputIntent` values from
`TreeView` are translated before they leave the widget.

## Reload And Errors

`reload()` rescans the whole root and preserves active and expanded paths only
when those paths still exist, remain visible, and are still admitted by the
entry cap. Otherwise active state falls back to the first enabled visible real
row.

Missing or non-directory roots fail during construction. Root unreadability
during construction, and missing/file/unreadable roots during reload, degrade to
a single disabled root-level error row. Runtime errors under a valid root render
as disabled error rows scoped to the affected directory.

## Symlink Policy

A root symlink to a directory is traversed while preserving the lexical
`root_path` provided by the caller. Descendant symlink directories are
selectable directory leaves but are not traversed for child rows.

## Theme Tokens

DirectoryTree reuses `TreeView` tokens:

| Token | Applies to |
| --- | --- |
| `widget.tree.row` | Normal enabled rows |
| `widget.tree.focus` | Active row while focused |
| `widget.tree.disabled` | Empty, error, sentinel, and other disabled rows |
| `widget.tree.empty` | Fallback empty TreeView state |

It also provides semantic per-row tokens through `TreeNode.theme_token`:

| Token | Applies to |
| --- | --- |
| `widget.directoryTree.directory` | Real directory rows |
| `widget.directoryTree.file` | Real file rows |
| `widget.directoryTree.empty` | Empty synthetic rows |
| `widget.directoryTree.error` | Error synthetic rows |
| `widget.directoryTree.sentinel` | Entry-cap sentinel rows |

`TreeView` composes base and semantic styles. Focused rows apply
`widget.tree.row`, then the semantic token, then `widget.tree.focus`, so focus
styling wins over directory/file color. Disabled rows apply
`widget.tree.disabled` plus the semantic token, so a theme can dim synthetic
rows while still giving empty/error/sentinel rows distinct colors.

## Test Obligations

Changes to DirectoryTree should cover:

- absolute lexical root validation and `..` rejection
- no default workspace or current-directory behavior
- hidden filtering, path filters, ignore matchers, and sort callbacks
- root inclusion in `visible_entries` and `visible_paths`
- synthetic rows included in `visible_entries` and excluded from `visible_paths`
- active and expanded state repair
- file and directory selection results
- reload preservation and root invalidation error model
- max-entry sentinels and collapsed descendant admission
- root symlink traversal and descendant symlink leaf behavior
- runtime scan errors
- public exports and example playback

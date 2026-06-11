# TUI Widgets P1B TextArea Design

## Status

Draft for implementation planning.

## Context

`loushang.tui` now has a practical widget catalog:

- P0A form and dialog controls, including `TextField`.
- P0B compact display and action controls.
- P0C light controls.
- P1A `Table` for dense row/column data.

The remaining gap for form-like workflows is multi-line text entry. `TextField`
wraps `TextInput`, which intentionally normalizes input to a single line.
`Composer` supports rich prompt editing and product-specific behavior, but it is
not a general-purpose form field. A reusable `TextArea` should sit between those
two: a deterministic multi-line field that can be embedded in `Form`, `Dialog`,
extension surfaces, and product UIs without carrying composer-specific history,
completion, paste-marker, or prompt semantics.

`EditorBuffer` already supports newline storage, line-start/line-end movement,
undo/redo, word movement, and text replacement. The first `TextArea` slice
should reuse that editing foundation instead of introducing a second editor
model.

## Goals

- Add a public `TextArea` widget for general-purpose multi-line text entry.
- Keep `TextArea` a normal `Renderable`, `Focusable`, and
  `EditorInputTargetProvider`.
- Reuse `EditorBuffer`, `SelectionController`, `KillRing`, keybinding
  semantics, and editor-target routing patterns from `TextInput`.
- Preserve newlines in direct text, paste, programmatic `set_text()`, and
  `value`.
- Support deterministic vertical viewport behavior so the cursor remains
  visible.
- Support width and height constraints, placeholder text, optional label,
  help/error lines, and theme tokens.
- Support callbacks for `on_change`, `on_submit`, and `on_escape`.
- Integrate with `Form` and `Dialog` through `editor_input_target()`.
- Export stable public API through `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests and a small example.

## Non-Goals

- Do not replace `Composer` or route product prompt behavior through `TextArea`.
- Do not add history browsing, slash commands, completions, paste markers,
  image protocol handling, or markdown preview.
- Do not add soft wrapping in the first slice. Long logical lines scroll
  horizontally inside the visible viewport.
- Do not add mouse selection or pointer capture.
- Do not add syntax highlighting.
- Do not add a layout engine or global focus manager.
- Do not change `TextInput`, `TextField`, `Composer`, `InputRouter`,
  `SurfaceHost`, or existing keybinding defaults unless a focused test proves a
  reusable hook is needed.

## Public API

Add `src/loushang/tui/ui_parts/widgets/textarea.py`.

```python
from collections.abc import Callable
from dataclasses import dataclass

@dataclass(slots=True)
class TextArea:
    label: str = ""
    value: str = ""
    placeholder: str = ""
    help_text: str = ""
    error: str = ""
    height: int = 4
    on_submit: Callable[[str], object] | None = None
    on_escape: Callable[[], object] | None = None
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False
```

The first public API is intentionally close to `TextField`:

- `value` is accepted by the initializer as the initial text, then exposed as a
  read-only property backed by `EditorBuffer`. It is not independent dataclass
  state after initialization.
- `set_text(text)` replaces content, preserves newlines, clears selection,
  resets viewport state, and clears undo history.
- `clear()` clears content, selection, viewport state, and undo history.
- `undo()` and `redo()` delegate to `EditorBuffer`.
- `focus()` and `blur()` set local focus.
- `handle_input(event, *, keybindings=None)` consumes text, paste, submit,
  escape, and editing keys.
- `editor_input_target()` returns an object implementing the existing
  `EditorInputTarget` protocol.

`height` is the preferred editor-body height in rows. It does not include label,
help, or error rows. Rendering still obeys `constraints.max_height`; if the
constraint is smaller, label rows are preserved first, detail rows are preserved
only when at least one body row can still render, and visible body rows shrink
to fit the remaining budget.

## Editing Behavior

`TextArea` owns an `EditorBuffer(max_undo_depth=100)`, a
`SelectionController`, and a `KillRing`, following `TextInput`.

Input behavior:

| Input | Behavior |
| --- | --- |
| text event | Insert text verbatim, including `\n`. |
| paste event | Insert pasted text verbatim, including `\n`. |
| `enter` | Insert newline by default. |
| submit binding | Emits `on_submit(value)` only when the configured keybinding matches `tui.input.submit` and is not the plain `enter` newline behavior. |
| `escape` / cancel binding | Emits `on_escape()` when provided and returns consumed. |
| editing keys | Reuse existing editor movement, deletion, kill/yank, undo/redo semantics. |

The default plain `enter` behavior should insert a newline because `TextArea` is
a multi-line field. A later `PromptDialog` can bind submit to another key such
as `ctrl+enter` if needed. The first slice should not change global keybinding
defaults; tests should exercise `on_submit` through an explicit keybinding
config if required.

Line semantics:

- `move_to_line_start()` and `move_to_line_end()` use `EditorBuffer` line
  helpers.
- Left/right movement crosses newline boundaries naturally because the buffer is
  a single cluster sequence.
- Visual up/down cursor movement is out of scope for P1B. `up` and `down`
  should remain available to parent containers unless a later slice adds
  explicit visual-line navigation.
- Word movement treats newline as separator through existing word-navigation
  behavior.
- `delete_backward()` before a newline joins lines.
- `delete_forward()` before a newline joins lines.
- `kill_to_line_start()` and `kill_to_line_end()` operate on the current
  logical line.
- Selection can span newlines; replacement, delete, kill, undo, and redo remain
  atomic.

## Rendering And Viewport

`TextArea.render(constraints)` returns a `RenderResult` with a cursor
declaration when the body row containing the cursor is visible.

Rendering layout:

1. Optional `label` row.
2. Editor body rows.
3. Optional detail row: `error` if present, otherwise `help_text`.

Height-budget precedence is explicit:

1. Render the label first when present and height allows.
2. Compute remaining height after the label.
3. If remaining height is zero, stop.
4. If a detail row exists and remaining height is at least two, reserve one row
   for detail so at least one body row can still render.
5. Render body rows with `min(height, remaining_height_after_detail_reservation)`.
6. Render the reserved detail row after body rows.
7. If only one row remains after the label, render one body row and omit detail.

Example with `label="Notes"`, `height=4`, `error="Required"`, and
`constraints.max_height=5`:

```text
Notes
<body row 1>
<body row 2>
<body row 3>
Required
```

The preferred body height is four, but it shrinks to three to keep the error row
visible. With `constraints.max_height=2`, the result is `Notes` plus one body
row; the error row is omitted.

Width and height rules:

- All visible lines fit `constraints.width` after stripping control sequences.
- `RenderConstraints` already guarantees positive width and height.
- Use `autowrap_safe_width(constraints.width)` for visible content width.
- The editor body renders at least one row when height budget allows.
- If no body row fits after the label, render only the label.
- Error/help rows are omitted when height budget cannot fit both at least one
  body row and the detail row.
- `error` takes precedence over `help_text`.

Viewport rules:

- Store `_first_visible_line: int` for vertical scrolling.
- Store `_scroll_column: int` for horizontal scrolling of the cursor line.
- The cursor logical line is kept between `_first_visible_line` and
  `_first_visible_line + visible_body_rows - 1`.
- Horizontal scrolling applies to all visible body rows in the first slice.
  This keeps the implementation deterministic and avoids per-line scroll state.
- If the cursor column is left of `_scroll_column`, move `_scroll_column` left.
- If the cursor column is right of the visible width, move `_scroll_column`
  right enough to reveal the cursor.

Display rules:

- Empty content renders `placeholder` on the first visible body row only.
- Placeholder does not move the cursor; cursor remains at row 0, column 0 in
  the body.
- Logical empty lines render as empty body rows.
- Lines are sliced with `slice_by_column()` and truncated with
  `truncate_to_width()`.
- The first slice does not draw borders, gutters, line numbers, or scrollbars.

Cursor mapping:

- Cursor row is `label_rows + (cursor_logical_line - first_visible_line)`.
- Cursor column is `max(0, cursor_column - _scroll_column)`, clamped to the
  visible rendered line width.
- If the cursor line is outside the rendered body because height is zero, omit
  the cursor declaration.

## Theme Tokens

Add these initial stable tokens:

| Token | Applies to |
| --- | --- |
| `widget.textArea.label` | Label row. |
| `widget.textArea.placeholder` | Placeholder text. |
| `widget.textArea.text` | Body text. |
| `widget.textArea.error` | Error row. |
| `widget.textArea.help` | Help row. |

Selection rendering should continue using the shared editor selection token
default:

- `editor.selection`

The implementation should use existing `apply_theme_style()` / `style_text()`
helpers and preserve visible width with ANSI styling.

## Files In Scope

Production:

- `src/loushang/tui/ui_parts/widgets/textarea.py`
- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_textarea.py`
- Existing form/dialog tests only if integration coverage fits better there.

Docs and examples:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`
- `examples/tui/47_widgets_textarea.py`

## Testing Strategy

Use TDD for implementation:

1. Add public export tests.
2. Add value/editing tests for text, paste, newline insertion, line join,
   undo/redo, and callbacks.
3. Add editor-target routing tests for insert, paste, movement, deletion,
   kill/yank, undo, and redo.
4. Add render tests for label, placeholder, help/error precedence, width and
   height constraints, cursor rows/columns, vertical viewport, and horizontal
   scrolling.
5. Add selection tests for multi-line selection replacement and visible
   selection styling when practical.
6. Add Form/Dialog integration tests proving `editor_input_target()` delegates
   through existing containers.
7. Add theme tests for label/body/placeholder/help/error visible-width
   stability.
8. Add docs and example importability tests.
9. Run focused tests, adjacent widget tests, full TUI tests, and Ruff.

Expected verification commands:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py tests/tui/test_widgets_table.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/47_widgets_textarea.py docs
```

## Rollout Plan

This should be one focused PR with small commits:

1. Commit the design spec.
2. Commit the implementation plan after spec review.
3. Add failing TextArea export and editing tests.
4. Implement the minimal TextArea editing model and editor target.
5. Add failing render and viewport tests.
6. Implement deterministic rendering and cursor mapping.
7. Add integration, theme, docs, and example coverage.
8. Run focused, adjacent, full TUI, and Ruff verification.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| TextArea duplicates too much `TextInput` code. | Keep the first slice behavior-compatible, then consider shared editor helpers only after both widgets are stable. |
| TextArea accidentally becomes Composer-lite. | Exclude history, completions, prompt semantics, paste markers, images, and markdown preview. |
| Enter/submit semantics are ambiguous. | Plain `enter` inserts newline; submit requires explicit keybinding in the first slice. |
| Viewport logic becomes complex. | Use one vertical line window and one shared horizontal scroll column. |
| ANSI styling breaks cursor or width math. | Assert stripped visible width and cursor coordinates in tests. |

## Success Criteria

- `TextArea` is exported from the same public modules as stable widgets.
- Multi-line text editing preserves newlines and supports undo/redo.
- Existing editor routing can edit a focused `TextArea` through
  `editor_input_target()`.
- Rendering obeys width and height constraints.
- Cursor row/column remains correct with label rows, vertical scrolling, and
  horizontal scrolling.
- Help/error/placeholder/theme states are deterministic and covered.
- `TextArea` works inside existing `Form` and `Dialog` focus/editor-target
  delegation.
- Existing TUI tests remain green.

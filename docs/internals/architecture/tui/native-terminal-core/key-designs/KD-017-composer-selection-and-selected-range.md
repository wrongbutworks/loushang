# KD-017: Composer Selection And Selected Range

Status: Accepted. Initial keyboard selection and shared edit foundation are
implemented as of 2026-06-05.

## Purpose

Define the editing selection model for the native TUI composer.

This design covers text selected inside the editable composer buffer. It does
not redefine command-list selection, completion-menu selection, transcript copy
selection, or terminal-native mouse selection.

## Implementation Status

The first implementation has landed in the native TUI core:

- `SelectionRange` provides anchor/focus bounds, normalized start/end, and
  empty-selection handling.
- `SelectionController` owns reusable selection state and is shared by Composer
  and TextInput.
- `EditorBuffer` provides grapheme-indexed text editing for reusable text
  inputs.
- `ComposerEditBuffer` provides atom-indexed editing for composer text and
  paste markers.
- `UndoStack` and `KillRing` are reusable editing infrastructure.
- Composer supports keyboard selection, selected-range replace/delete,
  kill-selection, yank-over-selection, selection-aware undo boundaries,
  completion refresh after selected-range replacement, and selection highlight
  rendering.
- TextInput uses the shared editing and selection primitives for the same
  index-unit discipline.
- Playback covers completion interaction and composer-selection stress,
  including visible frame-output assertions.

The following items remain outside the initial implementation:

- mouse-driven composer selection
- transcript or screen-buffer copy selection
- restoring selection through undo/redo snapshots
- changing the default redo keybinding policy. This was handled later as a
  separate follow-up with `alt+r`.

## Reference Observations

The reference implementations separate three concerns that should remain
separate in Loushang:

- editable buffer state and range replacement
- visual or screen-buffer selection
- menu/list selection

One textarea-style implementation keeps a cursor-oriented editable buffer with
range replacement, element-aware range expansion, kill operations, and
render-only highlight ranges. It does not require a persistent text
`selected_range` field in the core textarea to support range edits.

One fullscreen selection model uses `anchor` and `focus` points and normalizes
them only for rendering and copy extraction. That model is screen-coordinate
based and includes scrollback bookkeeping. It is useful for selection semantics,
but it is too screen-specific for composer text editing.

Loushang should borrow the anchor/focus semantics, but keep composer selection
in buffer index space. Screen coordinates should appear only when converting
mouse or render positions to buffer positions.

## Design Goals

- Keep selected text editing reusable and testable without terminal rendering.
- Preserve current composer atom safety, especially paste markers.
- Keep display width out of editing indexes.
- Make replacement and deletion one undoable edit.
- Keep completion-list selection and composer text selection independent.
- Add keyboard selection before mouse selection.
- Avoid changing transcript selection or list-selection behavior.

## Core Model

Introduce a small selection primitive:

```python
@dataclass(frozen=True, slots=True)
class SelectionRange:
    anchor: int
    focus: int

    @property
    def start(self) -> int: ...
    @property
    def end(self) -> int: ...
    def normalized(self, length: int) -> tuple[int, int]: ...
    @property
    def is_empty(self) -> bool: ...
```

`anchor` is where selection began. `focus` is where the cursor currently is.
The hardware cursor and composer cursor are always the focus endpoint.

The public composer-facing state should be:

```python
selected_range: tuple[int, int] | None
```

`selected_range` returns the normalized half-open range `[start, end)` in
buffer index space. It returns `None` when there is no active non-empty
selection. Empty selections should not be represented as `(i, i)`.

`start` and `end` expose the raw normalized ordering without clamping.
`normalized(length)` is the clamped form for applying the selection to a
specific buffer. Code that reads composer selection should branch on
`selected_range is None`, not on `start == end`.

## Index Units

Selection indexes must use the same unit as the owning editable buffer:

- `EditorBuffer`: grapheme cluster indexes.
- `ComposerEditBuffer`: composer atom indexes.

They must not use:

- Python code point indexes
- UTF-8 byte offsets
- terminal display columns
- `wcwidth` or visible-width units

Display width remains a render and hit-test concern. The composer can convert a
screen column to an atom index when mouse selection is added, but the stored
selection range stays atom based.

Paste markers are atomic. A selection may include a paste marker, but it must
not split one. This follows `ComposerEditBuffer`'s existing atom boundary model.

## Layer Responsibilities

### SelectionRange

`SelectionRange` owns only normalized bounds and empty-selection detection. It
does not know about buffers, rendering, undo, completion, or keybindings.

### ComposerEditBuffer

`ComposerEditBuffer` remains the content-editing primitive:

- insert atoms
- delete range
- replace range
- move cursor by atom, word, and line
- undo and redo content snapshots

It should not initially store persistent selection state. Keeping selection out
of the buffer avoids mixing UI interaction state with reusable range editing.

### Composer

`Composer` owns active text selection:

- `_selection: SelectionRange | None`
- `selected_range` property
- `has_selection()` convenience query
- `set_selection(anchor, focus)` for explicit selection setup
- `clear_selection()` for lifecycle cleanup
- selection extension operations
- replacing selected text during typing and paste
- clearing selection on ordinary movement, history recall, submit, completion
  application, clear, undo, and redo

This keeps selection close to completion, history, kill-ring, render, and
bottom-frame behavior.

The shared selection state machine now lives in `SelectionController`. Composer
owns product-specific selection behavior, while `SelectionController` remains
small enough for other editable widgets to reuse.

### TextInput

`TextInput` stores editable content in `EditorBuffer` and selection state in
`SelectionController`. It uses grapheme cluster indexes for editing and
selection. Display width remains a rendering and horizontal-scroll concern.

## Editing Semantics

### Default Lifecycle Rule

Selection is transient interaction state. Any public `Composer` method that
changes cursor position or buffer content clears selection by default, unless
the method is itself a selection extension operation or a selection-aware edit
that consumes and clears the selected range.

This default applies to ordinary movement, visual movement, page movement,
character jump, cursor hit-test movement, history recall, submit, clear,
completion application, undo, redo, and text-setting methods.

Examples that must not leave stale selection behind:

- `move_visual_up()` and `move_visual_down()`
- `move_visual_page_up()` and `move_visual_page_down()`
- `jump_to_char()`
- `move_cursor_to()` or equivalent hit-test movement
- `insert_newline()`
- `set_text()`
- `delete_word_backward()` and `delete_word_forward()`

This rule avoids "hidden selection" bugs where a later typed character
unexpectedly replaces old selected text after unrelated navigation.

### Selection Creation

Selection is created only by explicit selection actions:

- `shift+left`
- `shift+right`
- `ctrl+shift+left`
- `ctrl+shift+right`
- `alt+shift+b`
- `alt+shift+f`
- `shift+home`
- `shift+end`

Vertical selection can be added later:

- `shift+up`
- `shift+down`
- `shift+pageUp`
- `shift+pageDown`

When there is no current selection and a selection action succeeds, the old
cursor position becomes `anchor` and the new cursor position becomes `focus`.
When selection already exists, only `focus` changes.

If `focus` returns to `anchor`, the selection clears.

### Ordinary Cursor Movement

Ordinary non-shift movement clears selection after moving:

- left, right
- word left, word right
- line start, line end
- up, down
- page up, page down

This keeps terminal input behavior predictable and avoids leaving stale hidden
selection after navigation.

### Text Input And Paste

Text input and paste replace the selected range if one exists. The replacement
must be a single undoable edit.

Rules:

- normalize `selected_range`
- push one undo snapshot
- replace the selected range with inserted atoms
- move cursor to the end of the inserted atoms
- clear selection
- refresh completions
- reset kill/yank action state as appropriate

If no selection exists, existing insert and paste behavior remains unchanged.

### Centralized Edit Application

Implementation centralizes selection-aware edit bookkeeping instead of
spreading it across every editing method.

Recommended internal pattern:

```python
def _replace_selection_with_atoms(atoms, *, last_action): ...
def _delete_selection_or_none() -> bool: ...
def _kill_selection_or_none(*, prepend: bool) -> bool: ...
def _apply_buffer_edit(edit, *, last_action, refresh_completion): ...
```

The helper is responsible for:

- pushing at most one undo snapshot for a logical edit
- applying selected-range replacement or deletion before fallback behavior
- clearing redo when content changes
- clearing selection after the edit
- refreshing completion state when cursor/content changes
- resetting kill/yank action state unless the edit is a kill or yank

This prevents duplicate undo snapshots when selection replacement reuses lower
level `replace_range()` methods that can also record undo.

### Delete And Backspace

When selection exists:

- Backspace deletes the selected range.
- Delete deletes the selected range.
- Cursor moves to the range start.
- The delete is one undoable edit.
- Selection clears.

Backspace and Delete should not delete an extra atom next to the range.

### Kill And Yank

When selection exists:

- kill commands operate on the selected range instead of their normal
  line/word boundary target
- selected text should be pushed to the kill ring
- selection should clear after the kill
- yank should replace selection if selection exists, otherwise insert at cursor
- yank-pop should remain valid only after a yank action

Selection kill is exclusive: after killing selected text, the command must not
also kill to the line start, line end, previous word, or next word.

This makes selected text behave like ordinary killed text while preserving the
existing kill-ring model. When yank replaces a selected range, `_last_action`
must still become `yank` so yank-pop can replace the just-yanked text.

### Completion

Composer text selection and completion-list selection are independent.

When a selected completion is applied:

- if provider completion owns the full replacement, clear composer selection
  before applying provider output
- otherwise apply the existing completion prefix replacement
- clear composer selection after completion applies

If text selection exists while completion items are visible, typing replaces
the selected text and then refreshes completion items from the new cursor
position. Selection should not become part of the completion prefix model.

### History, Submit, Clear, Undo, Redo

These operations clear selection:

- history previous and next
- submit
- clear
- set text from product state
- apply completion
- undo
- redo

The first implementation should not restore selection through undo and redo.
Only content and cursor are restored by existing buffer snapshots.

Undo and redo intentionally restore only buffer content and cursor in the first
implementation. Selection is always cleared. If a future implementation needs
undo/redo to restore selection, that state belongs in a Composer-level snapshot,
not in `ComposerEditBuffer`.

## Rendering

The first implementation includes visible highlighting for keyboard selection.

The highlight contract:

- do nothing when `selected_range is None`
- render selected atoms with a dedicated editor-selection style
- preserve the ordinary cursor at `focus`
- when cursor and selection styles overlap, cursor style wins at the focus cell
- do not reuse completion-list selected-row styling
- do not style paste-marker internals differently from their atomic label
- wrap selection across rendered composer lines
- clip selection to the visible composer viewport
- close and reopen ANSI style on each rendered line so soft-wrapped multi-line
  selection cannot leak styling into later rows
- use the shared `highlight_selection_by_columns()` helper for column-range
  highlighting

Recommended theme token:

```text
editor.selection
```

This token should be separate from `selection.selected`, which is already used
for list and command surfaces.

## Keybinding Contract

Add editor selection actions instead of overloading movement action names:

```text
tui.editor.selectCharLeft
tui.editor.selectCharRight
tui.editor.selectWordLeft
tui.editor.selectWordRight
tui.editor.selectLineStart
tui.editor.selectLineEnd
```

Default bindings:

```text
shift+left
shift+right
ctrl+shift+left, alt+shift+b
ctrl+shift+right, alt+shift+f
shift+home
shift+end
```

These must route before ordinary movement actions.

Input parsing should continue to produce normalized key ids such as
`shift+left` and `ctrl+shift+right`. The router should not inspect raw terminal
escape sequences.

The router priority is:

1. active focused surface
2. composer text-selection keybindings
3. completion-list navigation and application
4. submit, newline, tab, and product command keys
5. ordinary composer cursor and editing keybindings
6. text and paste events

This preserves surface focus while ensuring `shift+left` or
`ctrl+shift+right` extends composer text selection even when completion items
are visible. Unmodified `up`, `down`, `tab`, `enter`, and `escape` keep their
completion-list behavior while the completion list is visible. Text and paste
events replace active selection regardless of whether completion items are
visible.

## Mouse Selection

Mouse selection is out of scope for the first implementation.

The model is ready for it because anchor/focus is directional. A future mouse
implementation should:

- convert composer screen coordinates to atom indexes
- set anchor on mouse press
- update focus on drag
- keep selection after release
- ignore transcript and list-surface coordinates

Composer should expose explicit selection setters rather than requiring mouse
handlers to mutate private fields.

The conversion layer must account for prompt width, continuation prompt width,
soft wrapping, visible composer scroll offset, and paste-marker display width.

## Failure Handling

If selection bounds are outside the current buffer after an external state
change, clamp them to the buffer length. If the clamped range is empty, clear
selection.

If a selected range intersects an atom that must remain atomic, the range must
expand or clamp to atom boundaries. With `ComposerEditBuffer` atom indexes this
is already the natural behavior.

If a terminal cannot report shift-modified navigation keys, users still retain
ordinary range editing through kill commands and completion prefix replacement.
Selection keybindings can be overridden by configuration.

## Implementation Sequence

1. Add `SelectionRange` and focused unit tests for normalization, clamping, and
   empty-range behavior. Done.
2. Add composer selection state and selection movement methods. Done.
3. Add centralized selection-aware edit helpers for insert, paste, Backspace,
   Delete, kill, yank, and yank-pop. Done.
4. Make all cursor/content-changing Composer methods obey the default
   selection lifecycle rule. Done.
5. Add keybinding actions and input-router priority coverage. Done.
6. Add render highlighting and playback tests. Done.
7. Add mouse selection only after keyboard selection is stable. Future work.

This sequence keeps range editing testable before rendering and avoids mixing
mouse coordinate work into the initial selection state machine.

## Test Obligations

- `SelectionRange(anchor, focus)` normalizes forward and backward ranges.
- Empty normalized selections clear to `None`.
- Composer selected range uses atom indexes, not display width.
- CJK and emoji selection does not split grapheme clusters.
- Paste markers are selected and deleted atomically.
- `shift+left` and `shift+right` extend selection from the original anchor.
- `ctrl+shift+left` and `ctrl+shift+right` extend by word boundaries.
- `shift+home` and `shift+end` extend to logical line boundaries.
- Ordinary movement clears selection.
- Visual up/down and page up/down clear selection unless invoked through future
  selection-extension actions.
- Character jump clears selection.
- Cursor hit-test movement clears selection.
- Typing replaces selection in one undoable edit.
- Bracketed paste replaces selection in one undoable edit.
- Backspace and Delete delete selection without deleting adjacent atoms.
- Kill commands push selected text to the kill ring.
- `kill_to_line_start()` and `kill_to_line_end()` kill selection only when
  selection exists and do not also kill line text.
- `delete_word_backward()` and `delete_word_forward()` kill selection only when
  selection exists and do not also kill word text.
- Yank replaces selection when selection exists.
- Yank-pop works after yank replaces selection.
- Completion application clears composer text selection.
- When completion list is visible, text-selection keybindings extend composer
  selection and do not navigate completion items.
- When completion list is visible, unmodified completion navigation keys still
  navigate completion items.
- Typing with selection and visible completion items replaces selection and
  refreshes completion state from the new cursor.
- History recall clears composer text selection.
- Submit and clear discard composer text selection.
- Undo and redo clear composer text selection in the first implementation.
- Undo after selection replacement restores the prior content and cursor in one
  undo step.
- Plain movement after `shift+left` clears selection.
- Playback covers visible highlight after keyboard selection.
- Playback proves completion-list selection and composer text selection do not
  share state.
- A stress playback covers CJK, emoji, paste marker, selection extension,
  kill, yank, undo, and selection-state assertions.

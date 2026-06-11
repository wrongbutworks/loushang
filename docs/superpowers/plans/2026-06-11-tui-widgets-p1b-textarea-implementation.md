# TUI Widgets P1B TextArea Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable multi-line `TextArea` widget for deterministic text entry in `loushang.tui` forms, dialogs, extension surfaces, and standalone widget apps.

**Architecture:** Implement `TextArea` as one focused widget module under `src/loushang/tui/ui_parts/widgets/textarea.py`. It should own an `EditorBuffer`, `SelectionController`, `KillRing`, deterministic viewport state, and a narrow editor-target adapter, while following the existing public export and rendering patterns used by `TextField` and the P1 widget catalog.

**Tech Stack:** Python 3.11+, dataclasses with slots, `EditorBuffer`, `SelectionController`, `KillRing`, `KeybindingManager`, `RenderResult`, `cell_width` helpers, existing widget theme helpers, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-11-tui-widgets-p1b-textarea-design.md`
- Existing patterns:
  - `src/loushang/tui/ui_parts/text_input.py`
  - `src/loushang/tui/ui_parts/widgets/field.py`
  - `src/loushang/tui/ui_parts/widgets/form.py`
  - `src/loushang/tui/ui_parts/widgets/dialog.py`
  - `src/loushang/tui/input.py`
  - `tests/tui/test_text_input.py`
  - `tests/tui/test_widgets_foundation.py`
  - `tests/tui/test_widgets_hardening.py`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/textarea.py`
  - Owns the public `TextArea` class.
  - Owns internal logical-line spans, cursor-to-line mapping, selection-to-line mapping, viewport adjustment, and `_TextAreaEditorTarget`.
- `tests/tui/test_widgets_textarea.py`
  - Focused tests for TextArea API, editing, rendering, viewport, selection, integration, docs example importability.
- `examples/tui/47_widgets_textarea.py`
  - Small runnable form/dialog-style TextArea composition example.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `TextArea`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `TextArea`.
- `src/loushang/tui/__init__.py`
  - Re-export `TextArea`.
- `tests/tui/test_widgets_hardening.py`
  - Add TextArea to small-constraint and theme hardening coverage once the widget exists.
- `docs/en/reference/tui-widgets.md`
  - Add P1B TextArea entry, usage snippet, theme tokens, and example link.
- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

Do not modify:

- `RenderLoop`, `InputRouter`, `SurfaceHost`, `Composer`, or `TextInput` behavior.
- Global default keybindings.

---

### Task 1: Add Failing TextArea API And Export Tests

**Files:**
- Create: `tests/tui/test_widgets_textarea.py`

- [ ] **Step 1: Create the focused test file with shared helpers**

Use the same helper style as the other widget tests:

```python
from __future__ import annotations

from typing import Any

import pytest

from loushang.tui import (
    RenderConstraints,
    TextArea,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import TextArea as UiTextArea
from loushang.tui.ui_parts.widgets import TextArea as WidgetTextArea


def render_result(part: Any, *, width: int = 40, height: int = 8):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)
```

- [ ] **Step 2: Add failing public export and initializer tests**

```python
def test_text_area_is_reexported_from_public_modules() -> None:
    assert TextArea is UiTextArea
    assert TextArea is WidgetTextArea


def test_text_area_accepts_initial_value_but_value_is_buffer_backed() -> None:
    area = TextArea(label="Notes", value="alpha\nbeta", placeholder="Type notes")

    assert area.value == "alpha\nbeta"
    with pytest.raises(AttributeError):
        area.value = "changed"  # type: ignore[misc]
```

- [ ] **Step 3: Add failing basic method tests**

```python
def test_text_area_programmatic_text_methods_preserve_newlines_and_clear_undo() -> None:
    area = TextArea(value="draft")

    area.set_text("one\ntwo")

    assert area.value == "one\ntwo"
    assert area.undo() is False

    area.clear()

    assert area.value == ""
    assert area.undo() is False
```

- [ ] **Step 4: Run the focused tests to verify they fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: FAIL during import because `TextArea` does not exist.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/tui/test_widgets_textarea.py
git commit -m "test(tui): add textarea widget api tests"
```

---

### Task 2: Implement TextArea Skeleton And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/textarea.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_textarea.py`

- [ ] **Step 1: Create `textarea.py` with state ownership and basic API**

Start with an `init=False` dataclass so `value` can be accepted by `__init__` but exposed as a read-only property:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.editor_buffer import EditorBuffer
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.kill_ring import KillRing
from loushang.tui.selection_controller import SelectionController
from loushang.tui.theme import ThemeResolver

__all__ = ["TextArea"]


@dataclass(frozen=True, slots=True)
class _LineSpan:
    index: int
    start: int
    end: int
    text: str


@dataclass(init=False, slots=True)
class TextArea:
    label: str
    placeholder: str
    help_text: str
    error: str
    height: int
    on_submit: Callable[[str], object] | None
    on_escape: Callable[[], object] | None
    on_change: Callable[[str], object] | None
    theme: ThemeResolver | None
    focused: bool
    _selection_theme_token: ClassVar[str] = "editor.selection"
    _buffer: EditorBuffer = field(init=False, repr=False)
    _selection_controller: SelectionController = field(init=False, repr=False)
    _kill_ring: KillRing = field(init=False, repr=False)
    _first_visible_line: int = field(default=0, init=False, repr=False)
    _scroll_column: int = field(default=0, init=False, repr=False)
    _last_action: Literal["kill", "yank", "type-word"] | None = field(default=None, init=False, repr=False)
```

The field list should match the spec:

```python
@dataclass(init=False, slots=True)
class TextArea:
    label: str
    placeholder: str
    help_text: str
    error: str
    height: int
    on_submit: Callable[[str], object] | None
    on_escape: Callable[[], object] | None
    on_change: Callable[[str], object] | None
    theme: ThemeResolver | None
    focused: bool
    _selection_theme_token: ClassVar[str] = "editor.selection"
    _buffer: EditorBuffer = field(init=False, repr=False)
    _selection_controller: SelectionController = field(init=False, repr=False)
    _kill_ring: KillRing = field(init=False, repr=False)
    _first_visible_line: int = field(default=0, init=False, repr=False)
    _scroll_column: int = field(default=0, init=False, repr=False)
    _last_action: Literal["kill", "yank", "type-word"] | None = field(default=None, init=False, repr=False)
```

Use this initializer shape:

```python
    def __init__(
        self,
        label: str = "",
        value: str = "",
        placeholder: str = "",
        help_text: str = "",
        error: str = "",
        height: int = 4,
        on_submit: Callable[[str], object] | None = None,
        on_escape: Callable[[], object] | None = None,
        on_change: Callable[[str], object] | None = None,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self.label = label
        self.placeholder = placeholder
        self.help_text = help_text
        self.error = error
        self.height = max(1, height)
        self.on_submit = on_submit
        self.on_escape = on_escape
        self.on_change = on_change
        self.theme = theme
        self.focused = focused
        self._buffer = EditorBuffer(max_undo_depth=100)
        self._selection_controller = SelectionController(
            length=lambda: len(self._buffer),
            cursor=lambda: self._buffer.cursor,
            set_cursor=self._buffer.move_cursor_to,
        )
        self._kill_ring = KillRing()
        self._first_visible_line = 0
        self._scroll_column = 0
        self._last_action = None
        self._buffer.set_text(value)
```

- [ ] **Step 2: Add minimal methods needed by Task 1**

```python
    @property
    def value(self) -> str:
        return self._buffer.value

    @property
    def selected_range(self) -> tuple[int, int] | None:
        return self._selection_controller.selected_range

    @property
    def kill_ring(self) -> tuple[str, ...]:
        return tuple(self._kill_ring)

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def set_text(self, text: str) -> None:
        self._buffer.set_text(text)
        self.clear_selection()
        self._reset_viewport()
        self._last_action = None

    def clear(self) -> None:
        self._buffer.clear()
        self.clear_selection()
        self._reset_viewport()
        self._last_action = None

    def undo(self) -> bool:
        before = self.value
        if not self._buffer.undo():
            return False
        self.clear_selection()
        self._last_action = None
        self._notify_change_if_needed(before)
        return True

    def redo(self) -> bool:
        before = self.value
        if not self._buffer.redo():
            return False
        self.clear_selection()
        self._last_action = None
        self._notify_change_if_needed(before)
        return True

    def clear_selection(self) -> None:
        self._selection_controller.clear()

    def editor_input_target(self) -> object:
        return _TextAreaEditorTarget(self)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        rows = [RenderLine(truncate_to_width(self.label, max_width=target_width, ellipsis=""))] if self.label else []
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(
        self,
        event: Any,
        *,
        keybindings: KeybindingManager | KeybindingConfig | None = None,
    ) -> bool:
        return False

    def _reset_viewport(self) -> None:
        self._first_visible_line = 0
        self._scroll_column = 0

    def _notify_change_if_needed(self, before: str) -> None:
        if self.value != before and self.on_change is not None:
            self.on_change(self.value)
```

Define a minimal target class so the module passes static checks; Task 3 will fill the full method surface:

```python
@dataclass(frozen=True, slots=True)
class _TextAreaEditorTarget:
    field: TextArea

    def insert_text(self, text: str) -> None:
        self.field._buffer.insert_text(text)

    def paste(self, text: str) -> None:
        self.field._buffer.insert_text(text)

    def undo(self) -> None:
        self.field.undo()

    def redo(self) -> None:
        self.field.redo()
```

- [ ] **Step 3: Re-export `TextArea` from public modules**

Update:

```python
from .textarea import TextArea as TextArea
```

in `src/loushang/tui/ui_parts/widgets/__init__.py`, then thread the same symbol through `src/loushang/tui/ui_parts/__init__.py` and `src/loushang/tui/__init__.py` imports plus `__all__`.

- [ ] **Step 4: Run Task 1 tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: PASS for public exports and programmatic value tests; failures for editing/rendering tests are not present yet.

- [ ] **Step 5: Run Ruff on touched production files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/textarea.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_textarea.py
```

Expected: PASS.

- [ ] **Step 6: Commit skeleton and exports**

```bash
git add src/loushang/tui/ui_parts/widgets/textarea.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_textarea.py
git commit -m "feat(tui): add textarea widget skeleton"
```

---

### Task 3: Add And Implement Multi-Line Editing Behavior

**Files:**
- Modify: `tests/tui/test_widgets_textarea.py`
- Modify: `src/loushang/tui/ui_parts/widgets/textarea.py`

- [ ] **Step 1: Add failing text, paste, newline, callback, and keybinding tests**

Add `InputEvent` to the `loushang.tui` imports in `tests/tui/test_widgets_textarea.py`.

```python
def test_text_area_handles_text_paste_enter_submit_and_escape() -> None:
    submits: list[str] = []
    escapes: list[str] = []
    changes: list[str] = []
    area = TextArea(on_submit=submits.append, on_escape=lambda: escapes.append("escape"), on_change=changes.append)

    assert area.handle_input(InputEvent(kind="text", text="alpha\nbeta")) is True
    assert area.value == "alpha\nbeta"

    assert area.handle_input(InputEvent(kind="key", key="enter")) is True
    assert area.value == "alpha\nbeta\n"
    assert submits == []

    assert area.handle_input(InputEvent(kind="paste", text="gamma\ndelta")) is True
    assert area.value == "alpha\nbeta\ngamma\ndelta"

    assert area.handle_input(
        InputEvent(kind="key", key="ctrl+enter"),
        keybindings={"tui.input.submit": ("ctrl+enter",)},
    ) is True
    assert submits == ["alpha\nbeta\ngamma\ndelta"]

    assert area.handle_input(InputEvent(kind="key", key="escape")) is True
    assert escapes == ["escape"]
    assert changes == ["alpha\nbeta", "alpha\nbeta\n", "alpha\nbeta\ngamma\ndelta"]
```

```python
def test_text_area_leaves_up_and_down_available_to_parent_containers() -> None:
    area = TextArea(value="alpha\nbeta")

    assert area.handle_input(InputEvent(kind="key", key="up")) is False
    assert area.handle_input(InputEvent(kind="key", key="down")) is False
```

- [ ] **Step 2: Add failing editor-target operation tests**

```python
def test_text_area_editor_target_preserves_multiline_edits_and_undo() -> None:
    changes: list[str] = []
    area = TextArea(on_change=changes.append)
    target = area.editor_input_target()

    target.insert_text("alpha")
    target.paste("\nbeta")
    target.delete_backward()

    assert area.value == "alpha\nbet"
    assert changes == ["alpha", "alpha\nbeta", "alpha\nbet"]
    assert area.undo() is True
    assert area.value == "alpha\nbeta"
```

```python
def test_text_area_line_boundaries_kill_and_delete_respect_current_logical_line() -> None:
    area = TextArea(value="alpha\nbeta")
    target = area.editor_input_target()

    target.move_to_line_start()
    target.delete_backward()
    assert area.value == "alphabeta"
    assert area.undo() is True
    assert area.value == "alpha\nbeta"

    target.move_to_line_end()
    target.kill_to_line_start()
    assert area.value == "alpha\n"
    assert area.kill_ring == ("beta",)
```

```python
def test_text_area_multiline_selection_replaces_atomically() -> None:
    area = TextArea(value="ab\ncd")
    target = area.editor_input_target()

    target.select_char_left()
    target.select_char_left()
    target.select_char_left()
    assert area.selected_range == (2, 5)

    target.insert_text("X")

    assert area.value == "abX"
    assert area.selected_range is None
    assert area.undo() is True
    assert area.value == "ab\ncd"
```

- [ ] **Step 3: Run focused editing tests to verify they fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: FAIL because `handle_input()` and `_TextAreaEditorTarget` do not implement editing yet.

- [ ] **Step 4: Implement editing helpers by adapting `TextInput` without single-line normalization**

Implement these public editing methods on `TextArea`:

```python
    def has_selection(self) -> bool:
        return self._selection_controller.has_selection()

    def set_selection(self, anchor: int, focus: int) -> None:
        self._selection_controller.set(anchor, focus)

    def insert_text(self, text: str) -> None:
        selection = self.selected_range
        if selection is not None:
            self._buffer.replace_range(selection[0], selection[1], text, record=False)
            self.clear_selection()
            return
        self._buffer.insert_text(text, record=False)

    def insert_newline(self) -> None:
        self.insert_text("\n")

    def delete_backward(self) -> None:
        if self._delete_selection_or_none():
            return
        self._buffer.delete_backward(record=False)

    def delete_forward(self) -> None:
        if self._delete_selection_or_none():
            return
        self._buffer.delete_forward(record=False)
```

Implement movement and selection using `EditorBuffer` line helpers for logical-line boundaries:

```python
    def move_left(self) -> None:
        self._buffer.move_left()
        self._after_cursor_move()

    def move_right(self) -> None:
        self._buffer.move_right()
        self._after_cursor_move()

    def move_word_left(self) -> None:
        self._buffer.move_word_left()
        self._after_cursor_move()

    def move_word_right(self) -> None:
        self._buffer.move_word_right()
        self._after_cursor_move()

    def move_to_line_start(self) -> None:
        self._buffer.move_to_line_start()
        self._after_cursor_move()

    def move_to_line_end(self) -> None:
        self._buffer.move_to_line_end()
        self._after_cursor_move()

    def select_char_left(self) -> None:
        self._extend_selection_to(self._buffer.cursor - 1)

    def select_char_right(self) -> None:
        self._extend_selection_to(self._buffer.cursor + 1)

    def select_word_left(self) -> None:
        self._extend_selection_to(self._buffer.word_left_index())

    def select_word_right(self) -> None:
        self._extend_selection_to(self._buffer.word_right_index())

    def select_line_start(self) -> None:
        self._extend_selection_to(self._line_start_index())

    def select_line_end(self) -> None:
        self._extend_selection_to(self._line_end_index())
```

Add `_line_start_index()` and `_line_end_index()` by scanning `grapheme_clusters(self.value)` around `self._buffer.cursor`; do not call private `EditorBuffer` methods.
Add `grapheme_clusters` to the `loushang.tui.cell_width` imports when these helpers are introduced.

- [ ] **Step 5: Implement kill/yank and undoable edit wrappers**

Port the `TextInput` `_apply_edit`, `_delete_selection_or_none`, `_kill_selection_or_none`, `_push_kill`, `_rotate_kill_ring`, `_after_cursor_move`, `_range_text`, `_selection_style` helpers.

For `kill_to_line_start()` and `kill_to_line_end()`, use the current logical line instead of the whole buffer:

```python
    def kill_to_line_start(self) -> bool:
        if self._kill_selection_or_none(prepend=True):
            return True
        start = self._line_start_index()
        cursor = self._buffer.cursor
        if start == cursor:
            return False
        killed = self._range_text(start, cursor)

        def edit() -> None:
            self._buffer.delete_range(start, cursor, record=False)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def kill_to_line_end(self) -> bool:
        if self._kill_selection_or_none(prepend=False):
            return True
        end = self._line_end_index()
        cursor = self._buffer.cursor
        if end == cursor:
            return False
        killed = self._range_text(cursor, end)

        def edit() -> None:
            self._buffer.delete_range(cursor, end, record=False)
            self._push_kill(killed, prepend=False)
            self._last_action = "kill"

        return self._apply_edit(edit)
```

- [ ] **Step 6: Implement `handle_input()` key semantics**

The key order matters:

1. text and paste insert verbatim.
2. key release returns `False`.
3. plain `enter` inserts newline before submit handling.
4. `tui.input.newLine` inserts newline.
5. non-plain-enter `tui.input.submit` invokes `on_submit(value)`.
6. `tui.select.cancel` invokes `on_escape()`.
7. editor editing keys are delegated.
8. up/down are not handled in P1B.

Use this shape:

```python
    def handle_input(
        self,
        event: Any,
        *,
        keybindings: KeybindingManager | KeybindingConfig | None = None,
    ) -> bool:
        kind = getattr(event, "kind", "")
        if kind == "text":
            text = getattr(event, "text", "")
            if not text:
                return False
            changed = self._apply_edit(lambda: self.insert_text(text))
            if changed:
                self._last_action = "type-word"
            return True
        if kind == "paste":
            text = getattr(event, "text", "")
            if not text:
                return False
            changed = self._apply_edit(lambda: self.insert_text(text))
            if changed:
                self._last_action = None
            return True
        if kind != "key" or getattr(event, "event_type", "press") == "release":
            return False

        key = getattr(event, "key", "")
        manager = keybindings if isinstance(keybindings, KeybindingManager) else KeybindingManager(keybindings)
        if key == "enter" or manager.matches(key, "tui.input.newLine"):
            changed = self._apply_edit(self.insert_newline)
            if changed:
                self._last_action = None
            return True
        if manager.matches(key, "tui.input.submit"):
            if self.on_submit is not None:
                self.on_submit(self.value)
            return True
        if manager.matches(key, "tui.select.cancel"):
            if self.on_escape is not None:
                self.on_escape()
            return True
        return self.handle_editing_key(key, keybindings=manager)
```

- [ ] **Step 7: Implement `_TextAreaEditorTarget`**

Mirror `_TextInputEditorTarget`, mapping target methods to TextArea methods. `insert_text()` and `paste()` must wrap edits with `_apply_edit()`, preserve newlines, and notify `on_change`.

```python
@dataclass(frozen=True, slots=True)
class _TextAreaEditorTarget:
    field: TextArea

    def insert_text(self, text: str) -> None:
        changed = self.field._apply_edit(lambda: self.field.insert_text(text))
        if changed:
            self.field._last_action = "type-word"

    def paste(self, text: str) -> None:
        changed = self.field._apply_edit(lambda: self.field.insert_text(text))
        if changed:
            self.field._last_action = None

    # Then delegate movement, selection, deletion, kill/yank, undo, redo.
```

- [ ] **Step 8: Run editing tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit editing behavior**

```bash
git add tests/tui/test_widgets_textarea.py src/loushang/tui/ui_parts/widgets/textarea.py
git commit -m "feat(tui): implement textarea multiline editing"
```

---

### Task 4: Add And Implement Rendering, Height Budget, And Theme Behavior

**Files:**
- Modify: `tests/tui/test_widgets_textarea.py`
- Modify: `tests/tui/test_widgets_hardening.py`
- Modify: `src/loushang/tui/ui_parts/widgets/textarea.py`

- [ ] **Step 1: Add failing layout and detail-row tests**

```python
def test_text_area_renders_label_body_placeholder_and_detail_with_height_precedence() -> None:
    area = TextArea(label="Notes", placeholder="Type notes", error="Required", height=4)

    assert plain_lines(area, width=20, height=5) == ("Notes", "Type notes", "", "", "Required")
    assert plain_lines(area, width=20, height=2) == ("Notes", "Type notes")
```

```python
def test_text_area_error_takes_precedence_over_help_and_visible_width_is_constrained() -> None:
    area = TextArea(label="Very long label", value="Very long value", help_text="Helpful", error="Required", height=2)
    area.editor_input_target().move_to_line_start()

    lines = render_lines(area, width=8, height=4)

    assert plain_lines(area, width=8, height=4) == ("Very lo", "Very lo", "", "Require")
    assert_widths_within(lines, 8)
```

- [ ] **Step 2: Add failing cursor and placeholder tests**

```python
def test_text_area_cursor_maps_to_body_row_after_label() -> None:
    area = TextArea(label="Notes", value="ab\ncd", height=4)

    result = render_result(area, width=20, height=6)

    assert plain_lines(area, width=20, height=6)[:3] == ("Notes", "ab", "cd")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (2, 2)
```

```python
def test_text_area_placeholder_does_not_move_cursor() -> None:
    area = TextArea(placeholder="Type notes", height=3)

    result = render_result(area, width=20, height=3)

    assert plain_lines(area, width=20, height=3) == ("Type notes", "", "")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (0, 0)
```

- [ ] **Step 3: Add failing theme hardening tests**

Add `TextArea` to the `loushang.tui` imports in `tests/tui/test_widgets_hardening.py`, then add:

```python
def test_text_area_themes_label_body_placeholder_help_and_error() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.textArea.label": {"color": "cyan"},
            "widget.textArea.text": {"color": "green"},
            "widget.textArea.placeholder": {"dim": True},
            "widget.textArea.help": {"color": "yellow"},
            "widget.textArea.error": {"color": "red"},
        }
    )
    area = TextArea(label="Notes", value="", placeholder="Type", help_text="Helpful", error="Required", theme=theme)

    raw = render_lines(area, width=20, height=4)

    assert raw[0].startswith("\x1b[36m")
    assert raw[1].startswith("\x1b[2m")
    assert raw[-1].startswith("\x1b[31m")
    assert tuple(strip_control_sequences(line) for line in raw) == ("Notes", "Type", "", "Required")
    assert all(visible_width(line) <= 20 for line in raw)
```

Also add a TextArea case to `p0a_constraint_cases()` or create a small P1 constraint list:

```python
TextArea(label="Very long label", value="Very long value\nNext", help_text="Very long help")
```

- [ ] **Step 4: Run rendering tests to verify they fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_hardening.py -q
```

Expected: FAIL because render still returns only the label skeleton.

- [ ] **Step 5: Implement logical-line spans and cursor location**

Add helpers:

```python
    def _line_spans(self) -> tuple[_LineSpan, ...]:
        clusters = list(grapheme_clusters(self.value))
        spans: list[_LineSpan] = []
        start = 0
        current: list[str] = []
        for index, cluster in enumerate(clusters):
            if cluster == "\n":
                spans.append(_LineSpan(len(spans), start, index, "".join(current)))
                start = index + 1
                current = []
            else:
                current.append(cluster)
        spans.append(_LineSpan(len(spans), start, len(clusters), "".join(current)))
        return tuple(spans)

    def _cursor_location(self, spans: tuple[_LineSpan, ...]) -> tuple[int, int]:
        cursor = self._buffer.cursor
        for span in spans:
            if span.start <= cursor <= span.end:
                column = visible_width(self._range_text(span.start, cursor))
                return span.index, column
        last = spans[-1]
        return last.index, visible_width(last.text)
```

- [ ] **Step 6: Implement render height-budget precedence exactly as the spec states**

Use this render structure:

```python
    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None

        if self.label and len(lines) < constraints.max_height:
            label = truncate_to_width(self.label, max_width=target_width, ellipsis="")
            lines.append(RenderLine(style_text(label, self.theme, "widget.textArea.label")))

        remaining = constraints.max_height - len(lines)
        if remaining <= 0:
            return RenderResult.from_lines(lines, constraints=constraints)

        detail = self.error or self.help_text
        detail_rows = 1 if detail and remaining >= 2 else 0
        body_rows = min(self.height, remaining - detail_rows)
        if body_rows <= 0:
            return RenderResult.from_lines(lines, constraints=constraints)

        spans = self._line_spans()
        cursor_line, cursor_column = self._cursor_location(spans)
        self._ensure_cursor_visible(cursor_line, cursor_column, visible_rows=body_rows, width=target_width, total_lines=len(spans))

        body_start_row = len(lines)
        lines.extend(self._render_body_lines(spans, rows=body_rows, width=target_width))

        relative_cursor_row = cursor_line - self._first_visible_line
        if 0 <= relative_cursor_row < body_rows:
            rendered_line = lines[body_start_row + relative_cursor_row].text
            cursor_col = max(0, cursor_column - self._scroll_column)
            cursor_col = min(cursor_col, visible_width(rendered_line))
            cursor = CursorDeclaration(row=body_start_row + relative_cursor_row, column=cursor_col)

        if detail_rows:
            detail_token = "widget.textArea.error" if self.error else "widget.textArea.help"
            rendered_detail = truncate_to_width(detail, max_width=target_width, ellipsis="")
            lines.append(RenderLine(style_text(rendered_detail, self.theme, detail_token)))

        return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints, cursor=cursor)
```

- [ ] **Step 7: Implement `_render_body_lines()` without soft wrapping**

```python
    def _render_body_lines(self, spans: tuple[_LineSpan, ...], *, rows: int, width: int) -> list[RenderLine]:
        rendered: list[RenderLine] = []
        for offset in range(rows):
            line_index = self._first_visible_line + offset
            span = spans[line_index] if line_index < len(spans) else None
            if not self.value and offset == 0:
                text = truncate_to_width(self.placeholder, max_width=width, ellipsis="")
                rendered.append(RenderLine(style_text(text, self.theme, "widget.textArea.placeholder")))
                continue
            raw = "" if span is None else span.text
            visible = slice_by_column(raw, start=self._scroll_column, length=width).text
            if span is not None:
                selection = self._line_selection_display_range(span)
                if selection is not None:
                    visible = highlight_selection_by_columns(
                        visible,
                        selection_range=(selection[0] - self._scroll_column, selection[1] - self._scroll_column),
                        selection_style=self._selection_style(),
                    )
            visible = truncate_to_width(visible, max_width=width, ellipsis="")
            rendered.append(RenderLine(style_text(visible, self.theme, "widget.textArea.text")))
        return rendered
```

- [ ] **Step 8: Implement viewport and theme helpers**

```python
    def _ensure_cursor_visible(
        self,
        cursor_line: int,
        cursor_column: int,
        *,
        visible_rows: int,
        width: int,
        total_lines: int,
    ) -> None:
        if cursor_line < self._first_visible_line:
            self._first_visible_line = cursor_line
        elif cursor_line >= self._first_visible_line + visible_rows:
            self._first_visible_line = cursor_line - visible_rows + 1
        self._first_visible_line = max(0, min(self._first_visible_line, max(0, total_lines - visible_rows)))

        if cursor_column < self._scroll_column:
            self._scroll_column = cursor_column
        elif cursor_column > self._scroll_column + width:
            self._scroll_column = cursor_column - width
        self._scroll_column = max(0, self._scroll_column)
```

Use `_selection_style()` with `editor.selection` and `DEFAULT_SELECTION_STYLE` exactly as `TextInput` does.
Add these imports in this task when rendering and selection styling are implemented:

```python
from loushang.tui.cell_width import grapheme_clusters, slice_by_column, visible_width
from loushang.tui.core import CursorDeclaration
from loushang.tui.selection_rendering import DEFAULT_SELECTION_STYLE, highlight_selection_by_columns
from loushang.tui.theme import ThemeStyle
from loushang.tui.ui_parts.widgets._utils import style_text
```

- [ ] **Step 9: Run rendering and hardening tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit rendering behavior**

```bash
git add tests/tui/test_widgets_textarea.py tests/tui/test_widgets_hardening.py src/loushang/tui/ui_parts/widgets/textarea.py
git commit -m "feat(tui): render textarea body and viewport"
```

---

### Task 5: Add And Implement Viewport Edge Cases And Selection Rendering

**Files:**
- Modify: `tests/tui/test_widgets_textarea.py`
- Modify: `src/loushang/tui/ui_parts/widgets/textarea.py`

- [ ] **Step 1: Add failing vertical and horizontal viewport tests**

```python
def test_text_area_scrolls_vertically_to_keep_cursor_visible() -> None:
    area = TextArea(value="one\ntwo\nthree\nfour", height=2)

    result = render_result(area, width=20, height=2)

    assert plain_lines(area, width=20, height=2) == ("three", "four")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("four"))
```

```python
def test_text_area_scrolls_horizontally_across_visible_body_rows() -> None:
    area = TextArea(value="abcdef\n123456", height=2)

    result = render_result(area, width=4, height=2)

    assert plain_lines(area, width=4, height=2) == ("def", "456")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, 3)
```

- [ ] **Step 2: Add failing selection rendering test**

Add `ThemeResolver` to the `loushang.tui` imports in `tests/tui/test_widgets_textarea.py` if it was not already added by Task 4.

```python
def test_text_area_selection_highlight_uses_editor_selection_theme_token() -> None:
    area = TextArea(
        value="ab\ncd",
        theme=ThemeResolver(defaults={"editor.selection": {"color": "cyan", "bold": True}}),
    )
    target = area.editor_input_target()
    target.select_char_left()

    raw = render_lines(area, width=20, height=3)[1]

    assert strip_control_sequences(raw) == "cd"
    assert "\x1b[1;36md\x1b[22;39m" in raw
```

- [ ] **Step 3: Run tests to verify failures or catch edge bugs**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: FAIL if Task 4 implementation does not yet fully handle shared horizontal scroll or per-line selection overlap.

- [ ] **Step 4: Implement per-line selection overlap**

Use absolute cluster indexes from `_LineSpan`:

```python
    def _line_selection_display_range(self, span: _LineSpan) -> tuple[int, int] | None:
        selection = self.selected_range
        if selection is None:
            return None
        start, end = selection
        overlap_start = max(start, span.start)
        overlap_end = min(end, span.end)
        if overlap_start >= overlap_end:
            return None
        display_start = visible_width(self._range_text(span.start, overlap_start))
        display_end = visible_width(self._range_text(span.start, overlap_end))
        if display_start == display_end:
            return None
        return display_start, display_end
```

Keep selection styling before the body text style is applied so body styling re-applies cleanly after selection reset codes.

- [ ] **Step 5: Fix viewport edge cases if needed**

Verify `_ensure_cursor_visible()` uses `>` rather than `>=` for the right edge, matching `TextInput`: a cursor may sit one column after the last visible glyph. Clamp `_first_visible_line` after total line count is known.

- [ ] **Step 6: Run focused and adjacent tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit viewport and selection edge coverage**

```bash
git add tests/tui/test_widgets_textarea.py src/loushang/tui/ui_parts/widgets/textarea.py
git commit -m "test(tui): cover textarea viewport edges"
```

---

### Task 6: Add Form/Dialog Integration, Docs, And Example

**Files:**
- Modify: `tests/tui/test_widgets_textarea.py`
- Create: `examples/tui/47_widgets_textarea.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`

- [ ] **Step 1: Add failing Form/Dialog integration tests**

Add `Dialog`, `Form`, `FormRow`, and `InputEvent` to the `loushang.tui` imports in `tests/tui/test_widgets_textarea.py`.

```python
def test_text_area_integrates_with_form_values_and_editor_target() -> None:
    area = TextArea(value="")
    form = Form([FormRow("notes", area)])
    form.focus()

    assert form.handle_input(InputEvent(kind="text", text="one\ntwo")) is True
    assert form.values() == {"notes": "one\ntwo"}

    target = form.editor_input_target()
    assert target is not None
    target.insert_text("\nthree")

    assert area.value == "one\ntwo\nthree"
```

```python
def test_text_area_dialog_delegates_active_editor_target() -> None:
    area = TextArea(value="")
    form = Form([FormRow("notes", area)])
    dialog = Dialog(title="Edit notes", body=form)
    dialog.focus()

    target = dialog.editor_input_target()
    assert target is not None
    target.insert_text("alpha\nbeta")

    assert area.value == "alpha\nbeta"
```

- [ ] **Step 2: Add failing example import test**

Add `import runpy` near the top of `tests/tui/test_widgets_textarea.py`.

```python
def test_widgets_textarea_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/47_widgets_textarea.py", run_name="__test__")

    assert callable(namespace["build_app"])
```

- [ ] **Step 3: Run tests to verify the example is missing**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py::test_widgets_textarea_example_imports -q
```

Expected: FAIL because `examples/tui/47_widgets_textarea.py` does not exist.

- [ ] **Step 4: Create `examples/tui/47_widgets_textarea.py`**

Follow the structure of `examples/tui/46_widgets_table.py`, but use a small `Form` with a focused `TextArea` and a status line:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    Form,
    FormRow,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TextArea,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class TextAreaApp(FocusableMixin):
    notes: TextArea = field(default_factory=lambda: TextArea(label="Notes", placeholder="Write notes", height=5))
    message: str = "Enter adds a line. Press q to quit."
    form: Form = field(init=False)

    def __post_init__(self) -> None:
        super().__init__()
        self.form = Form([FormRow("notes", self.notes)])
        self.form.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body = self.form.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2)))
        rows = [
            *body.lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=body.cursor)

    def handle_input(self, event: Any) -> object:
        return self.form.handle_input(event)
```

Complete the example with `build_app()`, async `main()`, and `if __name__ == "__main__"` exactly like the table example.

- [ ] **Step 5: Update docs**

In both English and Chinese widget reference files:

- Add `TextArea` to a new P1B Text Controls or P1B TextArea section.
- Move `TextArea` out of the planned catalog line.
- Add a short code snippet:

```python
from loushang.tui import TextArea

notes = TextArea(label="Notes", placeholder="Write notes", height=5)
notes.focus()
```

- Add theme tokens:
  - `widget.textArea.label`
  - `widget.textArea.placeholder`
  - `widget.textArea.text`
  - `widget.textArea.error`
  - `widget.textArea.help`
- Add the example link:
  - `examples/tui/47_widgets_textarea.py`

- [ ] **Step 6: Run docs/example tests and Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/test_widgets_textarea.py examples/tui/47_widgets_textarea.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
```

Expected: PASS.

- [ ] **Step 7: Commit integration, docs, and example**

```bash
git add tests/tui/test_widgets_textarea.py examples/tui/47_widgets_textarea.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document textarea widget"
```

---

### Task 7: Final Verification And PR Readiness

**Files:**
- No new files unless verification exposes a focused fix.

- [ ] **Step 1: Run focused TextArea suite**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget and input suites**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full TUI suite**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/47_widgets_textarea.py docs
```

Expected: PASS.

- [ ] **Step 5: Inspect branch diff**

Run:

```bash
git status --short
git diff --stat origin/main...HEAD
```

Expected: only TextArea implementation, tests, docs, example, and the spec/plan commits are present.

- [ ] **Step 6: Commit any final fixes**

If verification required a fix:

```bash
git add src/loushang/tui/ui_parts/widgets/textarea.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_hardening.py examples/tui/47_widgets_textarea.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "fix(tui): stabilize textarea widget"
```

If no final fixes were needed, do not create an empty commit.

---

## Implementation Notes

- `TextArea` intentionally duplicates some `TextInput` editing code in P1B. Do not extract shared helpers in this slice unless a test proves the duplication is causing a real bug.
- `TextArea` must not normalize `\n` to spaces.
- Plain `enter` is newline, even though the global default `tui.input.submit` is also `enter`.
- Submit tests must use an explicit non-enter binding such as `ctrl+enter`.
- `up` and `down` remain unhandled in P1B so parent containers can use them.
- `TextArea` should not implement Composer features: history, slash commands, completions, paste markers, image handling, markdown preview, or prompt-specific behavior.
- Rendering must use `autowrap_safe_width(constraints.width)` and must not soft-wrap logical lines.
- Height-budget precedence must match the spec: label first, then at least one body row, then detail only when there is room for body plus detail.
- Selection rendering is line-local but selection indexes are absolute buffer cluster indexes.

## Success Criteria

- `TextArea` is exported from `loushang.tui`, `loushang.tui.ui_parts`, and `loushang.tui.ui_parts.widgets`.
- Programmatic value setup, `set_text()`, `clear()`, undo, and redo preserve multi-line content correctly.
- Direct `handle_input()` preserves newlines in text and paste events.
- Plain `enter` inserts a newline; explicit non-enter submit keybindings invoke `on_submit(value)`.
- Existing editor target routing can edit a focused `TextArea`.
- Rendering obeys width, height, label, body, help/error, placeholder, theme, and cursor rules.
- Vertical and horizontal viewport behavior keeps the cursor visible deterministically.
- Multi-line selection replacement and visible selection styling work.
- `TextArea` works inside existing `Form` and `Dialog` focus/editor-target delegation.
- Docs and example import tests pass.
- Existing TUI tests remain green.

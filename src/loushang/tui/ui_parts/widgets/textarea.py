from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    grapheme_clusters,
    truncate_to_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.editor_buffer import EditorBuffer
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.kill_ring import KillRing
from loushang.tui.selection_controller import SelectionController
from loushang.tui.selection_rendering import DEFAULT_SELECTION_STYLE
from loushang.tui.theme import ThemeResolver, ThemeStyle

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

    def has_selection(self) -> bool:
        return self._selection_controller.has_selection()

    def set_selection(self, anchor: int, focus: int) -> None:
        self._selection_controller.set(anchor, focus)

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

    def handle_editing_key(
        self,
        key: str,
        *,
        keybindings: KeybindingManager | KeybindingConfig | None = None,
    ) -> bool:
        manager = keybindings if isinstance(keybindings, KeybindingManager) else KeybindingManager(keybindings)
        if manager.matches(key, "tui.editor.undo"):
            return self.undo()
        if manager.matches(key, "tui.editor.redo"):
            return self.redo()
        if manager.matches(key, "tui.editor.yank"):
            return self.yank()
        if manager.matches(key, "tui.editor.yankPop"):
            return self.yank_pop()
        if manager.matches(key, "tui.editor.selectCharLeft"):
            self.select_char_left()
            return True
        if manager.matches(key, "tui.editor.selectCharRight"):
            self.select_char_right()
            return True
        if manager.matches(key, "tui.editor.selectWordLeft"):
            self.select_word_left()
            return True
        if manager.matches(key, "tui.editor.selectWordRight"):
            self.select_word_right()
            return True
        if manager.matches(key, "tui.editor.selectLineStart"):
            self.select_line_start()
            return True
        if manager.matches(key, "tui.editor.selectLineEnd"):
            self.select_line_end()
            return True
        if manager.matches(key, "tui.editor.cursorLeft"):
            self.move_left()
            return True
        if manager.matches(key, "tui.editor.cursorRight"):
            self.move_right()
            return True
        if manager.matches(key, "tui.editor.cursorWordLeft"):
            self.move_word_left()
            return True
        if manager.matches(key, "tui.editor.cursorWordRight"):
            self.move_word_right()
            return True
        if manager.matches(key, "tui.editor.cursorLineStart"):
            self.move_to_line_start()
            return True
        if manager.matches(key, "tui.editor.cursorLineEnd"):
            self.move_to_line_end()
            return True
        if manager.matches(key, "tui.editor.deleteCharBackward"):
            self._last_action = None
            return self._apply_edit(self.delete_backward)
        if manager.matches(key, "tui.editor.deleteCharForward"):
            self._last_action = None
            return self._apply_edit(self.delete_forward)
        if manager.matches(key, "tui.editor.deleteWordBackward"):
            return self.delete_word_backward()
        if manager.matches(key, "tui.editor.deleteWordForward"):
            return self.delete_word_forward()
        if manager.matches(key, "tui.editor.deleteToLineStart"):
            return self.kill_to_line_start()
        if manager.matches(key, "tui.editor.deleteToLineEnd"):
            return self.kill_to_line_end()
        return False

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

    def delete_word_backward(self) -> bool:
        if self._kill_selection_or_none(prepend=True):
            return True
        start = self._buffer.word_left_index()
        cursor = self._buffer.cursor
        if start == cursor:
            return False
        killed = self._range_text(start, cursor)

        def edit() -> None:
            self._buffer.delete_range(start, cursor, record=False)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def delete_word_forward(self) -> bool:
        if self._kill_selection_or_none(prepend=False):
            return True
        end = self._buffer.word_right_index()
        cursor = self._buffer.cursor
        if end == cursor:
            return False
        killed = self._range_text(cursor, end)

        def edit() -> None:
            self._buffer.delete_range(cursor, end, record=False)
            self._push_kill(killed, prepend=False)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def yank(self) -> bool:
        text = self._kill_ring.peek()
        if text is None:
            return False
        changed = self._apply_edit(lambda: self.insert_text(text))
        if changed:
            self._last_action = "yank"
        return changed

    def yank_pop(self) -> bool:
        if self._last_action != "yank" or len(self._kill_ring) <= 1:
            return False
        previous = self._kill_ring.peek()
        if previous is None:
            return False
        previous_clusters = list(grapheme_clusters(previous))
        start = self._buffer.cursor - len(previous_clusters)
        if start < 0:
            return False
        if self._range_text(start, self._buffer.cursor) != previous:
            return False

        def edit() -> None:
            self._buffer.delete_range(start, self._buffer.cursor, record=False)
            self._rotate_kill_ring()
            replacement = self._kill_ring.peek()
            if replacement is not None:
                self.insert_text(replacement)
            self._last_action = "yank"

        return self._apply_edit(edit)

    def _reset_viewport(self) -> None:
        self._first_visible_line = 0
        self._scroll_column = 0

    def _apply_edit(self, edit: Callable[[], None]) -> bool:
        before = self.value
        if not self._buffer.apply_edit(edit):
            return False
        self._notify_change_if_needed(before)
        return True

    def _delete_selection_or_none(self) -> bool:
        selection = self.selected_range
        if selection is None:
            return False
        self._buffer.delete_range(selection[0], selection[1], record=False)
        self.clear_selection()
        self._last_action = None
        return True

    def _kill_selection_or_none(self, *, prepend: bool) -> bool:
        selection = self.selected_range
        if selection is None:
            return False
        killed = self._range_text(*selection)
        if not killed:
            self.clear_selection()
            return True

        def edit() -> None:
            self._buffer.delete_range(selection[0], selection[1], record=False)
            self._push_kill(killed, prepend=prepend)
            self.clear_selection()

        return self._apply_edit(edit)

    def _notify_change_if_needed(self, before: str) -> None:
        if self.value != before and self.on_change is not None:
            self.on_change(self.value)

    def _push_kill(self, text: str, *, prepend: bool) -> None:
        self._kill_ring.push(text, prepend=prepend, accumulate=self._last_action == "kill")

    def _rotate_kill_ring(self) -> None:
        self._kill_ring.rotate()

    def _line_start_index(self) -> int:
        clusters = list(grapheme_clusters(self.value))
        index = self._buffer.cursor
        while index > 0 and clusters[index - 1] != "\n":
            index -= 1
        return index

    def _line_end_index(self) -> int:
        clusters = list(grapheme_clusters(self.value))
        index = self._buffer.cursor
        while index < len(clusters) and clusters[index] != "\n":
            index += 1
        return index

    def _extend_selection_to(self, target: int) -> None:
        self._selection_controller.extend_to(target)
        self._last_action = None

    def _after_cursor_move(self) -> None:
        self.clear_selection()
        self._last_action = None

    def _range_text(self, start: int, end: int) -> str:
        return "".join(grapheme_clusters(self.value)[start:end])

    def _selection_style(self) -> ThemeStyle:
        if self.theme is not None and self._selection_theme_token:
            resolved = self.theme.resolve(self._selection_theme_token)
            if resolved:
                return resolved
        return DEFAULT_SELECTION_STYLE


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

    def move_left(self) -> None:
        self.field.move_left()

    def move_right(self) -> None:
        self.field.move_right()

    def move_word_left(self) -> None:
        self.field.move_word_left()

    def move_word_right(self) -> None:
        self.field.move_word_right()

    def move_to_line_start(self) -> None:
        self.field.move_to_line_start()

    def move_to_line_end(self) -> None:
        self.field.move_to_line_end()

    def select_char_left(self) -> None:
        self.field.select_char_left()

    def select_char_right(self) -> None:
        self.field.select_char_right()

    def select_word_left(self) -> None:
        self.field.select_word_left()

    def select_word_right(self) -> None:
        self.field.select_word_right()

    def select_line_start(self) -> None:
        self.field.select_line_start()

    def select_line_end(self) -> None:
        self.field.select_line_end()

    def delete_backward(self) -> None:
        self.field._last_action = None
        self.field._apply_edit(self.field.delete_backward)

    def delete_forward(self) -> None:
        self.field._last_action = None
        self.field._apply_edit(self.field.delete_forward)

    def delete_word_backward(self) -> None:
        self.field.delete_word_backward()

    def delete_word_forward(self) -> None:
        self.field.delete_word_forward()

    def kill_to_line_start(self) -> None:
        self.field.kill_to_line_start()

    def kill_to_line_end(self) -> None:
        self.field.kill_to_line_end()

    def yank(self) -> None:
        self.field.yank()

    def yank_pop(self) -> None:
        self.field.yank_pop()

    def undo(self) -> None:
        self.field.undo()

    def redo(self) -> None:
        self.field.redo()

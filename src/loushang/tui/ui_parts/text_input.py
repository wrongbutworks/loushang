from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    grapheme_clusters,
    slice_by_column,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.editor_buffer import EditorBuffer
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.kill_ring import KillRing
from loushang.tui.selection_controller import SelectionController
from loushang.tui.selection_rendering import (
    DEFAULT_SELECTION_STYLE,
    highlight_selection_by_columns,
)
from loushang.tui.theme import ThemeResolver, ThemeStyle

__all__ = ["TextInput"]


@dataclass(slots=True)
class TextInput:
    prompt: str = ""
    placeholder: str = ""
    on_submit: Callable[[str], object] | None = None
    on_escape: Callable[[], object] | None = None
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    selection_theme_token: str = "editor.selection"
    focused: bool = False
    _buffer: EditorBuffer = field(default_factory=lambda: EditorBuffer(max_undo_depth=100), repr=False)
    _selection_controller: SelectionController = field(init=False, repr=False)
    _scroll_column: int = 0
    _kill_ring: KillRing = field(default_factory=KillRing)
    _last_action: Literal["kill", "yank", "type-word"] | None = None

    def __post_init__(self) -> None:
        self._selection_controller = SelectionController(
            length=lambda: len(self._buffer),
            cursor=lambda: self._buffer.cursor,
            set_cursor=self._buffer.move_cursor_to,
        )

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
        self._buffer.set_text(_single_line_text(text))
        self.clear_selection()
        self._scroll_column = 0
        self._last_action = None

    def clear(self) -> None:
        self._buffer.clear()
        self.clear_selection()
        self._scroll_column = 0
        self._last_action = None

    def has_selection(self) -> bool:
        return self._selection_controller.has_selection()

    def set_selection(self, anchor: int, focus: int) -> None:
        self._selection_controller.set(anchor, focus)

    def clear_selection(self) -> None:
        self._selection_controller.clear()

    def editor_input_target(self) -> object:
        return _TextInputEditorTarget(self)

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
            self.move_to_start()
            return True
        if manager.matches(key, "tui.editor.cursorLineEnd"):
            self.move_to_end()
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
            return self.kill_to_start()
        if manager.matches(key, "tui.editor.deleteToLineEnd"):
            return self.kill_to_end()
        return False

    def insert_text(self, text: str) -> None:
        text = _single_line_text(text)
        selection = self.selected_range
        if selection is not None:
            self._buffer.replace_range(selection[0], selection[1], text, record=False)
            self.clear_selection()
            return
        self._buffer.insert_text(text, record=False)

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

    def move_to_start(self) -> None:
        self._buffer.move_to_start()
        self._after_cursor_move()

    def move_to_end(self) -> None:
        self._buffer.move_to_end()
        self._after_cursor_move()

    def move_word_left(self) -> None:
        self._buffer.move_word_left()
        self._after_cursor_move()

    def move_word_right(self) -> None:
        self._buffer.move_word_right()
        self._after_cursor_move()

    def select_char_left(self) -> None:
        self._extend_selection_to(self._buffer.cursor - 1)

    def select_char_right(self) -> None:
        self._extend_selection_to(self._buffer.cursor + 1)

    def select_word_left(self) -> None:
        self._extend_selection_to(self._word_left_index())

    def select_word_right(self) -> None:
        self._extend_selection_to(self._word_right_index())

    def select_line_start(self) -> None:
        self._extend_selection_to(0)

    def select_line_end(self) -> None:
        self._extend_selection_to(len(self._buffer))

    def kill_to_start(self) -> bool:
        if self._kill_selection_or_none(prepend=True):
            return True
        if self._buffer.cursor <= 0:
            return False
        killed = self._buffer.text_before_cursor

        def edit() -> None:
            self._buffer.delete_range(0, self._buffer.cursor, record=False)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def kill_to_end(self) -> bool:
        if self._kill_selection_or_none(prepend=False):
            return True
        if self._buffer.cursor >= len(self._buffer):
            return False
        killed = self._buffer.text_after_cursor

        def edit() -> None:
            self._buffer.delete_range(self._buffer.cursor, len(self._buffer), record=False)
            self._push_kill(killed, prepend=False)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def delete_word_backward(self) -> bool:
        if self._kill_selection_or_none(prepend=True):
            return True
        start = self._word_left_index()
        cursor = self._buffer.cursor
        if start == cursor:
            return False
        killed = "".join(grapheme_clusters(self.value)[start:cursor])

        def edit() -> None:
            self._buffer.delete_range(start, cursor, record=False)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def delete_word_forward(self) -> bool:
        if self._kill_selection_or_none(prepend=False):
            return True
        end = self._word_right_index()
        cursor = self._buffer.cursor
        if end == cursor:
            return False
        killed = "".join(grapheme_clusters(self.value)[cursor:end])

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
        clusters = list(grapheme_clusters(self.value))
        if "".join(clusters[start : self._buffer.cursor]) != previous:
            return False

        def edit() -> None:
            self._buffer.delete_range(start, self._buffer.cursor, record=False)
            self._rotate_kill_ring()
            replacement = self._kill_ring.peek()
            if replacement is not None:
                self.insert_text(replacement)
            self._last_action = "yank"

        return self._apply_edit(edit)

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

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        prompt_width = visible_width(self.prompt)
        input_width = max(0, target_width - prompt_width)
        cursor_column_in_text = visible_width(self._buffer.text_before_cursor)
        if input_width <= 0:
            line = truncate_to_width(self.prompt, max_width=target_width, ellipsis="")
            return RenderResult(lines=(RenderLine(line),), cursor=CursorDeclaration(row=0, column=visible_width(line)))

        self._ensure_cursor_visible(cursor_column_in_text, width=input_width)
        if self.value:
            visible = slice_by_column(self.value, start=self._scroll_column, length=input_width).text
            selection = self._selection_display_range()
            if selection is not None:
                visible = highlight_selection_by_columns(
                    visible,
                    selection_range=(selection[0] - self._scroll_column, selection[1] - self._scroll_column),
                    selection_style=self._selection_style(),
                )
        else:
            visible = truncate_to_width(self.placeholder, max_width=input_width, ellipsis="")
        line = truncate_to_width(f"{self.prompt}{visible}", max_width=target_width, ellipsis="")
        cursor_column = prompt_width + max(0, cursor_column_in_text - self._scroll_column)
        cursor_column = min(cursor_column, visible_width(line))
        return RenderResult(lines=(RenderLine(line),), cursor=CursorDeclaration(row=0, column=cursor_column))

    def _ensure_cursor_visible(self, cursor_column_in_text: int, *, width: int) -> None:
        if cursor_column_in_text < self._scroll_column:
            self._scroll_column = cursor_column_in_text
        elif cursor_column_in_text > self._scroll_column + width:
            self._scroll_column = cursor_column_in_text - width

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

    def _word_left_index(self) -> int:
        return self._buffer.word_left_index()

    def _word_right_index(self) -> int:
        return self._buffer.word_right_index()

    def _extend_selection_to(self, target: int) -> None:
        self._selection_controller.extend_to(target)
        self._last_action = None

    def _after_cursor_move(self) -> None:
        self.clear_selection()
        self._last_action = None

    def _range_text(self, start: int, end: int) -> str:
        return "".join(grapheme_clusters(self.value)[start:end])

    def _selection_display_range(self) -> tuple[int, int] | None:
        selection = self.selected_range
        if selection is None:
            return None
        start, end = selection
        clusters = list(grapheme_clusters(self.value))
        display_start = visible_width("".join(clusters[:start]))
        display_end = visible_width("".join(clusters[:end]))
        if display_start == display_end:
            return None
        return display_start, display_end

    def _selection_style(self) -> ThemeStyle:
        if self.theme is not None and self.selection_theme_token:
            resolved = self.theme.resolve(self.selection_theme_token)
            if resolved:
                return resolved
        return DEFAULT_SELECTION_STYLE


@dataclass(frozen=True, slots=True)
class _TextInputEditorTarget:
    field: TextInput

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
        self.field.move_to_start()

    def move_to_line_end(self) -> None:
        self.field.move_to_end()

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
        self.field.kill_to_start()

    def kill_to_line_end(self) -> None:
        self.field.kill_to_end()

    def yank(self) -> None:
        self.field.yank()

    def yank_pop(self) -> None:
        self.field.yank_pop()

    def undo(self) -> None:
        self.field.undo()

    def redo(self) -> None:
        self.field.redo()


def _single_line_text(text: str) -> str:
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

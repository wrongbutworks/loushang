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
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager

__all__ = ["TextInput"]


@dataclass(slots=True)
class TextInput:
    prompt: str = ""
    placeholder: str = ""
    on_submit: Callable[[str], object] | None = None
    on_escape: Callable[[], object] | None = None
    on_change: Callable[[str], object] | None = None
    focused: bool = False
    _text: str = ""
    _cursor: int = 0
    _scroll_column: int = 0
    _undo_stack: list[tuple[str, int]] = field(default_factory=list)
    _redo_stack: list[tuple[str, int]] = field(default_factory=list)
    _kill_ring: list[str] = field(default_factory=list)
    _last_action: Literal["kill", "yank", "type-word"] | None = None

    @property
    def value(self) -> str:
        return self._text

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def set_text(self, text: str) -> None:
        self._text = _single_line_text(text)
        self._cursor = len(grapheme_clusters(self._text))
        self._scroll_column = 0
        self._redo_stack.clear()
        self._last_action = None

    def clear(self) -> None:
        self._text = ""
        self._cursor = 0
        self._scroll_column = 0
        self._redo_stack.clear()
        self._last_action = None

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
        if manager.matches(key, "tui.editor.yank"):
            return self.yank()
        if manager.matches(key, "tui.editor.yankPop"):
            return self.yank_pop()
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
        inserted = list(grapheme_clusters(_single_line_text(text)))
        if not inserted:
            return
        clusters = list(grapheme_clusters(self._text))
        clusters[self._cursor : self._cursor] = inserted
        self._text = "".join(clusters)
        self._cursor += len(inserted)

    def delete_backward(self) -> None:
        if self._cursor <= 0:
            return
        clusters = list(grapheme_clusters(self._text))
        del clusters[self._cursor - 1]
        self._cursor -= 1
        self._text = "".join(clusters)

    def delete_forward(self) -> None:
        clusters = list(grapheme_clusters(self._text))
        if self._cursor >= len(clusters):
            return
        del clusters[self._cursor]
        self._text = "".join(clusters)

    def move_left(self) -> None:
        self._cursor = max(0, self._cursor - 1)

    def move_right(self) -> None:
        self._cursor = min(len(grapheme_clusters(self._text)), self._cursor + 1)

    def move_to_start(self) -> None:
        self._cursor = 0

    def move_to_end(self) -> None:
        self._cursor = len(grapheme_clusters(self._text))

    def move_word_left(self) -> None:
        self._cursor = self._word_left_index()

    def move_word_right(self) -> None:
        self._cursor = self._word_right_index()

    def kill_to_start(self) -> bool:
        if self._cursor <= 0:
            return False

        def edit() -> None:
            clusters = list(grapheme_clusters(self._text))
            killed = "".join(clusters[: self._cursor])
            del clusters[: self._cursor]
            self._cursor = 0
            self._text = "".join(clusters)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def kill_to_end(self) -> bool:
        clusters = list(grapheme_clusters(self._text))
        if self._cursor >= len(clusters):
            return False

        def edit() -> None:
            current_clusters = list(grapheme_clusters(self._text))
            killed = "".join(current_clusters[self._cursor :])
            del current_clusters[self._cursor :]
            self._text = "".join(current_clusters)
            self._push_kill(killed, prepend=False)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def delete_word_backward(self) -> bool:
        start = self._word_left_index()
        if start == self._cursor:
            return False

        def edit() -> None:
            clusters = list(grapheme_clusters(self._text))
            killed = "".join(clusters[start : self._cursor])
            del clusters[start : self._cursor]
            self._cursor = start
            self._text = "".join(clusters)
            self._push_kill(killed, prepend=True)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def delete_word_forward(self) -> bool:
        end = self._word_right_index()
        if end == self._cursor:
            return False

        def edit() -> None:
            clusters = list(grapheme_clusters(self._text))
            killed = "".join(clusters[self._cursor : end])
            del clusters[self._cursor : end]
            self._text = "".join(clusters)
            self._push_kill(killed, prepend=False)
            self._last_action = "kill"

        return self._apply_edit(edit)

    def yank(self) -> bool:
        if not self._kill_ring:
            return False
        changed = self._apply_edit(lambda: self.insert_text(self._kill_ring[-1]))
        if changed:
            self._last_action = "yank"
        return changed

    def yank_pop(self) -> bool:
        if self._last_action != "yank" or len(self._kill_ring) <= 1:
            return False
        previous = self._kill_ring[-1]
        previous_clusters = list(grapheme_clusters(previous))
        start = self._cursor - len(previous_clusters)
        if start < 0:
            return False
        clusters = list(grapheme_clusters(self._text))
        if "".join(clusters[start : self._cursor]) != previous:
            return False

        def edit() -> None:
            current_clusters = list(grapheme_clusters(self._text))
            del current_clusters[start : self._cursor]
            self._cursor = start
            self._text = "".join(current_clusters)
            self._rotate_kill_ring()
            self.insert_text(self._kill_ring[-1])
            self._last_action = "yank"

        return self._apply_edit(edit)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        before = self.value
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self._last_action = None
        self._notify_change_if_needed(before)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        before = self.value
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self._last_action = None
        self._notify_change_if_needed(before)
        return True

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        prompt_width = visible_width(self.prompt)
        input_width = max(0, target_width - prompt_width)
        clusters = grapheme_clusters(self._text)
        cursor_column_in_text = visible_width("".join(clusters[: self._cursor]))
        if input_width <= 0:
            line = truncate_to_width(self.prompt, max_width=target_width, ellipsis="")
            return RenderResult(lines=(RenderLine(line),), cursor=CursorDeclaration(row=0, column=visible_width(line)))

        self._ensure_cursor_visible(cursor_column_in_text, width=input_width)
        if self._text:
            visible = slice_by_column(self._text, start=self._scroll_column, length=input_width).text
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

    def _snapshot(self) -> tuple[str, int]:
        return self._text, self._cursor

    def _restore(self, snapshot: tuple[str, int]) -> None:
        self._text, self._cursor = snapshot
        self._cursor = min(self._cursor, len(grapheme_clusters(self._text)))

    def _apply_edit(self, edit: Callable[[], None]) -> bool:
        snapshot = self._snapshot()
        before = self.value
        edit()
        if self._snapshot() == snapshot:
            return False
        self._undo_stack.append(snapshot)
        del self._undo_stack[:-100]
        self._redo_stack.clear()
        self._notify_change_if_needed(before)
        return True

    def _notify_change_if_needed(self, before: str) -> None:
        if self.value != before and self.on_change is not None:
            self.on_change(self.value)

    def _push_kill(self, text: str, *, prepend: bool) -> None:
        if not text:
            return
        if self._last_action == "kill" and self._kill_ring:
            if prepend:
                self._kill_ring[-1] = f"{text}{self._kill_ring[-1]}"
            else:
                self._kill_ring[-1] = f"{self._kill_ring[-1]}{text}"
            return
        self._kill_ring.append(text)
        del self._kill_ring[:-20]

    def _rotate_kill_ring(self) -> None:
        if len(self._kill_ring) <= 1:
            return
        self._kill_ring.insert(0, self._kill_ring.pop())

    def _word_left_index(self) -> int:
        clusters = list(grapheme_clusters(self._text))
        index = self._cursor
        while index > 0 and _text_input_cluster_kind(clusters[index - 1]) == "space":
            index -= 1
        if index == 0:
            return index
        kind = _text_input_cluster_kind(clusters[index - 1])
        while index > 0 and _text_input_cluster_kind(clusters[index - 1]) == kind:
            index -= 1
        return index

    def _word_right_index(self) -> int:
        clusters = list(grapheme_clusters(self._text))
        index = self._cursor
        while index < len(clusters) and _text_input_cluster_kind(clusters[index]) == "space":
            index += 1
        if index >= len(clusters):
            return index
        kind = _text_input_cluster_kind(clusters[index])
        while index < len(clusters) and _text_input_cluster_kind(clusters[index]) == kind:
            index += 1
        return index


def _single_line_text(text: str) -> str:
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _text_input_cluster_kind(cluster: str) -> str:
    if cluster.isspace():
        return "space"
    if cluster.isalnum() or cluster == "_":
        return "word"
    return "punctuation"

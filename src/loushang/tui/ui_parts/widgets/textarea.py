from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
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

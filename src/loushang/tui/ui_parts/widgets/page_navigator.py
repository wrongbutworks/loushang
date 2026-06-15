from __future__ import annotations

from dataclasses import dataclass, field

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import style_text

__all__ = ["PageNavigation", "PageNavigationError", "PageNavigator"]


@dataclass(frozen=True, slots=True)
class PageNavigation:
    page: int
    previous_page: int
    raw_value: str


@dataclass(frozen=True, slots=True)
class PageNavigationError:
    raw_value: str
    message: str = "Invalid page"


@dataclass(slots=True)
class PageNavigator:
    current_page: int = 1
    total_pages: int = 1
    label: str = "Go to page"
    detail_text: str = ""
    error: str = ""
    input_width: int | None = None
    theme: ThemeResolver | None = None
    focused: bool = False
    _input: TextInput = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.total_pages = max(1, self.total_pages)
        self.current_page = _clamp_page(self.current_page, self.total_pages)
        self._input = TextInput(theme=self.theme, focused=self.focused)
        self._input.set_text(str(self.current_page))
        if self.focused:
            self._input.focus()
            self._input.set_selection(0, len(self._input.value))

    @property
    def value(self) -> str:
        return self._input.value

    def focus(self) -> None:
        was_focused = self.focused
        self.focused = True
        self._input.focus()
        if not was_focused:
            self._sync_value_to_page()
        self._input.set_selection(0, len(self._input.value))

    def blur(self) -> None:
        self.focused = False
        self._input.blur()

    def set_page(self, page: int, *, total_pages: int | None = None) -> None:
        if total_pages is not None:
            self.total_pages = max(1, total_pages)
        self.current_page = _clamp_page(page, self.total_pages)
        if not self.focused:
            self._sync_value_to_page()

    def set_text(self, text: str) -> None:
        self._input.set_text(text)

    def editor_input_target(self) -> object | None:
        if not self.focused:
            return None
        return self._input.editor_input_target()

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = normalize_key_id(getattr(event, "key", ""))
            if key == "enter":
                return self._submit()
        return self._input.handle_input(event)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        field_width = self._input_width()
        input_result = self._input.render(RenderConstraints(width=field_width, max_height=1))
        input_text = input_result.lines[0].text if input_result.lines else ""
        input_text = _pad_visible(input_text, field_width)

        prefix = "> " if self.focused else "  "
        line = f"{prefix}{self.label}: [{input_text}] / {self.total_pages}"
        detail = self.error or self.detail_text
        if detail:
            line = f"{line}    {detail}"
        token = "widget.pageNavigator.error" if self.error else "widget.pageNavigator"
        rendered = truncate_to_width(line, max_width=target_width, ellipsis="")

        cursor = None
        if self.focused and input_result.cursor is not None:
            cursor_column = visible_width(f"{prefix}{self.label}: [") + input_result.cursor.column
            if cursor_column <= visible_width(rendered):
                cursor = CursorDeclaration(row=0, column=cursor_column)

        return RenderResult.from_lines(
            (RenderLine(style_text(rendered, self.theme, token)),),
            constraints=constraints,
            cursor=cursor,
        )

    def _submit(self) -> PageNavigation | PageNavigationError:
        raw_value = self.value.strip()
        try:
            requested = int(raw_value)
        except ValueError:
            self.error = "Invalid page"
            return PageNavigationError(raw_value=raw_value, message=self.error)

        previous = self.current_page
        page = _clamp_page(requested, self.total_pages)
        self.current_page = page
        self.error = ""
        self._sync_value_to_page()
        return PageNavigation(page=page, previous_page=previous, raw_value=raw_value)

    def _sync_value_to_page(self) -> None:
        value = str(self.current_page)
        if self._input.value != value:
            self._input.set_text(value)

    def _input_width(self) -> int:
        if self.input_width is not None:
            return max(1, self.input_width)
        return max(4, len(str(self.total_pages)) + 1)


def _clamp_page(page: int, total_pages: int) -> int:
    return max(1, min(max(1, total_pages), page))


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(text))}"

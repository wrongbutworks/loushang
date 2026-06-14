from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from loushang.tui.cell_width import truncate_to_width
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.keybindings import normalize_key_id

PageScaffoldFocusRegion = Literal["header", "body"]


@dataclass(frozen=True, slots=True)
class PageScaffoldContext:
    focus_region: PageScaffoldFocusRegion
    header_focused: bool
    body_focused: bool


PageScaffoldFooter = str | Callable[[PageScaffoldContext], str]


@dataclass(slots=True)
class PageScaffold:
    body: object
    header: object | None = None
    footer: PageScaffoldFooter = ""
    focused: bool = False
    focus_region: PageScaffoldFocusRegion = "body"
    separator_after_header: bool = False
    reserve_footer: bool = True

    def focus(self) -> None:
        self.focused = True
        if self.focus_region == "header" and self.focus_header():
            return
        if self.focus_body():
            return
        self.focus_header()

    def blur(self) -> None:
        self.focused = False
        _call(self.header, "blur")
        _call(self.body, "blur")

    def focus_header(self) -> bool:
        if self.header is None or not _has_method(self.header, "focus"):
            return False
        _call(self.body, "blur")
        _call(self.header, "focus")
        self.focused = True
        self.focus_region = "header"
        return True

    def focus_body(self) -> bool:
        if not _has_method(self.body, "focus"):
            return False
        _call(self.header, "blur")
        _call(self.body, "focus")
        self.focused = True
        self.focus_region = "body"
        return True

    def editor_input_target(self) -> object | None:
        if not self.focused:
            return None
        target = self.header if self.focus_region == "header" else self.body
        method = getattr(target, "editor_input_target", None)
        return method() if callable(method) else None

    def handle_input(self, event: object) -> object:
        if not self.focused:
            return None
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if self.focus_region == "header":
            if key in {"down", "enter"}:
                return True if self.focus_body() else False
            return _handle(self.header, event)
        result = _handle(self.body, event)
        if result is not None:
            return result
        if key in {"up", "shift+tab"}:
            return True if self.focus_header() else False
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        page_height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        footer_text = self._footer_text(width)
        rows: list[RenderLine] = []

        header_result = _render_part(
            self.header,
            RenderConstraints(
                width=width,
                max_height=page_height,
                visible_height=constraints.visible_height,
            ),
            missing_render_lines=0,
        )
        header_lines = list(header_result.lines)
        header_line_count = min(len(header_lines), page_height)
        if header_lines:
            rows.extend(header_lines[:page_height])
        if self.separator_after_header and header_lines and len(rows) < page_height:
            rows.append(RenderLine("-" * max(1, width)))

        remaining_after_chrome = page_height - len(rows)
        footer_reserved = 1 if self.reserve_footer and footer_text and remaining_after_chrome >= 2 else 0
        body_budget = max(0, page_height - len(rows) - footer_reserved)
        if body_budget <= 0 and not rows:
            body_budget = page_height

        body_start = len(rows)
        body_line_count = 0
        if body_budget > 0 and len(rows) < page_height:
            body_result = _render_part(
                self.body,
                RenderConstraints(
                    width=width,
                    max_height=body_budget,
                    visible_height=constraints.visible_height,
                ),
                missing_render_lines=1,
            )
            body_lines = list(body_result.lines[:body_budget])
            body_line_count = len(body_lines)
            rows.extend(body_lines)
        else:
            body_result = RenderResult.from_lines([], constraints=constraints)

        if footer_text and len(rows) < page_height:
            if self.reserve_footer:
                while len(rows) < page_height - 1:
                    rows.append(RenderLine(""))
            if len(rows) < page_height:
                rows.append(RenderLine(footer_text))

        cursor = self._offset_cursor(
            header_result.cursor,
            body_result.cursor,
            body_start,
            header_line_count,
            body_line_count,
            len(rows),
        )
        return RenderResult.from_lines(rows[:page_height], constraints=constraints, cursor=cursor)

    def _context(self) -> PageScaffoldContext:
        return PageScaffoldContext(
            focus_region=self.focus_region,
            header_focused=self.focused and self.focus_region == "header",
            body_focused=self.focused and self.focus_region == "body",
        )

    def _footer_text(self, width: int) -> str:
        value = self.footer(self._context()) if callable(self.footer) else self.footer
        return truncate_to_width(str(value), max_width=width, ellipsis="") if value else ""

    def _offset_cursor(
        self,
        header_cursor: CursorDeclaration | None,
        body_cursor: CursorDeclaration | None,
        body_start: int,
        header_line_count: int,
        body_line_count: int,
        row_count: int,
    ) -> CursorDeclaration | None:
        cursor = header_cursor if self.focus_region == "header" else body_cursor
        if cursor is not None:
            row = cursor.row if self.focus_region == "header" else body_start + cursor.row
            if row < 0 or row >= row_count:
                return None
            return CursorDeclaration(row=row, column=cursor.column)
        if not self.focused:
            return None
        if self.focus_region == "header" and header_line_count > 0:
            return CursorDeclaration(row=0, column=0)
        if self.focus_region == "body" and body_line_count > 0 and body_start < row_count:
            return CursorDeclaration(row=body_start, column=0)
        return None


def _render_part(
    part: object | None,
    constraints: RenderConstraints,
    *,
    missing_render_lines: int,
) -> RenderResult:
    render = getattr(part, "render", None)
    if callable(render):
        return render(constraints)
    line_count = min(max(0, missing_render_lines), max(0, constraints.max_height))
    return RenderResult.from_lines([RenderLine("") for _ in range(line_count)], constraints=constraints)


def _has_method(part: object | None, name: str) -> bool:
    return callable(getattr(part, name, None))


def _call(part: object | None, name: str) -> object:
    method = getattr(part, name, None)
    return method() if callable(method) else None


def _handle(part: object | None, event: object) -> object:
    method = getattr(part, "handle_input", None)
    return method(event) if callable(method) else None

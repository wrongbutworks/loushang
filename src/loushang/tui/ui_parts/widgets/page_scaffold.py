from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from loushang.tui.cell_width import truncate_to_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult

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

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        footer_text = self._footer_text(width)
        rows: list[RenderLine] = []

        header_result = _render_part(
            self.header,
            RenderConstraints(
                width=width,
                max_height=constraints.max_height,
                visible_height=constraints.visible_height,
            ),
            missing_render_lines=0,
        )
        header_lines = list(header_result.lines)
        if header_lines:
            rows.extend(header_lines[: constraints.max_height])
        if self.separator_after_header and header_lines and len(rows) < constraints.max_height:
            rows.append(RenderLine("-" * max(1, width)))

        remaining_after_chrome = constraints.max_height - len(rows)
        footer_reserved = 1 if self.reserve_footer and footer_text and remaining_after_chrome >= 2 else 0
        body_budget = max(0, constraints.max_height - len(rows) - footer_reserved)
        if body_budget <= 0 and not rows:
            body_budget = constraints.max_height

        body_start = len(rows)
        if body_budget > 0 and len(rows) < constraints.max_height:
            body_result = _render_part(
                self.body,
                RenderConstraints(
                    width=width,
                    max_height=body_budget,
                    visible_height=constraints.visible_height,
                ),
                missing_render_lines=1,
            )
            rows.extend(list(body_result.lines[:body_budget]))
        else:
            body_result = RenderResult.from_lines([], constraints=constraints)

        if footer_text and len(rows) < constraints.max_height:
            if self.reserve_footer:
                while len(rows) < constraints.max_height - 1:
                    rows.append(RenderLine(""))
            if len(rows) < constraints.max_height:
                rows.append(RenderLine(footer_text))

        cursor = self._offset_cursor(
            header_result.cursor,
            body_result.cursor,
            body_start,
            len(rows),
        )
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

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
        row_count: int,
    ) -> CursorDeclaration | None:
        cursor = header_cursor if self.focus_region == "header" else body_cursor
        if cursor is None:
            return None
        row = cursor.row if self.focus_region == "header" else body_start + cursor.row
        if row < 0 or row >= row_count:
            return None
        return CursorDeclaration(row=row, column=cursor.column)


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

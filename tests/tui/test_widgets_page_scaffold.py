from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
    strip_control_sequences,
)
from loushang.tui.ui_parts.widgets.page_scaffold import PageScaffold


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


@dataclass(slots=True)
class StaticPart:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines(
            [RenderLine(line[: constraints.width]) for line in self.lines[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class CursorPart(StaticPart):
    cursor: CursorDeclaration | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        result = StaticPart.render(self, constraints)
        return RenderResult.from_lines(result.lines, constraints=constraints, cursor=self.cursor)


def test_page_scaffold_renders_body_only_page() -> None:
    scaffold = PageScaffold(body=StaticPart(("body",)))

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_ignores_non_renderable_optional_header() -> None:
    scaffold = PageScaffold(
        header=object(),
        body=StaticPart(("body",)),
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_renders_blank_line_for_non_renderable_body() -> None:
    scaffold = PageScaffold(body=object())

    assert plain_lines(scaffold, width=20, height=3) == ("",)


def test_page_scaffold_renders_header_separator_body_padding_and_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=12, height=5) == (
        "header",
        "------------",
        "body",
        "",
        "footer",
    )


def test_page_scaffold_reserves_footer_height_under_long_body_content() -> None:
    scaffold = PageScaffold(
        body=StaticPart(tuple(f"row {index}" for index in range(10))),
        footer="footer",
    )

    lines = plain_lines(scaffold, width=20, height=4)

    assert lines[-1] == "footer"
    assert "row 0" in lines
    assert "row 9" not in lines


def test_page_scaffold_tiny_heights_prioritize_header_body_then_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
    )

    assert plain_lines(scaffold, width=20, height=1) == ("header",)
    assert plain_lines(scaffold, width=20, height=2) == ("header", "body")


def test_page_scaffold_offsets_body_cursor_after_header_and_separator() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        footer="footer",
        focused=True,
        focus_region="body",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=5))

    assert result.cursor == CursorDeclaration(row=2, column=2)


def test_page_scaffold_uses_header_cursor_without_body_offset() -> None:
    scaffold = PageScaffold(
        header=CursorPart(("header",), CursorDeclaration(row=0, column=1)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        focused=True,
        focus_region="header",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=4))

    assert result.cursor == CursorDeclaration(row=0, column=1)

from __future__ import annotations

import pytest

from loushang.tui import (
    CURSOR_MARKER,
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)


def test_render_constraints_validate_positive_width_and_height() -> None:
    RenderConstraints(width=80, max_height=24)

    with pytest.raises(ValueError, match="width must be positive"):
        RenderConstraints(width=0, max_height=24)

    with pytest.raises(ValueError, match="max_height must be positive"):
        RenderConstraints(width=80, max_height=0)


def test_render_result_rejects_overflow_against_constraints() -> None:
    constraints = RenderConstraints(width=4, max_height=2)

    with pytest.raises(ValueError, match="line 1 exceeds width 4"):
        RenderResult.from_text("abcd\nabcde", constraints=constraints)

    with pytest.raises(ValueError, match="render result exceeds max height 2"):
        RenderResult.from_lines(
            [RenderLine("a"), RenderLine("b"), RenderLine("c")],
            constraints=constraints,
        )


def test_render_result_supports_explicit_cursor_declaration() -> None:
    result = RenderResult.from_lines(
        [RenderLine("abc")],
        constraints=RenderConstraints(width=10, max_height=1),
        cursor=CursorDeclaration(row=0, column=2),
    )

    assert result.cursor == CursorDeclaration(row=0, column=2)
    assert result.lines[0].text == "abc"


def test_render_result_extracts_cursor_marker_and_strips_it() -> None:
    result = RenderResult.from_text(
        f"ab{CURSOR_MARKER}c",
        constraints=RenderConstraints(width=10, max_height=1),
    )

    assert result.cursor == CursorDeclaration(row=0, column=2)
    assert result.lines == (RenderLine("abc"),)


def test_render_result_rejects_cursor_outside_rendered_lines() -> None:
    with pytest.raises(ValueError, match="cursor row out of range"):
        RenderResult.from_lines(
            [RenderLine("abc")],
            constraints=RenderConstraints(width=10, max_height=1),
            cursor=CursorDeclaration(row=1, column=0),
        )

    with pytest.raises(ValueError, match="cursor column out of range"):
        RenderResult.from_lines(
            [RenderLine("abc")],
            constraints=RenderConstraints(width=10, max_height=1),
            cursor=CursorDeclaration(row=0, column=4),
        )

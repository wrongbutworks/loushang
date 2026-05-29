from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.cell_width import visible_width

CURSOR_MARKER = "\x1b_loushang:cursor\x07"


@dataclass(frozen=True, slots=True)
class RenderConstraints:
    width: int
    max_height: int
    visible_height: int | None = None

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("width must be positive")
        if self.max_height <= 0:
            raise ValueError("max_height must be positive")
        if self.visible_height is not None and self.visible_height <= 0:
            raise ValueError("visible_height must be positive")


@dataclass(frozen=True, slots=True)
class CursorDeclaration:
    row: int
    column: int

    def __post_init__(self) -> None:
        if self.row < 0:
            raise ValueError("cursor row must be non-negative")
        if self.column < 0:
            raise ValueError("cursor column must be non-negative")


@dataclass(frozen=True, slots=True)
class RenderLine:
    text: str

    @property
    def width(self) -> int:
        return visible_width(self.text)


@dataclass(frozen=True, slots=True)
class RenderResult:
    lines: tuple[RenderLine, ...]
    cursor: CursorDeclaration | None = None

    @classmethod
    def from_text(cls, text: str, *, constraints: RenderConstraints) -> RenderResult:
        cursor: CursorDeclaration | None = None
        rendered_lines: list[RenderLine] = []
        for row, line in enumerate(text.split("\n")):
            if CURSOR_MARKER in line:
                before_marker, marker, after_marker = line.partition(CURSOR_MARKER)
                if marker and cursor is not None:
                    raise ValueError("render result contains multiple cursor markers")
                cursor = CursorDeclaration(row=row, column=visible_width(before_marker))
                line = before_marker + after_marker
            rendered_lines.append(RenderLine(line))
        return cls.from_lines(rendered_lines, constraints=constraints, cursor=cursor)

    @classmethod
    def from_lines(
        cls,
        lines: list[RenderLine] | tuple[RenderLine, ...],
        *,
        constraints: RenderConstraints,
        cursor: CursorDeclaration | None = None,
    ) -> RenderResult:
        rendered_lines: list[RenderLine] = []
        marker_cursor = cursor
        for row, line in enumerate(lines):
            text = line.text
            if CURSOR_MARKER in text:
                before_marker, marker, after_marker = text.partition(CURSOR_MARKER)
                if marker and marker_cursor is not None:
                    raise ValueError("render result contains multiple cursor markers")
                marker_cursor = CursorDeclaration(row=row, column=visible_width(before_marker))
                text = before_marker + after_marker
            rendered_lines.append(RenderLine(text))
        result = cls(lines=tuple(rendered_lines), cursor=marker_cursor)
        result.validate(constraints)
        return result

    def validate(self, constraints: RenderConstraints) -> None:
        if len(self.lines) > constraints.max_height:
            raise ValueError(f"render result exceeds max height {constraints.max_height}")

        for index, line in enumerate(self.lines):
            if line.width > constraints.width:
                raise ValueError(f"line {index} exceeds width {constraints.width}")

        if self.cursor is None:
            return
        if self.cursor.row >= len(self.lines):
            raise ValueError("cursor row out of range")
        if self.cursor.column > self.lines[self.cursor.row].width:
            raise ValueError("cursor column out of range")

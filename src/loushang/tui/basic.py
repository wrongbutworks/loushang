from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from loushang.tui.cell_width import (
    TAB_WIDTH,
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
    wrap_ansi,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import (
    ThemeResolver,
    ThemeStyle,
    apply_theme_style,
    theme_signature,
)

BackgroundFn = Callable[[str], str]


class RenderableLike(Protocol):
    def render(self, constraints: RenderConstraints) -> RenderResult: ...


@dataclass(slots=True)
class Text:
    text: str = ""
    padding_x: int = 1
    padding_y: int = 1
    background: BackgroundFn | None = None
    theme: ThemeResolver | None = None
    theme_token: str | None = None
    _cached_text: str | None = field(default=None, init=False, repr=False)
    _cached_width: int | None = field(default=None, init=False, repr=False)
    _cached_background_sample: str | None = field(default=None, init=False, repr=False)
    _cached_theme_signature: tuple[int, str, tuple[tuple[str, str], ...]] | None = field(
        default=None, init=False, repr=False
    )
    _cached_lines: tuple[str, ...] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.padding_x < 0:
            raise ValueError("padding_x must be non-negative")
        if self.padding_y < 0:
            raise ValueError("padding_y must be non-negative")

    def set_text(self, text: str) -> None:
        self.text = text
        self.invalidate()

    def set_background(self, background: BackgroundFn | None) -> None:
        self.background = background
        self.invalidate()

    def invalidate(self) -> None:
        self._cached_text = None
        self._cached_width = None
        self._cached_background_sample = None
        self._cached_theme_signature = None
        self._cached_lines = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        lines = self._render_lines(constraints.width)[: constraints.max_height]
        return RenderResult.from_lines([RenderLine(line) for line in lines], constraints=constraints)

    def _render_lines(self, width: int) -> tuple[str, ...]:
        background_sample = self.background("test") if self.background is not None else None
        style_signature = theme_signature(self.theme, self.theme_token)
        if (
            self._cached_lines is not None
            and self._cached_text == self.text
            and self._cached_width == width
            and self._cached_background_sample == background_sample
            and self._cached_theme_signature == style_signature
        ):
            return self._cached_lines

        lines = self._compute_lines(width)
        self._cached_text = self.text
        self._cached_width = width
        self._cached_background_sample = background_sample
        self._cached_theme_signature = style_signature
        self._cached_lines = lines
        return lines

    def _compute_lines(self, width: int) -> tuple[str, ...]:
        if not self.text or self.text.strip() == "":
            return ()

        normalized = self.text.replace("\t", " " * TAB_WIDTH)
        target_width = autowrap_safe_width(width)
        content_width = max(1, target_width - self.padding_x * 2)
        left = " " * self.padding_x
        right = " " * self.padding_x
        style = _resolve_style(self.theme, self.theme_token)
        content_lines: list[str] = []
        for wrapped in wrap_ansi(normalized, width=content_width):
            content_lines.append(_fit_line(left + wrapped + right, width=width, background=self.background, style=style))

        empty_line = _fit_line("", width=width, background=self.background, style=style)
        vertical_padding = [empty_line for _ in range(self.padding_y)]
        return tuple([*vertical_padding, *content_lines, *vertical_padding])


@dataclass(slots=True)
class Spacer:
    lines: int = 1

    def __post_init__(self) -> None:
        if self.lines < 0:
            raise ValueError("lines must be non-negative")

    def set_lines(self, lines: int) -> None:
        if lines < 0:
            raise ValueError("lines must be non-negative")
        self.lines = lines

    def invalidate(self) -> None:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        count = min(self.lines, constraints.max_height)
        return RenderResult.from_lines([RenderLine("") for _ in range(count)], constraints=constraints)


@dataclass(slots=True)
class TruncatedText:
    text: str
    padding_x: int = 0
    padding_y: int = 0
    ellipsis: str = "..."
    theme: ThemeResolver | None = None
    theme_token: str | None = None

    def __post_init__(self) -> None:
        if self.padding_x < 0:
            raise ValueError("padding_x must be non-negative")
        if self.padding_y < 0:
            raise ValueError("padding_y must be non-negative")

    def invalidate(self) -> None:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        target_width = autowrap_safe_width(width)
        available_width = max(1, target_width - self.padding_x * 2)
        first_line = self.text.split("\n", 1)[0]
        display = truncate_to_width(first_line, max_width=available_width, ellipsis=self.ellipsis)
        style = _resolve_style(self.theme, self.theme_token)
        line = _fit_line((" " * self.padding_x) + display + (" " * self.padding_x), width=width, style=style)
        empty_line = _fit_line("", width=width, style=style)
        lines = [*(empty_line for _ in range(self.padding_y)), line, *(empty_line for _ in range(self.padding_y))]
        lines = lines[: constraints.max_height]
        return RenderResult.from_lines([RenderLine(item) for item in lines], constraints=constraints)


@dataclass(slots=True)
class Box:
    padding_x: int = 1
    padding_y: int = 1
    background: BackgroundFn | None = None
    theme: ThemeResolver | None = None
    theme_token: str | None = None
    children: list[RenderableLike] = field(default_factory=list)
    _cached_width: int | None = field(default=None, init=False, repr=False)
    _cached_background_sample: str | None = field(default=None, init=False, repr=False)
    _cached_theme_signature: tuple[int, str, tuple[tuple[str, str], ...]] | None = field(
        default=None, init=False, repr=False
    )
    _cached_child_lines: tuple[str, ...] | None = field(default=None, init=False, repr=False)
    _cached_lines: tuple[str, ...] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.padding_x < 0:
            raise ValueError("padding_x must be non-negative")
        if self.padding_y < 0:
            raise ValueError("padding_y must be non-negative")

    def add_child(self, child: RenderableLike) -> None:
        self.children.append(child)
        self.invalidate()

    def remove_child(self, child: RenderableLike) -> None:
        self.children.remove(child)
        self.invalidate()

    def clear(self) -> None:
        self.children.clear()
        self.invalidate()

    def set_background(self, background: BackgroundFn | None) -> None:
        self.background = background
        self.invalidate()

    def invalidate(self) -> None:
        self._cached_width = None
        self._cached_background_sample = None
        self._cached_theme_signature = None
        self._cached_child_lines = None
        self._cached_lines = None
        for child in self.children:
            invalidate = getattr(child, "invalidate", None)
            if callable(invalidate):
                invalidate()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        lines = self._render_lines(constraints.width, constraints.max_height)
        return RenderResult.from_lines([RenderLine(line) for line in lines], constraints=constraints)

    def _render_lines(self, width: int, max_height: int) -> tuple[str, ...]:
        child_lines = self._render_child_lines(width, max_height)
        if not child_lines:
            self._cached_width = width
            self._cached_child_lines = child_lines
            self._cached_lines = ()
            return ()

        background_sample = self.background("test") if self.background is not None else None
        style_signature = theme_signature(self.theme, self.theme_token)
        if (
            self._cached_lines is not None
            and self._cached_width == width
            and self._cached_background_sample == background_sample
            and self._cached_theme_signature == style_signature
            and self._cached_child_lines == child_lines
        ):
            return self._cached_lines[:max_height]

        style = _resolve_style(self.theme, self.theme_token)
        empty_line = _fit_line("", width=width, background=self.background, style=style)
        vertical_padding = [empty_line for _ in range(self.padding_y)]
        content_lines = [
            _fit_line((" " * self.padding_x) + line, width=width, background=self.background, style=style)
            for line in child_lines
        ]
        lines = tuple([*vertical_padding, *content_lines, *vertical_padding])
        self._cached_width = width
        self._cached_background_sample = background_sample
        self._cached_theme_signature = style_signature
        self._cached_child_lines = child_lines
        self._cached_lines = lines
        return lines[:max_height]

    def _render_child_lines(self, width: int, max_height: int) -> tuple[str, ...]:
        if not self.children:
            return ()
        content_width = max(1, autowrap_safe_width(width) - self.padding_x * 2)
        budget = max(0, max_height - self.padding_y * 2)
        rendered: list[str] = []
        for child in self.children:
            if budget <= 0:
                break
            result = child.render(RenderConstraints(width=content_width, max_height=budget))
            for line in result.lines:
                rendered.append(line.text)
                budget -= 1
                if budget <= 0:
                    break
        return tuple(rendered)


def _fit_line(
    text: str,
    *,
    width: int,
    background: BackgroundFn | None = None,
    style: ThemeStyle | None = None,
) -> str:
    fill_width = _fills_width(background=background, style=style)
    target_width = autowrap_safe_width(width)
    line = truncate_to_width(text, max_width=target_width, ellipsis="")
    if not fill_width:
        return apply_theme_style(line, style)
    padding = " " * max(0, target_width - visible_width(line))
    padded = f"{line}{padding}"
    if background is None:
        return apply_theme_style(padded, style)
    styled = background(padded)
    if style is not None:
        styled = apply_theme_style(styled, style)
    if visible_width(styled) <= target_width:
        return styled
    return truncate_to_width(styled, max_width=target_width, ellipsis="")


def _resolve_style(theme: ThemeResolver | None, token: str | None) -> ThemeStyle | None:
    if theme is None or not token:
        return None
    return theme.resolve(token)


def _fills_width(*, background: BackgroundFn | None, style: ThemeStyle | None) -> bool:
    if background is not None:
        return True
    if not style:
        return False
    return style.get("background") is not None or style.get("bg") is not None

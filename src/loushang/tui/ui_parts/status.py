from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult

from .layout import RegionRenderable


@dataclass(frozen=True, slots=True)
class StatusField:
    text: str
    priority: int = 0


@dataclass(slots=True)
class StatusBar:
    fields: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        ordered = sorted(self.fields, key=lambda status_field: status_field.priority, reverse=True)
        selected: list[StatusField] = []
        for status_field in ordered:
            candidate = selected + [status_field]
            text = _join_status(candidate)
            if visible_width(text) <= target_width:
                selected = candidate
        text = _join_status(selected)
        if not text and ordered:
            text = ordered[0].text
        line = truncate_to_width(text, max_width=target_width)
        return RenderResult.from_lines([RenderLine(line)], constraints=constraints)


@dataclass(frozen=True, slots=True)
class FooterField:
    text: str
    side: Literal["left", "right"] = "left"
    priority: int = 0


@dataclass(slots=True)
class FooterStatusLine:
    fields: list[FooterField] | tuple[FooterField, ...] = field(default_factory=list)
    separator: str = " | "
    min_gap: int = 2

    def __post_init__(self) -> None:
        if self.min_gap < 1:
            raise ValueError("min_gap must be positive")

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        selected: list[FooterField] = []
        for footer_field in sorted(self.fields, key=lambda field: field.priority, reverse=True):
            candidate = [*selected, footer_field]
            if _footer_fields_fit(candidate, width=target_width, separator=self.separator, min_gap=self.min_gap):
                selected = candidate
        if not selected and self.fields:
            selected = [max(self.fields, key=lambda field: field.priority)]
        line = _render_footer_fields(selected, width=target_width, separator=self.separator)
        return RenderResult.from_lines([RenderLine(line)], constraints=constraints)


@dataclass(slots=True)
class FooterView:
    primary: RegionRenderable | str | None = None
    secondary: RegionRenderable | str | None = None
    extension_statuses: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rendered: list[str] = []
        for part in (self.primary, self.secondary):
            if part is None or len(rendered) >= constraints.max_height:
                continue
            rendered.extend(
                _render_footer_part(
                    part,
                    RenderConstraints(
                        width=constraints.width,
                        max_height=constraints.max_height - len(rendered),
                        visible_height=constraints.visible_height,
                    ),
                )
            )
        if self.extension_statuses and len(rendered) < constraints.max_height:
            rendered.extend(
                _render_extension_statuses(
                    self.extension_statuses,
                    RenderConstraints(
                        width=constraints.width,
                        max_height=constraints.max_height - len(rendered),
                        visible_height=constraints.visible_height,
                    ),
                )
            )
        return RenderResult.from_lines(
            [RenderLine(line) for line in rendered[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class WorkingLine:
    label: str
    elapsed_seconds: float

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        prefix = f"- {self.label} {_format_elapsed(self.elapsed_seconds)} "
        filler_width = max(0, target_width - visible_width(prefix))
        line = truncate_to_width(prefix + ("-" * filler_width), max_width=target_width)
        return RenderResult.from_lines([RenderLine(line)], constraints=constraints)


def _join_status(fields: list[StatusField]) -> str:
    return " | ".join(field.text for field in fields)


def _footer_fields_fit(fields: list[FooterField], *, width: int, separator: str, min_gap: int) -> bool:
    left = _join_footer_fields(fields, side="left", separator=separator)
    right = _join_footer_fields(fields, side="right", separator=separator)
    if left and right:
        return visible_width(left) + min_gap + visible_width(right) <= width
    return visible_width(left or right) <= width


def _render_footer_fields(fields: list[FooterField], *, width: int, separator: str) -> str:
    left = _join_footer_fields(fields, side="left", separator=separator)
    right = _join_footer_fields(fields, side="right", separator=separator)
    if left and right:
        left_width = visible_width(left)
        right_width = visible_width(right)
        if left_width + right_width >= width:
            return truncate_to_width(f"{left}  {right}", max_width=width)
        return f"{left}{' ' * (width - left_width - right_width)}{right}"
    if right:
        padding = max(0, width - visible_width(right))
        return (" " * padding) + truncate_to_width(right, max_width=width)
    return truncate_to_width(left, max_width=width)


def _join_footer_fields(fields: list[FooterField], *, side: Literal["left", "right"], separator: str) -> str:
    selected = [field for field in fields if field.side == side]
    selected.sort(key=lambda field: field.priority, reverse=True)
    return separator.join(_sanitize_footer_text(field.text) for field in selected if _sanitize_footer_text(field.text))


def _render_footer_part(part: RegionRenderable | str, constraints: RenderConstraints) -> list[str]:
    target_width = autowrap_safe_width(constraints.width)
    if isinstance(part, str):
        text = _sanitize_footer_text(part)
        if not text:
            return []
        return [truncate_to_width(text, max_width=target_width)]
    result = part.render(constraints)
    return [truncate_to_width(line.text, max_width=target_width) for line in result.lines]


def _render_extension_statuses(
    statuses: list[StatusField] | tuple[StatusField, ...],
    constraints: RenderConstraints,
) -> list[str]:
    sanitized = [
        StatusField(_sanitize_footer_text(status.text), priority=status.priority)
        for status in statuses
        if _sanitize_footer_text(status.text)
    ]
    if not sanitized:
        return []
    return [line.text for line in StatusBar(sanitized).render(constraints).lines]


def _sanitize_footer_text(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining = seconds - (minutes * 60)
    return f"{minutes}m {remaining:05.2f}s"


__all__ = [
    "FooterField",
    "FooterStatusLine",
    "FooterView",
    "StatusBar",
    "StatusField",
    "WorkingLine",
]

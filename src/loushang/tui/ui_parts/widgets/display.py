from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text

BadgeKind = Literal["default", "info", "success", "warning", "danger"]
StatusKind = Literal["neutral", "info", "success", "warning", "danger"]


@dataclass(slots=True)
class Badge:
    label: str
    kind: BadgeKind = "default"
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        rendered = truncate_to_width(f"[{self.label}]", max_width=target_width, ellipsis="")
        rendered = style_text(rendered, self.theme, f"widget.badge.{self.kind}")
        return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)


@dataclass(slots=True)
class StatusPill:
    label: str
    status: StatusKind = "neutral"
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        rendered = truncate_to_width(f"({self.label})", max_width=target_width, ellipsis="")
        rendered = style_text(rendered, self.theme, f"widget.status.{self.status}")
        return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)


@dataclass(slots=True)
class ProgressBar:
    value: float
    total: float = 100
    label: str = ""
    width: int | None = None
    show_percent: bool = True
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        line = _progress_line(self, target_width)
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)


@dataclass(frozen=True, slots=True)
class KeyValueItem:
    key: str
    value: object
    description: str = ""


@dataclass(slots=True)
class KeyValueList:
    items: Sequence[KeyValueItem | tuple[str, object]]
    separator: str = ": "
    key_width: int | None = None
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        normalized = [_normalize_item(item) for item in self.items]
        key_width = _key_width(normalized, self.key_width, target_width)
        lines: list[RenderLine] = []
        for item in normalized:
            if len(lines) >= constraints.max_height:
                break
            lines.append(RenderLine(_key_value_line(item, key_width, self.separator, target_width, self.theme)))
        return RenderResult.from_lines(lines, constraints=constraints)


def _ratio(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, value / total))


def _percent_text(ratio: float) -> str:
    return f"{round(ratio * 100):.0f}%"


def _progress_line(progress: ProgressBar, target_width: int) -> str:
    ratio = _ratio(progress.value, progress.total)
    percent = _percent_text(ratio) if progress.show_percent else ""
    label = truncate_to_width(progress.label, max_width=target_width, ellipsis="").strip()
    prefix = f"{label} " if label else ""
    suffix = f" {percent}" if percent else ""
    available = max(1, target_width - visible_width(prefix) - visible_width(suffix) - 2)
    if progress.width is not None:
        available = max(1, min(progress.width, available))
    while prefix and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        label_width = max(0, visible_width(prefix) - 2)
        label = truncate_to_width(label.rstrip(), max_width=label_width, ellipsis="")
        prefix = f"{label} " if label else ""
    while suffix and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        suffix = ""
    while available > 1 and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        available -= 1
    filled = round(ratio * available)
    fill = "#" * filled
    track = "-" * max(0, available - filled)
    styled_fill = style_text(fill, progress.theme, "widget.progress.fill")
    styled_track = style_text(track, progress.theme, "widget.progress.track")
    bar = f"[{styled_fill}{styled_track}]"
    line = f"{prefix}{bar}{suffix}"
    if prefix or suffix:
        line = style_text(line, progress.theme, "widget.progress.label")
    return truncate_to_width(line, max_width=target_width, ellipsis="")


def _normalize_item(item: KeyValueItem | tuple[str, object]) -> KeyValueItem:
    if isinstance(item, KeyValueItem):
        return item
    key, value = item
    return KeyValueItem(str(key), value)


def _key_width(items: Sequence[KeyValueItem], configured: int | None, target_width: int) -> int:
    if configured is not None:
        return max(0, min(configured, target_width))
    if not items:
        return 0
    longest = max(visible_width(item.key) for item in items)
    return max(0, min(longest, max(1, target_width // 2)))


def _key_value_line(
    item: KeyValueItem,
    key_width: int,
    separator: str,
    target_width: int,
    theme: ThemeResolver | None,
) -> str:
    key = truncate_to_width(item.key, max_width=key_width, ellipsis="")
    key = key + (" " * max(0, key_width - visible_width(key)))
    rendered_key = style_text(key, theme, "widget.keyValue.key")
    prefix = f"{rendered_key}{separator}"
    remaining = max(0, target_width - visible_width(prefix))
    value_text = str(item.value)
    if item.description and remaining > visible_width(value_text) + 2:
        value_text = f"{value_text}  {item.description}"
    value = truncate_to_width(value_text, max_width=remaining, ellipsis="")
    rendered_value = style_text(value, theme, "widget.keyValue.value")
    return truncate_to_width(f"{prefix}{rendered_value}", max_width=target_width, ellipsis="")

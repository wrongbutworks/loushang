from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult


@dataclass(slots=True)
class PendingQueueView:
    items: list[str] | tuple[str, ...] = field(default_factory=list)
    header: str = "Queued follow-up inputs"
    sections: tuple[PendingSection, ...] = ()

    @property
    def has_content(self) -> bool:
        if self.sections:
            return any(section.items or section.show_when_empty for section in self.sections)
        return bool(self.items)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if self.sections:
            return self._render_sections(constraints)
        if not self.items:
            return RenderResult.from_lines([], constraints=constraints)
        item_budget = max(0, constraints.max_height - 1)
        visible_items = list(self.items)[-item_budget:] if item_budget else []
        raw_lines = [self.header, *(f"-> {item}" for item in visible_items)]
        target_width = autowrap_safe_width(constraints.width)
        lines = [RenderLine(truncate_to_width(line, max_width=target_width)) for line in raw_lines]
        return RenderResult.from_lines(lines, constraints=constraints)

    def _render_sections(self, constraints: RenderConstraints) -> RenderResult:
        raw_lines: list[str] = []
        for section in self.sections:
            if not section.items and not section.show_when_empty:
                continue
            if raw_lines:
                raw_lines.append("")
            label = _section_label(section)
            if section.hint and section.hint_placement == "header":
                label = f"{label} ({section.hint})"
            raw_lines.append(label)
            raw_lines.extend(f"  ↳ {item}" for item in section.items)
            if section.hint and section.hint_placement == "footer":
                raw_lines.append(f"    {section.hint}")
        target_width = autowrap_safe_width(constraints.width)
        lines = [RenderLine(truncate_to_width(line, max_width=target_width)) for line in raw_lines[: constraints.max_height]]
        return RenderResult.from_lines(lines, constraints=constraints)


@dataclass(frozen=True, slots=True)
class PendingSection:
    label: str
    items: tuple[str, ...] = ()
    hint: str | None = None
    hint_placement: Literal["header", "footer"] = "footer"
    marker: str = "•"
    show_when_empty: bool = False


def _section_label(section: PendingSection) -> str:
    if not section.marker:
        return section.label
    return f"{section.marker} {section.label}"


__all__ = [
    "PendingQueueView",
    "PendingSection",
]

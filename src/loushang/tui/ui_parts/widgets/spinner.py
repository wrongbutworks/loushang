from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text


@dataclass(slots=True)
class Spinner:
    label: str = ""
    frame: int = 0
    frames: Sequence[str] = ("|", "/", "-", "\\")
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        line = _spinner_line(self, target_width)
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)


def _spinner_line(spinner: Spinner, target_width: int) -> str:
    frame = spinner.frames[spinner.frame % len(spinner.frames)] if spinner.frames else ""
    if frame and spinner.label:
        line = f"{style_text(frame, spinner.theme, 'widget.spinner.frame')} {style_text(spinner.label, spinner.theme, 'widget.spinner.label')}"
    elif frame:
        line = style_text(frame, spinner.theme, "widget.spinner.frame")
    elif spinner.label:
        line = style_text(spinner.label, spinner.theme, "widget.spinner.label")
    else:
        line = ""
    return truncate_to_width(line, max_width=target_width, ellipsis="")

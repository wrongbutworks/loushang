from __future__ import annotations

from loushang.tui.cell_width import truncate_to_width, visible_width


def fixed_width(text: str, *, width: int) -> str:
    if width <= 0:
        return ""
    return truncate_to_width(text, max_width=width, pad=True)


__all__ = ["fixed_width", "visible_width"]

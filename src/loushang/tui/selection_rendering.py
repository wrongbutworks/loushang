from __future__ import annotations

from loushang.tui.cell_width import slice_by_column, visible_width
from loushang.tui.theme import ThemeStyle, apply_theme_style

__all__ = ["DEFAULT_SELECTION_STYLE", "highlight_selection_by_columns"]

DEFAULT_SELECTION_STYLE: ThemeStyle = {"reverse": True}


def highlight_selection_by_columns(
    text: str,
    *,
    selection_range: tuple[int, int] | None,
    selection_style: ThemeStyle | None = None,
) -> str:
    if selection_range is None:
        return text
    selection_start, selection_end = selection_range
    if selection_start >= selection_end:
        return text
    text_width = visible_width(text)
    overlap_start = max(0, min(selection_start, text_width))
    overlap_end = max(0, min(selection_end, text_width))
    if overlap_start >= overlap_end:
        return text
    selected_width = overlap_end - overlap_start
    after_start = overlap_start + selected_width
    before = slice_by_column(text, start=0, length=overlap_start).text
    selected = slice_by_column(text, start=overlap_start, length=selected_width).text
    after = slice_by_column(text, start=after_start, length=max(0, text_width - after_start)).text
    return before + apply_theme_style(selected, selection_style or DEFAULT_SELECTION_STYLE) + after

from __future__ import annotations

from typing import Any

from loushang.tui import (
    FilterApply,
    FilterBar,
    FilterBoundary,
    FilterField,
    FilterFocusChange,
    InputEvent,
    RenderConstraints,
    strip_control_sequences,
)
from loushang.tui.ui_parts import FilterBar as UiFilterBar
from loushang.tui.ui_parts.widgets import FilterBar as WidgetFilterBar


def plain_lines(part: Any, *, width: int = 80, height: int = 3) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def stock_filter_bar() -> FilterBar:
    return FilterBar(
        (
            FilterField("search", "Search", width=16),
            FilterField("sector", "Sector", width=8),
            FilterField("min_price", "Min price", width=8, row=1),
        ),
        row_details={0: "Matches 334/2,000"},
    )


def test_filter_bar_is_reexported_from_public_modules() -> None:
    assert FilterBar is UiFilterBar
    assert FilterBar is WidgetFilterBar


def test_filter_bar_renders_grouped_fields_and_row_detail() -> None:
    bar = stock_filter_bar()
    bar.set_value("search", "ai")

    assert plain_lines(bar, width=90) == (
        "  Search: [ai              ]  Sector: [        ]  Matches 334/2,000",
        "  Min price: [        ]",
    )


def test_filter_bar_focus_selects_field_and_submit_returns_values_without_live_apply() -> None:
    bar = stock_filter_bar()

    bar.focus("search")
    assert plain_lines(bar, width=90)[0].startswith("> Search:")
    assert bar.handle_input(InputEvent(kind="text", text="ai")) is True
    assert bar.values == {"search": "ai", "sector": "", "min_price": ""}

    result = bar.handle_input(InputEvent(kind="key", key="enter"))

    assert result == FilterApply(values={"search": "ai", "sector": "", "min_price": ""}, active_key="search")
    assert bar.active_key == "search"


def test_filter_bar_tab_moves_between_fields_and_reports_boundaries() -> None:
    bar = stock_filter_bar()
    bar.focus("search")

    assert bar.handle_input(InputEvent(kind="key", key="tab")) == FilterFocusChange(
        active_key="sector",
        previous_key="search",
    )
    assert bar.handle_input(InputEvent(kind="key", key="tab")) == FilterFocusChange(
        active_key="min_price",
        previous_key="sector",
    )
    assert bar.handle_input(InputEvent(kind="key", key="tab")) == FilterBoundary(
        direction="forward",
        active_key="min_price",
        values={"search": "", "sector": "", "min_price": ""},
    )
    assert bar.handle_input(InputEvent(kind="key", key="shift+tab")) == FilterFocusChange(
        active_key="sector",
        previous_key="min_price",
    )


def test_filter_bar_cursor_stays_within_truncated_render_line() -> None:
    bar = stock_filter_bar()
    bar.focus("sector")
    assert bar.handle_input(InputEvent(kind="text", text="industrial")) is True

    result = bar.render(RenderConstraints(width=42, max_height=2))

    assert result.cursor is None or result.cursor.column <= result.lines[result.cursor.row].width

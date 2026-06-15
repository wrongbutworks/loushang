from __future__ import annotations

from typing import Any

from loushang.tui import (
    ColumnChooser,
    ColumnChooserClose,
    ColumnChooserColumn,
    ColumnChooserMove,
    ColumnChooserSelect,
    ColumnChooserSort,
    ColumnChooserToggle,
    ColumnChooserWidthChange,
    InputEvent,
    RenderConstraints,
    strip_control_sequences,
)
from loushang.tui.ui_parts import ColumnChooser as UiColumnChooser
from loushang.tui.ui_parts.widgets import ColumnChooser as WidgetColumnChooser


def plain_lines(part: Any, *, width: int = 80, height: int = 5) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def market_columns() -> tuple[ColumnChooserColumn, ...]:
    return (
        ColumnChooserColumn("symbol", "Symbol", visible=True, width=8, fixed=True, sortable=True),
        ColumnChooserColumn("price", "Price", visible=True, width=10, sortable=True),
        ColumnChooserColumn("change_pct", "Change %", visible=False, width=9, sortable=False),
    )


def test_column_chooser_is_reexported_from_public_modules() -> None:
    assert ColumnChooser is UiColumnChooser
    assert ColumnChooser is WidgetColumnChooser


def test_column_chooser_renders_visibility_width_fixed_and_sortable_state() -> None:
    chooser = ColumnChooser(market_columns(), focused=True)

    assert plain_lines(chooser, width=80) == (
        "> [x] Symbol            width 8   fixed sort",
        "  [x] Price             width 10        sort",
        "  [ ] Change %          width 9",
    )


def test_column_chooser_navigation_select_and_close() -> None:
    chooser = ColumnChooser(market_columns(), focused=True)

    assert chooser.handle_input(InputEvent(kind="key", key="down")) is True
    assert chooser.active_key == "price"
    assert chooser.handle_input(InputEvent(kind="key", key="end")) is True
    assert chooser.active_key == "change_pct"
    assert chooser.handle_input(InputEvent(kind="key", key="enter")) == ColumnChooserSelect("change_pct")
    assert chooser.handle_input(InputEvent(kind="key", key="escape")) == ColumnChooserClose()


def test_column_chooser_returns_column_control_intents_without_mutating_columns() -> None:
    chooser = ColumnChooser(market_columns(), focused=True)

    assert chooser.handle_input(InputEvent(kind="key", key="space")) == ColumnChooserToggle("symbol")
    assert chooser.handle_input(InputEvent(kind="key", key="]")) == ColumnChooserWidthChange("symbol", 1)
    assert chooser.handle_input(InputEvent(kind="key", key="[")) == ColumnChooserWidthChange("symbol", -1)
    assert chooser.handle_input(InputEvent(kind="key", key="ctrl+down")) == ColumnChooserMove("symbol", "down")
    assert chooser.handle_input(InputEvent(kind="key", key="ctrl+up")) == ColumnChooserMove("symbol", "up")
    assert chooser.handle_input(InputEvent(kind="key", key="s")) == ColumnChooserSort("symbol")
    assert tuple(column.visible for column in chooser.columns) == (True, True, False)


def test_column_chooser_repairs_active_key_when_columns_are_replaced() -> None:
    chooser = ColumnChooser(market_columns(), active_key="price", focused=True)

    chooser.set_columns((ColumnChooserColumn("change", "Change", width=9, sortable=False),))

    assert chooser.active_key == "change"
    assert plain_lines(chooser, width=80) == ("> [x] Change            width 9",)


def test_column_chooser_cursor_stays_within_truncated_render_line() -> None:
    chooser = ColumnChooser(
        (ColumnChooserColumn("long", "A very long display column header", width=123, fixed=True, sortable=True),),
        focused=True,
    )

    result = chooser.render(RenderConstraints(width=24, max_height=1))

    assert result.cursor is None or result.cursor.column <= result.lines[result.cursor.row].width

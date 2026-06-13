from __future__ import annotations

from typing import Any

from loushang.tui import InputEvent, RenderConstraints, strip_control_sequences
from loushang.tui.ui_parts.widgets.searchable_list import (
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
)


def render_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def _items() -> tuple[SearchableListItem, ...]:
    return (
        SearchableListItem("model", "Model", "kimi-for-coding"),
        SearchableListItem("thinking-mode", "Thinking mode", "true"),
        SearchableListItem("permission-mode", "Default permission mode", "Default"),
        SearchableListItem("editor-mode", "Editor mode", "vim"),
        SearchableListItem("archive", "Archive", "disabled", disabled=True),
    )


def test_searchable_list_filters_key_and_label_case_insensitive_in_order() -> None:
    view = SearchableList(_items(), query="MODE")

    assert view.query == "MODE"
    assert [item.key for item in view.filtered_items] == [
        "model",
        "thinking-mode",
        "permission-mode",
        "editor-mode",
    ]

    view.set_query("permission")
    assert [item.key for item in view.filtered_items] == ["permission-mode"]


def test_searchable_list_search_down_enters_list_and_up_returns_to_search() -> None:
    view = SearchableList(_items(), focused=True)

    assert view.focus_region == "search"
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.focus_region == "list"
    assert view.active_key == "model"

    assert view.handle_input(InputEvent(kind="key", key="up")) is True
    assert view.focus_region == "search"


def test_searchable_list_activation_returns_structured_select() -> None:
    view = SearchableList(_items(), focused=True)

    assert view.handle_input(InputEvent(kind="key", key="enter")) == SearchableListSelect(
        key="model",
        label="Model",
        value="kimi-for-coding",
    )


def test_searchable_list_disabled_items_visible_but_not_active() -> None:
    view = SearchableList(_items(), query="archive", focused=True)

    assert [item.key for item in view.filtered_items] == ["archive"]
    assert view.active_item is None
    assert view.active_key == ""
    assert view.handle_input(InputEvent(kind="key", key="enter")) is None
    assert any("Archive" in line for line in plain_lines(view))


def test_searchable_list_empty_result_resets_scroll_and_overflow() -> None:
    view = SearchableList(_items(), query="missing", focused=True)

    assert view.filtered_items == ()
    assert view.active_item is None
    assert view.scroll_offset == 0
    assert view.more_above == 0
    assert view.more_below == 0
    assert "No matching items" in plain_lines(view, width=40, height=5)


def test_searchable_list_renders_bounded_viewport_and_overflow_counts() -> None:
    items = tuple(SearchableListItem(f"item-{index}", f"Item {index}") for index in range(20))
    view = SearchableList(items, focused=True)
    view.focus_list()

    lines = plain_lines(view, width=40, height=6)
    assert any("Item 0" in line for line in lines)
    assert not any("Item 19" in line for line in lines)
    assert view.more_above == 0
    assert view.more_below > 0

    for _ in range(8):
        view.handle_input(InputEvent(kind="key", key="down"))
    plain_lines(view, width=40, height=6)
    assert view.more_above > 0
    assert view.more_below > 0

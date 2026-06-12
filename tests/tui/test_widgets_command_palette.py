from __future__ import annotations

from typing import Any, get_args

from loushang.tui import (
    CommandPalette,
    CommandPaletteItem,
    InputEvent,
    RenderConstraints,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.compat import CompletionItem, CompletionProvider
from loushang.tui.input import InputIntentKind
from loushang.tui.ui_parts.widgets.command_palette import CommandPaletteView


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (
        str(getattr(intent, "kind", "")),
        str(getattr(intent, "text", "")),
        str(getattr(intent, "note", "")),
    )


def intent_tuples(intents: object) -> tuple[tuple[str, str, str], ...]:
    if isinstance(intents, tuple):
        return tuple(intent_tuple(intent) for intent in intents)
    return (intent_tuple(intents),)


def test_command_palette_item_disabled_defaults_to_false() -> None:
    assert CommandPaletteItem("deploy").disabled is False
    assert CommandPaletteItem("archive", disabled=True).disabled is True


def test_command_palette_intent_kinds_are_declared() -> None:
    kinds = get_args(InputIntentKind)

    assert "command_select" in kinds
    assert "command_cancel" in kinds


def test_existing_coding_palette_adapter_keeps_disabled_out_of_scope() -> None:
    from loushang.coding.ui.native_surfaces import _palette_items

    items = _palette_items(
        CommandPalette(
            (
                CommandPaletteItem(
                    value="archive",
                    label="Archive release",
                    description="unavailable",
                    disabled=True,
                ),
            )
        )
    )

    assert len(items) == 1
    assert items[0].selected_value == "archive"
    assert not hasattr(items[0], "disabled")


def _items() -> tuple[CommandPaletteItem, ...]:
    return (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("logs", "Open logs", "Show latest logs"),
        CommandPaletteItem("tests", "Run tests", "Execute test suite"),
        CommandPaletteItem("cache", "Clear cache", "Invalidate local cache"),
        CommandPaletteItem("worker", "Restart worker", "Restart background worker"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    )


def render_result(part: Any, *, width: int = 60, height: int = 10):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def test_command_palette_view_title_sources_and_private_snapshot() -> None:
    palette = CommandPalette(_items(), title="Actions")

    assert CommandPaletteView(palette).title == "Actions"
    assert CommandPaletteView(palette, title="").title == ""
    assert CommandPaletteView(_items()).title == "Command Palette"
    assert CommandPaletteView(_items(), title="Run").title == "Run"


def test_command_palette_view_query_is_internal_editor_backed() -> None:
    view = CommandPaletteView(_items(), query="dep")

    assert view.query == "dep"
    assert [item.value for item in view.filtered_items] == ["deploy"]

    view.set_query("log")
    assert view.query == "log"
    assert [item.value for item in view.filtered_items] == ["logs"]

    assert view.handle_input(InputEvent(kind="text", text="s")) is True
    assert view.query == "logs"
    assert [item.value for item in view.filtered_items] == ["logs"]


def test_command_palette_view_filters_value_label_and_description_case_insensitive_in_order() -> None:
    view = CommandPaletteView(_items())

    assert [item.value for item in view.filtered_items] == [
        "deploy",
        "logs",
        "tests",
        "cache",
        "worker",
        "archive",
    ]

    view.set_query("RUN")
    assert [item.value for item in view.filtered_items] == ["deploy", "tests"]

    view.set_query("restart")
    assert [item.value for item in view.filtered_items] == ["worker"]


def test_command_palette_from_completion_provider_preserves_existing_shape() -> None:
    palette = CommandPalette.from_completion_provider(
        CompletionProvider(
            (
                CompletionItem("/deploy", label="/deploy", description="Deploy app"),
            )
        ),
        title="Commands",
    )

    assert palette == CommandPalette(
        (CommandPaletteItem("/deploy", "/deploy", "Deploy app"),),
        title="Commands",
    )


def test_command_palette_view_disabled_items_render_but_navigation_skips_them() -> None:
    view = CommandPaletteView(_items())
    view.focus()

    view.set_query("archive")
    assert view.active_value == ""
    assert view.handle_input(InputEvent(kind="key", key="enter")) is None
    lines = plain_lines(view, width=60, height=10)
    assert not any(line.startswith("> Archive release") for line in lines)
    assert any("Archive release" in line for line in lines)


def test_command_palette_view_navigation_repairs_active_and_visible_window() -> None:
    view = CommandPaletteView(_items(), max_visible=2)
    view.focus()

    assert view.active_value == "deploy"
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.active_value == "tests"

    lines = plain_lines(view, width=60, height=8)
    assert any(line.startswith("> Run tests") for line in lines)
    assert sum(line.startswith("> ") for line in lines) == 1

    assert view.handle_input(InputEvent(kind="key", key="ctrl+end")) is True
    assert view.active_value == "worker"
    assert view.handle_input(InputEvent(kind="key", key="ctrl+home")) is True
    assert view.active_value == "deploy"


def test_command_palette_view_select_and_cancel_intents_with_close_flags() -> None:
    view = CommandPaletteView(_items())

    assert intent_tuples(view.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("command_select", "deploy", "Deploy service"),
        ("surface_close", "", ""),
    )

    stay_open = CommandPaletteView(_items(), close_on_select=False, close_on_cancel=False)
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("command_select", "deploy", "Deploy service"),
    )
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="escape"))) == (
        ("command_cancel", "", ""),
    )
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="esc"))) == (
        ("command_cancel", "", ""),
    )
    assert intent_tuples(view.handle_input(InputEvent(kind="key", key="ctrl+c"))) == (
        ("command_cancel", "", ""),
        ("surface_close", "", ""),
    )


def test_command_palette_view_home_end_edit_query_ctrl_edges_move_results() -> None:
    view = CommandPaletteView(_items(), query="dep")

    assert view.handle_input(InputEvent(kind="key", key="home")) is True
    assert view.handle_input(InputEvent(kind="text", text="x")) is True
    assert view.query == "xdep"
    assert view.active_value == ""

    view.set_query("")
    assert view.handle_input(InputEvent(kind="key", key="ctrl+end")) is True
    assert view.active_value == "worker"


def test_command_palette_view_preserves_active_value_across_query_changes() -> None:
    view = CommandPaletteView(_items())

    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.active_value == "logs"

    view.set_query("log")
    assert view.active_value == "logs"

    view.set_query("run")
    assert view.active_value == "deploy"


def test_command_palette_view_paste_updates_query_and_repairs_active() -> None:
    view = CommandPaletteView(_items())

    assert view.handle_input(InputEvent(kind="paste", text="cache")) is True
    assert view.query == "cache"
    assert view.active_value == "cache"


def test_command_palette_view_respects_width_height_cursor_and_empty_state() -> None:
    view = CommandPaletteView(_items(), query="missing")
    view.focus()

    result = render_result(view, width=18, height=5)
    lines = tuple(strip_control_sequences(line.text) for line in result.lines)

    assert len(lines) <= 5
    assert all(visible_width(line) <= 18 for line in lines)
    assert any("No commands" in line for line in lines)
    assert result.cursor is not None

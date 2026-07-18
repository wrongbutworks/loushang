from __future__ import annotations

from loushang.harnesstui.surface.factory import (
    command_surface_view,
    info_surface_view,
)
from loushang.tui import CommandSurface, InfoPanel, SelectItem


def test_info_surface_view_preserves_existing_coding_defaults() -> None:
    view = info_surface_view(title="Available Models", text="first\nsecond")

    assert view.title == "Available Models"
    assert view.purpose == "info"
    assert view.subtitle == ""
    assert view.footer == "Enter/Esc to close"
    assert view.presentation == "bottom"
    assert view.preferred_height is None
    assert view.content == InfoPanel(
        title="Available Models",
        text="first\nsecond",
        footer="",
    )


def test_info_surface_view_keeps_all_copy_and_layout_policy_caller_supplied() -> None:
    view = info_surface_view(
        title="Diagnostics",
        text="body",
        subtitle="Terminal state",
        footer="Esc to dismiss",
        presentation="bottom-exclusive",
        preferred_height=12,
        panel_title="Plain diagnostics",
        panel_footer="Stored output",
    )

    assert view.title == "Diagnostics"
    assert view.subtitle == "Terminal state"
    assert view.footer == "Esc to dismiss"
    assert view.presentation == "bottom-exclusive"
    assert view.preferred_height == 12
    assert view.content == InfoPanel(
        title="Plain diagnostics",
        text="body",
        footer="Stored output",
    )


def test_command_surface_view_preserves_existing_coding_palette_defaults() -> None:
    items = (
        SelectItem(label="/model", value="/model", description="Select a model"),
        SelectItem(label="/status", value="/status"),
    )

    view = command_surface_view(
        title="Commands",
        purpose="command",
        items=(item for item in items),
    )

    assert view.title == "Commands"
    assert view.purpose == "command"
    assert view.subtitle == ""
    assert view.footer == "Enter to select - Esc to close"
    assert view.presentation == "bottom"
    assert view.preferred_height is None
    assert isinstance(view.content, CommandSurface)
    assert view.content.items == list(items)
    assert view.content.max_visible == 8
    assert view.content.filter_text == ""


def test_command_surface_view_accepts_caller_surface_and_search_policy() -> None:
    view = command_surface_view(
        title="Models",
        purpose="model",
        items=(
            SelectItem(label="provider/first", value="first"),
            SelectItem(label="provider/second", value="second"),
        ),
        subtitle="Choose one",
        footer="Enter to use",
        presentation="bottom-exclusive",
        preferred_height=10,
        query="second",
        max_visible=3,
    )

    assert view.purpose == "model"
    assert view.subtitle == "Choose one"
    assert view.footer == "Enter to use"
    assert view.presentation == "bottom-exclusive"
    assert view.preferred_height == 10
    assert isinstance(view.content, CommandSurface)
    assert view.content.max_visible == 3
    assert view.content.filter_text == "second"
    assert view.content.selected_item() == SelectItem(
        label="provider/second",
        value="second",
    )

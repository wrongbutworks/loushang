from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from loushang.harnesstui.surface.view import (
    ScreenSurfacePresentation,
    ScreenSurfaceView,
)
from loushang.tui import CommandSurface, InfoPanel, SelectItem


def info_surface_view(
    *,
    title: str,
    text: str,
    subtitle: str = "",
    footer: str = "Enter/Esc to close",
    presentation: ScreenSurfacePresentation = "bottom",
    preferred_height: int | None = None,
    panel_title: str | None = None,
    panel_footer: str = "",
) -> ScreenSurfaceView:
    """Build a reusable information surface from presentation-ready text."""

    content = InfoPanel.from_text(
        title=title if panel_title is None else panel_title,
        text=text,
        footer=panel_footer,
    )
    return ScreenSurfaceView(
        title=title,
        purpose="info",
        content=content,
        footer=footer,
        subtitle=subtitle,
        presentation=presentation,
        preferred_height=preferred_height,
    )


def command_surface_view(
    *,
    title: str,
    purpose: Literal["model", "command"],
    items: Iterable[SelectItem],
    subtitle: str = "",
    footer: str = "Enter to select - Esc to close",
    presentation: ScreenSurfacePresentation = "bottom",
    preferred_height: int | None = None,
    query: str = "",
    max_visible: int = 8,
) -> ScreenSurfaceView:
    """Build a searchable command-style surface over neutral selection items."""

    content = CommandSurface(
        list(items),
        query=query,
        max_visible=max_visible,
    )
    return ScreenSurfaceView(
        title=title,
        purpose=purpose,
        content=content,
        footer=footer,
        subtitle=subtitle,
        presentation=presentation,
        preferred_height=preferred_height,
    )


__all__ = ["command_surface_view", "info_surface_view"]

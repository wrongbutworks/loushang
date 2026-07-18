from __future__ import annotations

from collections.abc import Callable

from loushang.harnesstui.status.line import (
    StatusLineSettings,
    status_line_settings_from_control,
    status_line_settings_to_patch,
)
from loushang.harnesstui.status.provider import StatusProvider as StatusProvider
from loushang.harnesstui.status.snapshot import StatusSnapshot as StatusSnapshot

CodingTuiStatusProvider = StatusProvider


def statusline_settings_from_settings_manager(
    settings_manager: object | None,
) -> StatusLineSettings | None:
    if settings_manager is None:
        return None
    getter = getattr(settings_manager, "get_statusline_settings", None)
    if not callable(getter):
        return None
    return status_line_settings_from_control(getter())


def statusline_settings_persistence_callback(
    settings_manager: object | None,
    *,
    scope: str = "global",
) -> Callable[[StatusLineSettings], None] | None:
    if settings_manager is None:
        return None
    setter = getattr(settings_manager, "set_statusline_settings", None)
    if not callable(setter):
        return None

    def _save(settings: StatusLineSettings) -> None:
        setter(status_line_settings_to_patch(settings), scope=scope)

    return _save


__all__ = [
    "CodingTuiStatusProvider",
    "StatusSnapshot",
    "statusline_settings_from_settings_manager",
    "statusline_settings_persistence_callback",
]

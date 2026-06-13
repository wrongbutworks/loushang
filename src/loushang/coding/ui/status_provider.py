from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loushang.coding.ui.toolbar import ToolbarSnapshot, render_toolbar
from loushang.tui import SettingItem, SettingsList, SettingsListRenderer


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    model_label: str | None
    cwd: str
    branch: str | None
    session_label: str | None
    thinking_level: str | None
    running: bool
    statusline_visible: bool


class CodingTuiStatusProvider:
    def __init__(
        self,
        *,
        model_label: str | None,
        cwd: str,
        branch: str | None,
        session_label: Callable[[], str | None],
        thinking_level: Callable[[], str | None],
        running: Callable[[], bool],
    ) -> None:
        self._model_label = model_label
        self._cwd = cwd
        self._branch = branch
        self._session_label = session_label
        self._thinking_level = thinking_level
        self._running = running
        self._visible = True

    def render(self) -> str:
        return render_toolbar(
            ToolbarSnapshot(
                model=self._model_label,
                cwd=self._cwd,
                branch=self._branch,
                session=self._session_label(),
                thinking=self._thinking_level(),
                running=self._running(),
            )
        )

    def is_visible(self) -> bool:
        return self._visible

    def snapshot(self) -> StatusSnapshot:
        return StatusSnapshot(
            model_label=self._model_label,
            cwd=self._cwd,
            branch=self._branch,
            session_label=self._session_label(),
            thinking_level=self._thinking_level(),
            running=self._running(),
            statusline_visible=self._visible,
        )

    def set_visible(self, visible: bool | None) -> str:
        if visible is not None:
            self._visible = visible
        return f"Status line: {'on' if self._visible else 'off'}"

    def settings_list(self) -> SettingsList:
        return SettingsList(
            (
                SettingItem(
                    id="statusline",
                    label="Status line",
                    enabled=self._visible,
                ),
            )
        )

    def apply_settings(self, settings: SettingsList) -> str:
        for item in settings.items:
            if item.id == "statusline":
                self._visible = item.enabled
                break
        return self.set_visible(None)

    def settings_text(self) -> str:
        return "".join(fragment for _style, fragment in SettingsListRenderer(title="Settings").render(self.settings_list()))


__all__ = ["CodingTuiStatusProvider", "StatusSnapshot"]

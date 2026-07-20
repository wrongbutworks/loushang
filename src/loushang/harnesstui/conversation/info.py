"""Product-neutral presentation of local conversation information."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loushang.harnesstui.conversation.run_context import StableEmit
from loushang.tui import InfoPanel

InfoPanelPresenter = Callable[[InfoPanel], bool | Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ConversationInfoPresenter:
    """Present local information inline or through an optional modal port."""

    emit: StableEmit
    render_status: Callable[[str], None]
    render_panel: Callable[[InfoPanel], None] | None = None
    present_panel: InfoPanelPresenter | None = None

    async def show(
        self,
        title: str,
        text: str,
        *,
        label: str,
        modal: bool = False,
    ) -> None:
        if modal and self.present_panel is not None:
            panel = InfoPanel.from_text(
                title=title,
                text=text,
                footer="Press Enter to continue.",
            )
            handled = self.present_panel(panel)
            if inspect.isawaitable(handled):
                handled = await handled
            if handled:
                return
        await self.emit(lambda: self._render(title, text), label=label)

    def _render(self, title: str, text: str) -> None:
        if self.render_panel is None:
            self.render_status(text)
            return
        self.render_panel(InfoPanel.from_text(title=title, text=text, footer=""))


__all__ = ["ConversationInfoPresenter", "InfoPanelPresenter"]

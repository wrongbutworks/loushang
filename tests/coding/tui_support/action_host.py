from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TextIO

from loushang.coding.interaction.controller import CodingUiController
from loushang.coding.interaction.screen_host import (
    ScreenCodingConversationActionHost,
    ScreenConversationPresenter,
)
from loushang.harnesstui.conversation.control import ConversationTextAction


def coding_screen_prompt_handler(
    *,
    presenter: ScreenConversationPresenter,
    controller: CodingUiController,
    stderr: TextIO,
    verbose: bool,
) -> Callable[[str], Awaitable[int | None]]:
    """Bind the production Coding action host to a playback prompt callback."""

    host = ScreenCodingConversationActionHost(
        presenter=presenter,
        controller=controller,
        stderr=stderr,
        verbose=verbose,
    )

    async def handle(text: str) -> int | None:
        return await host.submit(
            ConversationTextAction(text=text, source="prompt")
        )

    return handle


__all__ = ["coding_screen_prompt_handler"]

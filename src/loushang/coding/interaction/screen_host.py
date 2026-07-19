from __future__ import annotations

import base64
from typing import Protocol, TextIO

from loushang.ai.types import ImagePart
from loushang.coding.interaction.controller import ControllerResult
from loushang.coding.interaction.intent import (
    AbortIntent,
    CodingUiIntent,
    PromptIntent,
    QuitIntent,
    parse_prompt_intent,
)
from loushang.harnesstui.conversation.attachments import PromptImageAttachment
from loushang.harnesstui.conversation.control import ConversationTextAction


class ScreenConversationPresenter(Protocol):
    def add_error(self, text: str) -> None: ...

    def add_status(self, text: str) -> None: ...

    def set_status(self, message: str | None) -> None: ...


class ScreenConversationController(Protocol):
    async def dispatch(self, intent: CodingUiIntent) -> ControllerResult: ...

    async def steer(
        self,
        text: str,
        images: tuple[ImagePart, ...] | None = None,
    ) -> ControllerResult: ...

    async def follow_up(
        self,
        text: str,
        images: tuple[ImagePart, ...] | None = None,
    ) -> ControllerResult: ...

    async def wait_for_idle(self) -> None: ...


class ScreenCodingConversationActionHost:
    """Bind neutral screen actions to Coding intents and result presentation."""

    def __init__(
        self,
        *,
        presenter: ScreenConversationPresenter,
        controller: ScreenConversationController,
        stderr: TextIO,
        verbose: bool,
    ) -> None:
        self._presenter = presenter
        self._controller = controller
        self._stderr = stderr
        self._verbose = verbose

    async def submit(self, action: ConversationTextAction) -> int | None:
        intent = parse_prompt_intent(action.text)
        if intent is None:
            return None
        if isinstance(intent, QuitIntent):
            return 0
        images = image_parts_from_prompt_attachments(action.attachments)
        if images is not None and isinstance(intent, PromptIntent):
            intent = PromptIntent(intent.text, images=images)
        result = await self._controller.dispatch(intent)
        self._present_result(result)
        return result.exit_code

    async def steer(self, action: ConversationTextAction) -> int | None:
        result = await self._controller.steer(
            action.text,
            images=image_parts_from_prompt_attachments(action.attachments),
        )
        self._present_result(result, status_label="Steering failed")
        return result.exit_code

    async def follow_up(self, action: ConversationTextAction) -> int | None:
        result = await self._controller.follow_up(
            action.text,
            images=image_parts_from_prompt_attachments(action.attachments),
        )
        self._present_result(result, status_label="Follow-up failed")
        return result.exit_code

    async def abort(self) -> None:
        await self._controller.dispatch(AbortIntent())
        await self._controller.wait_for_idle()

    def _present_result(
        self,
        result: ControllerResult,
        *,
        status_label: str = "Request failed",
    ) -> None:
        if result.error_message:
            self._presenter.add_error(result.error_message)
            self._presenter.set_status(f"{status_label}: {result.error_message}")
        elif result.status_message:
            self._presenter.add_status(result.status_message)
            self._presenter.set_status(result.status_message)
        if self._verbose and result.traceback_text:
            self._stderr.write(result.traceback_text)
            self._stderr.flush()


def image_parts_from_prompt_attachments(
    attachments: tuple[PromptImageAttachment, ...],
) -> tuple[ImagePart, ...] | None:
    """Convert neutral prompt attachments at Coding's product boundary."""

    if not attachments:
        return None
    return tuple(
        ImagePart(
            type="image",
            data=base64.b64encode(attachment.bytes).decode("ascii"),
            mime_type=attachment.mime_type,
        )
        for attachment in attachments
    )


__all__ = [
    "ScreenCodingConversationActionHost",
    "image_parts_from_prompt_attachments",
]

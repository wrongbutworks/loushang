from __future__ import annotations

import base64
from typing import Protocol, TextIO

from loushang.ai.types import ImagePart
from loushang.coding.interaction.intent import (
    AbortIntent,
    CodingUiIntent,
    PromptIntent,
    QuitIntent,
    parse_prompt_intent,
)
from loushang.coding.interaction.tui_profile import CODING_SCREEN_ACTION_COPY
from loushang.harness.host.types import HostActionResult
from loushang.harnesstui.conversation.action_presentation import (
    ConversationActionPresentationPort,
    ConversationActionResultPresenter,
    ConversationTracebackPolicy,
    PresentedConversationActionHost,
    PresentedConversationActionPorts,
)
from loushang.harnesstui.conversation.attachments import PromptImageAttachment


class CodingConversationControllerPort(Protocol):
    """Coding controller effects consumed by the shared action host."""

    async def dispatch(self, intent: CodingUiIntent) -> HostActionResult: ...

    async def steer(
        self,
        text: str,
        images: tuple[ImagePart, ...] | None = None,
    ) -> HostActionResult: ...

    async def follow_up(
        self,
        text: str,
        images: tuple[ImagePart, ...] | None = None,
    ) -> HostActionResult: ...

    async def wait_for_idle(self) -> None: ...


class ScreenCodingConversationActionHost(
    PresentedConversationActionHost[CodingUiIntent, tuple[ImagePart, ...] | None]
):
    """Bind shared action sequencing to Coding intents and image values."""

    def __init__(
        self,
        *,
        presenter: ConversationActionPresentationPort,
        controller: CodingConversationControllerPort,
        stderr: TextIO,
        verbose: bool,
    ) -> None:
        super().__init__(
            ports=PresentedConversationActionPorts(
                parse=parse_prompt_intent,
                exit_code=lambda intent: 0 if isinstance(intent, QuitIntent) else None,
                attachments=image_parts_from_prompt_attachments,
                prepare=_intent_with_prompt_attachments,
                dispatch=controller.dispatch,
                steer=controller.steer,
                follow_up=controller.follow_up,
                abort_intent=AbortIntent,
                wait_for_idle=controller.wait_for_idle,
            ),
            presenter=ConversationActionResultPresenter(
                target=presenter,
                stderr=stderr,
                traceback_policy=ConversationTracebackPolicy(enabled=verbose),
            ),
            copy=CODING_SCREEN_ACTION_COPY,
        )


def _intent_with_prompt_attachments(
    intent: CodingUiIntent,
    images: tuple[ImagePart, ...] | None,
) -> CodingUiIntent:
    if images is not None and isinstance(intent, PromptIntent):
        return PromptIntent(intent.text, images=images)
    return intent


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
    "CodingConversationControllerPort",
    "ScreenCodingConversationActionHost",
    "image_parts_from_prompt_attachments",
]

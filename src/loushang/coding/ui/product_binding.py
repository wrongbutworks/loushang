"""Coding policy bound to the shared HarnessTUI conversation components."""

from __future__ import annotations

import base64
from typing import Any, TextIO

from loushang.ai.types import ImagePart
from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.harnesstui.commands.source import materialize_command_items
from loushang.harnesstui.conversation.action_presentation import (
    ConversationActionPresentationPort,
    PresentedConversationActionHost,
    build_standard_presented_conversation_action_host,
)
from loushang.harnesstui.conversation.attachments import PromptImageAttachment
from loushang.harnesstui.conversation.controller import (
    ConversationUiController,
    build_standard_conversation_ui_controller,
)
from loushang.harnesstui.conversation.intents import ConversationIntent
from loushang.observability import get_log

_LOG = get_log(__name__).bind(component="CodingUiController")


def build_coding_ui_controller(
    *,
    session: Any,
    runtime: Any | None = None,
    verbose: bool = False,
) -> ConversationUiController:
    return build_standard_conversation_ui_controller(
        session=session,
        runtime=runtime,
        verbose=verbose,
        command_catalog_factory=lambda current_session: CodingCommandCatalog(
            session_commands=(
                current_session.list_commands
                if callable(getattr(current_session, "list_commands", None))
                else None
            )
        ),
        problem_code_prefix="coding_ui",
        problem_logger=_LOG,
    )


def build_screen_coding_action_host(
    *,
    presenter: ConversationActionPresentationPort,
    controller: ConversationUiController,
    stderr: TextIO,
    verbose: bool,
) -> PresentedConversationActionHost[
    ConversationIntent,
    tuple[ImagePart, ...] | None,
]:
    return build_standard_presented_conversation_action_host(
        presenter=presenter,
        controller=controller,
        stderr=stderr,
        verbose=verbose,
        attachments=image_parts_from_prompt_attachments,
    )


async def snapshot_coding_command_catalog(session: object) -> CodingCommandCatalog:
    getter = getattr(session, "list_commands", None)
    items = await materialize_command_items(getter if callable(getter) else None)
    return CodingCommandCatalog(session_commands=lambda: items)


def image_parts_from_prompt_attachments(
    attachments: tuple[PromptImageAttachment, ...],
) -> tuple[ImagePart, ...] | None:
    """Convert neutral prompt attachments at Coding's Agent boundary."""

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
    "build_coding_ui_controller",
    "build_screen_coding_action_host",
    "image_parts_from_prompt_attachments",
    "snapshot_coding_command_catalog",
]

from __future__ import annotations

from pathlib import Path
from typing import cast

from loushang.harnesstui.conversation.host import ConversationScreenRunProfile
from loushang.harnesstui.conversation.input import (
    ClipboardImageInputProfile,
    ClipboardImageStatusCopy,
    bind_clipboard_image_input_router,
)
from loushang.harnesstui.conversation.input_policy import (
    DEFAULT_CONVERSATION_INPUT_POLICY,
)
from loushang.harnesstui.conversation.screen_runner import (
    ConversationInputRouterFactoryPort,
)

CODING_INTERRUPTION_MESSAGE = (
    "Conversation interrupted - tell the model what to do differently."
)
CODING_CANCELLATION_MESSAGE = "Operation aborted"

_CODING_CLIPBOARD_INPUT = ClipboardImageInputProfile(
    directory=lambda app: Path(app.state.cwd) / ".loushang" / "clipboard",
    display_root=lambda app: Path(app.state.cwd),
    status_copy=ClipboardImageStatusCopy(
        empty="No clipboard image found.",
        read_error_prefix="Unable to read clipboard image: ",
        unsupported_prefix="Unsupported clipboard image type: ",
        write_error_prefix="Unable to attach clipboard image: ",
        attached_prefix="Attached clipboard image: ",
        unknown_type="unknown",
    ),
)

CODING_CONVERSATION_INPUT_POLICY = DEFAULT_CONVERSATION_INPUT_POLICY

build_screen_input_router = bind_clipboard_image_input_router(
    _CODING_CLIPBOARD_INPUT,
    policy=CODING_CONVERSATION_INPUT_POLICY,
)
CODING_SCREEN_RUN_PROFILE = ConversationScreenRunProfile(
    input_router_factory=cast(
        ConversationInputRouterFactoryPort,
        build_screen_input_router,
    ),
    interruption_message=CODING_INTERRUPTION_MESSAGE,
    cancellation_message=CODING_CANCELLATION_MESSAGE,
)

__all__ = [
    "CODING_CANCELLATION_MESSAGE",
    "CODING_CONVERSATION_INPUT_POLICY",
    "CODING_INTERRUPTION_MESSAGE",
    "CODING_SCREEN_RUN_PROFILE",
    "build_screen_input_router",
]

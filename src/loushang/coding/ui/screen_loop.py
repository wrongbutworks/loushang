from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TextIO, cast

from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import (
    build_screen_input_router,
)
from loushang.harnesstui.conversation.attachments import PromptImageAttachment
from loushang.harnesstui.conversation.control import (
    ConversationActionHost,
    ConversationTextAction,
)
from loushang.harnesstui.conversation.screen_runner import (
    ConversationInputRouterPort,
    ConversationScreenPort,
    LocalCommandPredicate,
    ShouldExit,
    SurfaceIntentHandler,
    TerminalModeFactory,
    TerminalSizeProvider,
    TextHandler,
    run_conversation_screen,
)
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager


async def run_screen_coding_tui(
    *,
    app: ScreenCodingTuiApp,
    stdin: TextIO,
    stdout: TextIO,
    action_host: ConversationActionHost,
    handle_local: TextHandler | None = None,
    handle_surface_intent: SurfaceIntentHandler | None = None,
    should_exit: ShouldExit,
    is_local_command: LocalCommandPredicate | None = None,
    keybindings: KeybindingManager | KeybindingConfig | None = None,
    terminal_mode_factory: TerminalModeFactory | None = None,
    terminal_size_provider: TerminalSizeProvider | None = None,
) -> int:
    """Bind Coding attachments and copy to the shared conversation runner."""

    return await run_conversation_screen(
        app=app,
        stdin=stdin,
        stdout=stdout,
        handle_prompt=_bind_text_action(action_host.submit, source="prompt"),
        handle_local=handle_local,
        handle_steer=_bind_text_action(action_host.steer, source="steer"),
        handle_followup=_bind_text_action(
            action_host.follow_up,
            source="follow_up",
        ),
        handle_surface_intent=handle_surface_intent,
        on_abort=action_host.abort,
        should_exit=should_exit,
        is_local_command=is_local_command,
        keybindings=keybindings,
        terminal_mode_factory=terminal_mode_factory,
        terminal_size_provider=terminal_size_provider,
        input_router_factory=_coding_input_router_factory,
        interruption_message=(
            "Conversation interrupted - tell the model what to do differently."
        ),
        cancellation_message="Operation aborted",
    )


def _coding_input_router_factory(
    *,
    app: ConversationScreenPort,
    should_exit: ShouldExit,
    is_local_command: LocalCommandPredicate,
    keybindings: KeybindingManager | KeybindingConfig | None,
    width: int,
    height: int,
) -> ConversationInputRouterPort:
    return build_screen_input_router(
        app=cast(ScreenCodingTuiApp, app),
        should_exit=should_exit,
        is_local_command=is_local_command,
        keybindings=keybindings,
        width=width,
        height=height,
    )


TextActionHandler = Callable[[ConversationTextAction], Awaitable[int | None]]


def _bind_text_action(handler: TextActionHandler, *, source: str) -> TextHandler:
    async def adapted(
        text: str,
        *,
        attachments: tuple[object, ...] | None = None,
    ) -> int | None:
        prompt_attachments = tuple(
            _require_prompt_image_attachment(attachment)
            for attachment in attachments or ()
        )
        return await handler(
            ConversationTextAction(
                text=text,
                attachments=prompt_attachments,
                source=source,
            )
        )

    return adapted


def _require_prompt_image_attachment(value: object) -> PromptImageAttachment:
    if not isinstance(value, PromptImageAttachment):
        raise TypeError("Coding prompt attachments must be prompt images")
    return value


__all__ = ["run_screen_coding_tui"]

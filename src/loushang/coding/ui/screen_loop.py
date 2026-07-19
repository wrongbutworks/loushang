from __future__ import annotations

from typing import TextIO, cast

from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import (
    build_screen_input_router,
    image_parts_from_prompt_attachments,
)
from loushang.harnesstui.conversation.screen_runner import (
    AbortHandler,
    ConversationInputRouterPort,
    ConversationScreenPort,
    LocalCommandPredicate,
    PromptHandler,
    ShouldExit,
    SurfaceIntentHandler,
    TerminalModeFactory,
    TerminalSizeProvider,
    TextHandler,
    maybe_await,
    run_conversation_screen,
    supports_keyword,
)
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager


async def run_screen_coding_tui(
    *,
    app: ScreenCodingTuiApp,
    stdin: TextIO,
    stdout: TextIO,
    handle_prompt: PromptHandler,
    handle_local: TextHandler | None = None,
    handle_steer: TextHandler | None = None,
    handle_followup: TextHandler | None = None,
    handle_surface_intent: SurfaceIntentHandler | None = None,
    on_abort: AbortHandler,
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
        handle_prompt=_adapt_attachment_handler(handle_prompt),
        handle_local=handle_local,
        handle_steer=(
            _adapt_attachment_handler(handle_steer)
            if handle_steer is not None
            else None
        ),
        handle_followup=(
            _adapt_attachment_handler(handle_followup)
            if handle_followup is not None
            else None
        ),
        handle_surface_intent=handle_surface_intent,
        on_abort=on_abort,
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


def _adapt_attachment_handler(handler: TextHandler) -> TextHandler:
    async def adapted(
        text: str,
        *,
        attachments: tuple[object, ...] | None = None,
    ) -> int | None:
        images = image_parts_from_prompt_attachments(attachments)
        if images is not None and supports_keyword(handler, "images"):
            result = await maybe_await(handler(text, images=images))
        else:
            result = await maybe_await(handler(text))
        return result if isinstance(result, int) else None

    return adapted


__all__ = ["run_screen_coding_tui"]

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any, TextIO, cast

from loushang.ai.types import ImagePart
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import ScreenInputRouter
from loushang.harnesstui.conversation.screen_runner import (
    ConversationInputRouterPort,
    ConversationScreenPort,
    abort_active,
    configure_runtime_for_terminal_context,
    elapsed_since,
    finish_active_task,
    maybe_await,
    pop_interrupt_pending_steer,
    run_conversation_screen,
    run_surface_intent_handler,
    supports_keyword,
    terminal_size,
    write_startup_welcome,
)
from loushang.tui import _runner_utils
from loushang.tui.input import InputIntent
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.terminal import TerminalSize
from loushang.tui.terminal_diagnostics import format_terminal_diagnostics

PromptHandler = Callable[..., Awaitable[int | None] | int | None]
TextHandler = Callable[..., Awaitable[int | None] | int | None]
SurfaceIntentHandler = Callable[[InputIntent], Awaitable[int | None] | int | None]
AbortHandler = Callable[[], Awaitable[object] | object]
ShouldExit = Callable[[str], bool]
LocalCommandPredicate = Callable[[str], bool]
TerminalModeFactory = Callable[[TextIO, TextIO], AbstractContextManager[object]]
TerminalSizeProvider = Callable[[], TerminalSize]

_finish_tui_exit = _runner_utils.finish_tui_exit
_flush_pending_input = _runner_utils.flush_pending_input
_input_events_for_chunk = _runner_utils.input_events_for_chunk
_poll_terminal_runtime = _runner_utils.poll_terminal_runtime
_request_runtime_render = _runner_utils.request_runtime_render
_terminal_runtime_wakeup_ms = _runner_utils.terminal_runtime_wakeup_ms
_format_terminal_diagnostics = format_terminal_diagnostics

_write_startup_welcome = write_startup_welcome
_configure_runtime_for_terminal_context = configure_runtime_for_terminal_context
_elapsed_since = elapsed_since
_pop_interrupt_pending_steer = pop_interrupt_pending_steer
_run_surface_intent_handler = run_surface_intent_handler
_maybe_await = maybe_await
_supports_keyword = supports_keyword
_terminal_size = terminal_size


async def _finish_coding_active_task(
    *,
    app: ScreenCodingTuiApp,
    active_task: asyncio.Task[int | None],
    started_at: float | None,
) -> int | None:
    return await finish_active_task(
        app=app,
        active_task=active_task,
        started_at=started_at,
        cancellation_message="Operation aborted",
    )


_finish_active_task = _finish_coding_active_task


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
    """Adapt Coding payloads and product copy to the shared screen runner."""

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
        terminal_size_provider=terminal_size_provider or _terminal_size,
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
    return cast(
        ConversationInputRouterPort,
        ScreenInputRouter(
            app=cast(ScreenCodingTuiApp, app),
            should_exit=should_exit,
            is_local_command=is_local_command,
            keybindings=keybindings,
            width=width,
            height=height,
        ),
    )


async def _abort_active(
    *,
    app: ScreenCodingTuiApp,
    active_task: Any,
    on_abort: AbortHandler,
) -> None:
    await abort_active(
        app=app,
        active_task=active_task,
        on_abort=on_abort,
        interruption_message=(
            "Conversation interrupted - tell the model what to do differently."
        ),
    )


async def _run_prompt_handler(
    handler: PromptHandler,
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> int | None:
    result = await _call_text_handler(handler, text, images=images)
    return result if isinstance(result, int) else None


async def _run_text_handler(
    handler: TextHandler,
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> int | None:
    result = await _call_text_handler(handler, text, images=images)
    return result if isinstance(result, int) else None


async def _call_text_handler(
    handler: Callable[..., object],
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> object:
    if images is not None and _supports_keyword(handler, "images"):
        return await _maybe_await(handler(text, images=images))
    return await _maybe_await(handler(text))


def _adapt_attachment_handler(handler: TextHandler) -> TextHandler:
    async def adapted(
        text: str,
        *,
        attachments: tuple[object, ...] | None = None,
    ) -> int | None:
        images = cast(tuple[ImagePart, ...] | None, attachments)
        return await _run_text_handler(handler, text, images=images)

    return adapted


__all__ = ["run_screen_coding_tui"]

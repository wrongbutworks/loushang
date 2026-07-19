from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO

from loushang.coding.commands.tui import (
    CommandPaletteChooser,
    format_coding_commands,
    select_coding_command,
)
from loushang.coding.diagnostics.tui import DebugCommandHandler
from loushang.coding.interaction.controller import CodingUiController
from loushang.coding.interaction.plain_abort import AbortHandler
from loushang.coding.interaction.plain_dispatch import PromptDispatchHandler
from loushang.coding.interaction.plain_follow_up import FollowUpQueueHandler
from loushang.coding.interaction.plain_host import (
    InfoPanelPresenter,
    PlainCodingConversationActionHost,
)
from loushang.coding.interaction.plain_result import PromptResultHandler
from loushang.coding.model_selection_tui import (
    ModelPaletteChooser,
    format_available_models,
    select_available_model,
)
from loushang.coding.presentation.session import (
    is_running,
    session_error_message,
    session_label,
    thinking_level,
)
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.plain_renderer import PlainCodingUiRenderer
from loushang.harnesstui.conversation.control import (
    ConversationActionHost,
    ConversationTextAction,
)
from loushang.harnesstui.conversation.control import (
    ConversationRunControl as RunLifecycle,
)
from loushang.harnesstui.conversation.control import SteerActionHandler as SteerHandler
from loushang.harnesstui.status.persistence import (
    statusline_settings_from_store,
    statusline_settings_persistence_callback,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.tui import CompletionProvider


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


EnableDebug = Callable[..., Path]
DisableDebug = Callable[[], None]


@dataclass(frozen=True)
class PlainCodingTuiApp:
    lifecycle: RunLifecycle
    action_host: ConversationActionHost
    completion_provider: CompletionProvider | None = None

    async def handle_prompt(self, text: str) -> int | None:
        return await self.action_host.submit(
            ConversationTextAction(text=text, source="plain_prompt")
        )


def build_plain_coding_tui_app(
    *,
    runtime: Any,
    session: Any,
    renderer: PlainCodingUiRenderer,
    event_renderer: Any,
    stderr: TextIO,
    verbose: bool,
    model_label: str | None,
    cwd: str,
    branch: str | None,
    emit: StableEmit,
    trace: TraceFn,
    now: Callable[[], float],
    enable_debug: EnableDebug,
    disable_debug: DisableDebug,
    completion_provider: CompletionProvider | None = None,
    model_palette_chooser: ModelPaletteChooser | None = None,
    command_palette_chooser: CommandPaletteChooser | None = None,
    info_panel_presenter: InfoPanelPresenter | None = None,
) -> PlainCodingTuiApp:
    lifecycle = RunLifecycle()
    controller = CodingUiController(runtime=runtime, session=session, verbose=verbose)
    follow_up_queue = FollowUpQueueHandler(
        lifecycle=lifecycle,
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=trace,
    )
    steer_handler = SteerHandler(
        lifecycle=lifecycle,
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=trace,
    )
    abort_handler = AbortHandler(
        lifecycle=lifecycle,
        controller=controller,
        renderer=renderer,
        emit=emit,
        session_running=lambda: is_running(session),
        trace=trace,
    )
    debug_command = DebugCommandHandler(
        session=session,
        cwd=cwd,
        renderer=renderer,
        emit=emit,
        trace=trace,
        enable=enable_debug,
        disable=disable_debug,
    )
    prompt_dispatch = PromptDispatchHandler(
        lifecycle=lifecycle,
        controller=controller,
        session_running=lambda: is_running(session),
        now=now,
        trace=trace,
    )
    prompt_result = PromptResultHandler(
        lifecycle=lifecycle,
        renderer=renderer,
        emit=emit,
        stderr=stderr,
        verbose=verbose,
        last_error_message=lambda: event_renderer.last_error_message,
        session_error_message=lambda: session_error_message(session),
        now=now,
        trace=trace,
    )
    settings_manager = getattr(session, "settings_manager", None)
    status_provider = StatusProvider(
        model_label=model_label,
        cwd=cwd,
        branch=branch,
        session_label=lambda: session_label(session),
        thinking_level=lambda: thinking_level(session),
        running=lambda: lifecycle.visible_running(session_running=is_running(session)),
        statusline_settings=statusline_settings_from_store(settings_manager),
        on_statusline_settings_changed=statusline_settings_persistence_callback(settings_manager),
    )
    action_host = PlainCodingConversationActionHost(
        lifecycle=lifecycle,
        follow_up=follow_up_queue.queue,
        steer=steer_handler.steer,
        debug=debug_command.handle,
        dispatch=prompt_dispatch.dispatch,
        result=prompt_result.handle,
        abort=abort_handler.abort,
        session=session,
        emit=emit,
        render_status=renderer.render_status,
        render_info_panel=getattr(renderer, "render_info_panel", None),
        present_info_panel=info_panel_presenter,
        model_select=lambda query: select_available_model(session, query=query, choose=model_palette_chooser),
        models=lambda query: format_available_models(session, query=query),
        command_select=lambda query: select_coding_command(session, query=query, choose=command_palette_chooser),
        commands=lambda query: format_coding_commands(session, query=query),
        hotkeys=format_hotkeys,
        settings_text=status_provider.settings_summary_text,
        now=now,
        session_running=lambda: is_running(session),
        trace=trace,
    )
    return PlainCodingTuiApp(
        lifecycle=lifecycle,
        action_host=action_host,
        completion_provider=completion_provider,
    )


__all__ = ["PlainCodingTuiApp", "build_plain_coding_tui_app"]

"""Product-neutral composition for a plain conversation application."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TextIO, TypeVar

from loushang.harnesstui.conversation.control import (
    AbortActionHandler,
    ActionResult,
    ConversationActionHost,
    ConversationRunControl,
    ConversationTextAction,
    FollowUpActionHandler,
    InterruptionRenderer,
    SteerActionHandler,
)
from loushang.harnesstui.conversation.dispatch import (
    ConversationDispatchHandler,
    ConversationDispatchOutcome,
    ConversationResultPresenter,
    DispatchResult,
    ResultRenderer,
)
from loushang.harnesstui.conversation.host import (
    ConversationHostPorts,
    ConversationHostProfile,
    RoutedConversationActionHost,
)
from loushang.harnesstui.conversation.run_context import StableEmit, TraceFn
from loushang.tui import CompletionProvider

IntentT = TypeVar("IntentT")
IntentT_contra = TypeVar("IntentT_contra", contravariant=True)
LocalT = TypeVar("LocalT")
PendingT = TypeVar("PendingT")


class PlainConversationController(Protocol[IntentT_contra]):
    async def dispatch(self, intent: IntentT_contra) -> DispatchResult: ...

    async def steer(self, text: str) -> ActionResult: ...

    async def follow_up(self, text: str) -> ActionResult: ...


class PlainConversationRenderer(
    InterruptionRenderer,
    ResultRenderer,
    Protocol,
):
    pass


@dataclass(frozen=True)
class PlainConversationApp:
    lifecycle: ConversationRunControl
    action_host: ConversationActionHost
    completion_provider: CompletionProvider | None = None

    async def handle_prompt(self, text: str) -> int | None:
        return await self.action_host.submit(
            ConversationTextAction(text=text, source="plain_prompt")
        )


def build_plain_conversation_app(
    *,
    lifecycle: ConversationRunControl,
    profile: ConversationHostProfile[IntentT, LocalT],
    controller: PlainConversationController[IntentT],
    renderer: PlainConversationRenderer,
    emit: StableEmit,
    trace: TraceFn,
    session_running: Callable[[], bool],
    abort_action: Callable[[], Awaitable[Any]],
    abort_settling: Callable[[ConversationTextAction, IntentT], Awaitable[None]],
    is_work_intent: Callable[[IntentT], bool],
    local: Callable[
        [ConversationTextAction, IntentT, LocalT | None],
        Awaitable[int | None],
    ],
    resolve_error: Callable[[ConversationDispatchOutcome], str | None],
    suppress_result: Callable[[ConversationDispatchOutcome, str | None], bool],
    stderr: TextIO,
    verbose: bool,
    last_error_message: Callable[[], str | None],
    now: Callable[[], float],
    restore_queue: Callable[[str], Awaitable[str | None]],
    pending_messages: Callable[[], PendingT],
    idle_follow_up_message: str,
    queued_follow_up_message: str,
    completion_provider: CompletionProvider | None = None,
) -> PlainConversationApp:
    """Compose shared action handlers around caller policy and effects."""

    follow_up = FollowUpActionHandler(
        lifecycle=lifecycle,
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=trace,
        idle_status_message=idle_follow_up_message,
        queued_status_message=queued_follow_up_message,
    )
    steer = SteerActionHandler(
        lifecycle=lifecycle,
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=trace,
    )
    abort = AbortActionHandler(
        run_control=lifecycle,
        abort_action=abort_action,
        renderer=renderer,
        emit=emit,
        session_running=session_running,
        trace=trace,
    )
    dispatch = ConversationDispatchHandler[IntentT](
        lifecycle=lifecycle,
        controller=controller,
        is_work_intent=is_work_intent,
        session_running=session_running,
        now=now,
        trace=trace,
    )
    presenter = ConversationResultPresenter(
        renderer=renderer,
        emit=emit,
        stderr=stderr,
        verbose=verbose,
        last_error_message=last_error_message,
        now=now,
        trace=trace,
    )

    async def present_result(
        outcome: ConversationDispatchOutcome,
        _action: ConversationTextAction,
        _intent: IntentT,
        prompt_started: float,
    ) -> int | None:
        error_message = resolve_error(outcome)
        if suppress_result(outcome, error_message):
            return outcome.result.exit_code
        return await presenter.handle(
            outcome,
            prompt_started=prompt_started,
            error_message=error_message,
        )

    host = RoutedConversationActionHost(
        profile=profile,
        ports=ConversationHostPorts[
            IntentT,
            ConversationDispatchOutcome,
            LocalT,
            PendingT,
        ](
            abort_settling=abort_settling,
            follow_up=lambda action: follow_up.queue(
                action.text,
                source=action.source,
            ),
            steer=lambda action: steer.steer(action.text),
            local=local,
            dispatch=lambda _action, intent: dispatch.dispatch(intent),
            result=present_result,
            abort=abort.abort,
            restore_queue=restore_queue,
            pending_messages=pending_messages,
        ),
    )
    return PlainConversationApp(
        lifecycle=lifecycle,
        action_host=host,
        completion_provider=completion_provider,
    )


__all__ = [
    "PlainConversationApp",
    "PlainConversationController",
    "PlainConversationRenderer",
    "build_plain_conversation_app",
]

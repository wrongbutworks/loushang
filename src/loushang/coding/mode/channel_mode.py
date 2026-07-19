"""Coding adapter for the standard Channel operation protocol."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol, TextIO, cast

from loushang.channel import (
    ChannelDelivery,
    ChannelDeliveryListener,
    ChannelError,
    ChannelEventDelivery,
    ChannelHost,
    ChannelOperationAccepted,
    ChannelOperationCancelled,
    ChannelOperationCancelRequest,
    ChannelOperationRequest,
)
from loushang.channel.types import ChannelEnvelope
from loushang.coding.event import (
    SUPPORTED_JSON_EVENT_VIEWS,
    JsonEventView,
    normalize_event_select,
    project_runtime_event_to_json_views,
    should_emit_runtime_event_view,
)
from loushang.harness.events import RuntimeEvent

RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


class CodingChannelSession(Protocol):
    """The narrow Coding session shape needed by the standard Channel adapter."""

    session_id: str

    def subscribe_runtime_events(
        self, listener: RuntimeEventListener
    ) -> Unsubscribe: ...

    def prompt(
        self,
        text: str,
        *,
        streaming_behavior: str | None = None,
        source: str | None = None,
    ) -> Awaitable[None]: ...

    def abort(self) -> Awaitable[None] | None: ...


class CodingChannelOperationPort:
    """Map a standard Coding turn operation onto one Coding session."""

    def __init__(
        self,
        *,
        session: CodingChannelSession,
        event_view: JsonEventView = "full",
        event_select: Sequence[str] | str | None = None,
    ) -> None:
        if event_view not in SUPPORTED_JSON_EVENT_VIEWS:
            raise ValueError(f"unsupported json event view: {event_view}")
        self._session = session
        self._event_view = event_view
        self._event_select = normalize_event_select(event_select)
        self._listeners: list[ChannelDeliveryListener] = []
        self._runtime_unsubscribe: Unsubscribe | None = None
        self._active_operation_id: str | None = None
        self._active_request_id: str | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def accept_operation(
        self, request: ChannelOperationRequest
    ) -> ChannelOperationAccepted | ChannelError:
        operation = request.envelope.payload
        if operation.domain != "coding":
            return _operation_error(
                request,
                code="unsupported_domain",
                message="Coding Channel accepts only operations in the coding domain.",
            )
        if operation.kind != "SubmitCodingTurn":
            return _operation_error(
                request,
                code="unsupported_operation",
                message="Coding Channel supports only SubmitCodingTurn.",
            )
        if operation.session_id not in (None, self._session.session_id):
            return _operation_error(
                request,
                code="session_mismatch",
                message="operation session_id does not match the active Coding session.",
            )
        if self._active_operation_id is not None:
            return _operation_error(
                request,
                code="operation_in_progress",
                message="the active Coding session already has a Channel operation.",
                retryable=True,
            )

        try:
            text, streaming_behavior = _turn_payload(operation.payload)
        except ValueError as error:
            return _operation_error(
                request,
                code="invalid_operation_payload",
                message=str(error),
            )

        operation_id = operation.operation_id
        self._active_operation_id = operation_id
        self._active_request_id = request.request_id
        task = asyncio.create_task(
            self._run_turn(
                operation_id=operation_id,
                request_id=request.request_id,
                text=text,
                streaming_behavior=streaming_behavior,
            )
        )
        self._tasks[operation_id] = task
        return ChannelOperationAccepted(
            request_id=request.request_id,
            operation_id=operation_id,
        )

    async def cancel_operation(
        self, request: ChannelOperationCancelRequest
    ) -> ChannelOperationCancelled | ChannelError:
        if request.operation_id not in self._tasks:
            return ChannelError(
                code="unknown_operation",
                message="the Coding session has no active operation with this id.",
                request_id=request.request_id,
            )
        try:
            await _maybe_await(self._session.abort())
        except Exception as error:
            return ChannelError(
                code="cancellation_rejected",
                message=str(error) or type(error).__name__,
                request_id=request.request_id,
            )
        return ChannelOperationCancelled(
            request_id=request.request_id,
            operation_id=request.operation_id,
        )

    def subscribe_deliveries(self, listener: ChannelDeliveryListener) -> Unsubscribe:
        self._listeners.append(listener)
        if self._runtime_unsubscribe is None:
            self._runtime_unsubscribe = self._session.subscribe_runtime_events(
                self._on_runtime_event
            )

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
            if not self._listeners:
                self._release_runtime_subscription()

        return unsubscribe

    def close(self) -> None:
        """Release the runtime subscription after its Channel host stops."""

        for task in tuple(self._tasks.values()):
            task.cancel()
        self._tasks.clear()
        self._active_operation_id = None
        self._active_request_id = None
        self._listeners.clear()
        self._release_runtime_subscription()

    async def _run_turn(
        self,
        *,
        operation_id: str,
        request_id: str,
        text: str,
        streaming_behavior: str | None,
    ) -> None:
        try:
            await self._session.prompt(
                text,
                streaming_behavior=streaming_behavior,
                source="channel",
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._publish(
                ChannelError(
                    code="operation_dispatch_failed",
                    message=str(error) or type(error).__name__,
                    request_id=request_id,
                )
            )
        finally:
            self._tasks.pop(operation_id, None)
            if self._active_operation_id == operation_id:
                self._active_operation_id = None
                self._active_request_id = None

    def _on_runtime_event(self, event: RuntimeEvent[object]) -> None:
        operation_id = self._active_operation_id
        for index, view in enumerate(
            project_runtime_event_to_json_views(event, event_view=self._event_view),
            start=1,
        ):
            if not should_emit_runtime_event_view(view, self._event_select):
                continue
            if operation_id is not None:
                view = replace(view, correlation_id=operation_id)
            self._publish(
                ChannelEventDelivery(
                    envelope=ChannelEnvelope(
                        envelope_id=f"channel:{event.event_id}:{index}",
                        kind="event",
                        payload=view,
                    )
                )
            )

    def _publish(self, delivery: ChannelDelivery) -> None:
        for listener in tuple(self._listeners):
            result = listener(delivery)
            if inspect.isawaitable(result):
                asyncio.get_running_loop().create_task(result)

    def _release_runtime_subscription(self) -> None:
        unsubscribe = self._runtime_unsubscribe
        self._runtime_unsubscribe = None
        if unsubscribe is not None:
            unsubscribe()


def _operation_error(
    request: ChannelOperationRequest,
    *,
    code: str,
    message: str,
    retryable: bool = False,
) -> ChannelError:
    return ChannelError(
        code=code,
        message=message,
        request_id=request.request_id,
        retryable=retryable,
    )


def _turn_payload(payload: object) -> tuple[str, str | None]:
    if not isinstance(payload, Mapping):
        raise ValueError("SubmitCodingTurn payload must be a JSON object.")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("SubmitCodingTurn payload requires non-empty text.")
    streaming_behavior = payload.get("streaming_behavior")
    if streaming_behavior is None:
        return text, None
    if not isinstance(streaming_behavior, str) or not streaming_behavior:
        raise ValueError("streaming_behavior must be a non-empty string when set.")
    return text, streaming_behavior


async def _maybe_await(value: object) -> None:
    if inspect.isawaitable(value):
        await value


async def run_channel_mode(
    *,
    runtime: object,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    event_view: JsonEventView = "full",
    event_select: Sequence[str] | str | None = None,
) -> int:
    """Run the standard Channel JSONL host against the active Coding session."""

    session = _current_session(runtime)
    port = CodingChannelOperationPort(
        session=session,
        event_view=event_view,
        event_select=event_select,
    )
    host = ChannelHost(port=port, stdin=stdin, stdout=stdout, stderr=stderr)
    try:
        return await host.run()
    finally:
        port.close()


def _current_session(runtime: object) -> CodingChannelSession:
    getter = getattr(runtime, "get_current_session", None)
    if not callable(getter):
        raise TypeError("Channel mode runtime must provide get_current_session()")
    session = getter()
    if session is None:
        raise RuntimeError("Channel mode requires an active Coding session")
    return cast(CodingChannelSession, session)


__all__ = [
    "CodingChannelOperationPort",
    "CodingChannelSession",
    "run_channel_mode",
]

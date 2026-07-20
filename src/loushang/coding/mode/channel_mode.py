"""Coding adapter for the standard Channel operation protocol."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import TextIO, cast

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
from loushang.coding.work_runtime import (
    CodingOperationInProgressError,
    CodingWorkRuntime,
)
from loushang.harness.events import RuntimeEvent
from loushang.harness.session import SessionControlPort
from loushang.work import InMemoryEventLogBackend, WorkEvent
from loushang.work.event_log import EventLogBackend

Unsubscribe = Callable[[], None]

# Compatibility type alias. The actual control contract is Harness-owned.
CodingChannelSession = SessionControlPort


class CodingChannelOperationPort:
    """Map a standard Coding turn operation onto one Coding session."""

    def __init__(
        self,
        *,
        session: SessionControlPort,
        event_view: JsonEventView = "full",
        event_select: Sequence[str] | str | None = None,
        work_event_log: EventLogBackend | None = None,
        coding_work_runtime: CodingWorkRuntime | None = None,
    ) -> None:
        if event_view not in SUPPORTED_JSON_EVENT_VIEWS:
            raise ValueError(f"unsupported json event view: {event_view}")
        self._session = session
        self._event_view = event_view
        self._event_select = normalize_event_select(event_select)
        self._listeners: list[ChannelDeliveryListener] = []
        self._runtime_unsubscribe: Unsubscribe | None = None
        self._coding_runtime = coding_work_runtime or CodingWorkRuntime(
            session=session,
            event_log=work_event_log or InMemoryEventLogBackend(),
        )
        self._work_runtime = self._coding_runtime.work_runtime
        self._work_unsubscribe = self._work_runtime.subscribe_events(
            self._on_work_event
        )
        self._close_task: asyncio.Task[None] | None = None

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
        if self._work_runtime.active_runs(session_id=self._session.session_id):
            return _operation_error(
                request,
                code="operation_in_progress",
                message="the active Coding session already has a Channel operation.",
                retryable=True,
            )

        try:
            _turn_payload(operation.payload)
        except ValueError as error:
            return _operation_error(
                request,
                code="invalid_operation_payload",
                message=str(error),
            )

        try:
            accepted = await self._coding_runtime.accept_operation(operation)
        except CodingOperationInProgressError:
            return _operation_error(
                request,
                code="operation_in_progress",
                message="the active Coding session already has a Channel operation.",
                retryable=True,
            )
        return ChannelOperationAccepted(
            request_id=request.request_id,
            operation_id=operation.operation_id,
            run_id=accepted.run_id,
        )

    async def cancel_operation(
        self, request: ChannelOperationCancelRequest
    ) -> ChannelOperationCancelled | ChannelError:
        run = self._work_runtime.get_run_for_operation(request.operation_id)
        if run is None or run.status in {
            "completed",
            "failed",
            "cancelled",
            "orphaned",
        }:
            return ChannelError(
                code="unknown_operation",
                message="the Coding session has no active operation with this id.",
                request_id=request.request_id,
            )
        try:
            await self._work_runtime.cancel(run.run_id)
        except Exception as error:
            return ChannelError(
                code="cancellation_failed",
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

        self._listeners.clear()
        self._release_runtime_subscription()
        self._work_unsubscribe()
        if self._work_runtime.active_runs() and self._close_task is None:
            self._close_task = asyncio.get_running_loop().create_task(
                self._work_runtime.dispose()
            )

    async def aclose(self) -> None:
        self.close()
        if self._close_task is not None:
            await self._close_task

    def _on_runtime_event(self, event: RuntimeEvent[object]) -> None:
        active_runs = self._work_runtime.active_runs(
            session_id=self._session.session_id
        )
        operation_id = active_runs[0].operation_id if active_runs else None
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

    def _on_work_event(self, event: WorkEvent) -> None:
        self._publish(
            ChannelEventDelivery(
                envelope=ChannelEnvelope(
                    envelope_id=f"channel:work:{event.event_id}",
                    kind="event",
                    payload=event,
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


async def run_channel_mode(
    *,
    runtime: object,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    event_view: JsonEventView = "full",
    event_select: Sequence[str] | str | None = None,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: CodingWorkRuntime | None = None,
) -> int:
    """Run the standard Channel JSONL host against the active Coding session."""

    session = _current_session_control(runtime)
    port = CodingChannelOperationPort(
        session=session,
        event_view=event_view,
        event_select=event_select,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
    )
    host = ChannelHost(port=port, stdin=stdin, stdout=stdout, stderr=stderr)
    try:
        return await host.run()
    finally:
        await port.aclose()


def _current_session_control(runtime: object) -> SessionControlPort:
    getter = getattr(runtime, "get_current_session", None)
    if not callable(getter):
        raise TypeError("Channel mode runtime must provide get_current_session()")
    session = getter()
    if session is None:
        raise RuntimeError("Channel mode requires an active Coding session")
    control = getattr(session, "session_control", None)
    if control is None:
        raise TypeError("Active Coding session must expose Harness session_control")
    return cast(SessionControlPort, control)


__all__ = [
    "CodingChannelOperationPort",
    "CodingChannelSession",
    "run_channel_mode",
]

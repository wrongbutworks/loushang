from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Callable, Generic, TypeVar, cast

from loushang.ai.types import (
    AssistantMessage,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
)

TEvent = TypeVar("TEvent")
TResult = TypeVar("TResult")

DEFAULT_EVENT_STREAM_QUEUE_SIZE = 256


class EventStream(Generic[TEvent, TResult]):
    def __init__(
        self,
        *,
        is_terminal: Callable[[TEvent], bool],
        extract_result: Callable[[TEvent], TResult],
        max_queue_size: int = DEFAULT_EVENT_STREAM_QUEUE_SIZE,
    ) -> None:
        self._queue: asyncio.Queue[TEvent | None] = asyncio.Queue(
            maxsize=max(1, max_queue_size)
        )
        self._final_result: TResult | None = None
        self._producer_error: BaseException | None = None
        self._ended: bool = False
        self._producer_task: asyncio.Task[object] | None = None
        self._is_terminal = is_terminal
        self._extract_result = extract_result

    def push(self, event: TEvent) -> None:
        if self._ended:
            return
        self._queue.put_nowait(event)
        if self._is_terminal(event):
            self._final_result = self._extract_result(event)
            self._put_nowait_force(None)
            self._ended = True

    async def emit(self, event: TEvent) -> None:
        if self._ended:
            return
        await self._queue.put(event)
        if self._is_terminal(event):
            self._final_result = self._extract_result(event)
            await self._queue.put(None)
            self._ended = True

    def __aiter__(self) -> AsyncIterator[TEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[TEvent]:
        try:
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not self._ended:
                await self.aclose()

    def attach_task(self, task: asyncio.Task[object]) -> None:
        self._producer_task = task
        task.add_done_callback(self._finish_from_task)

    async def aclose(self) -> None:
        if self._ended:
            return
        self._ended = True
        task = self._producer_task
        if task is not None and not task.done():
            task.cancel()
        self._put_nowait_force(None)

    cancel = aclose

    def end(self, result: TResult | None = None) -> None:
        if self._ended:
            return
        self._ended = True
        if result is not None:
            self._final_result = result
        self._put_nowait_force(None)

    async def result(self) -> TResult:
        if self._final_result is not None:
            return self._final_result

        async for _ in self:
            if self._final_result is not None:
                return self._final_result

        if self._final_result is None:
            if self._producer_error is not None:
                raise RuntimeError(
                    "Event stream producer failed"
                ) from self._producer_error
            raise RuntimeError("Event stream finished without a final result")
        return self._final_result

    def _finish_from_task(self, task: asyncio.Task[object]) -> None:
        if self._ended:
            return
        if task.cancelled():
            self.end()
            return
        try:
            self._producer_error = task.exception()
        except asyncio.CancelledError:
            self.end()
            return
        self.end()

    def _put_nowait_force(self, item: TEvent | None) -> None:
        try:
            self._queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        try:
            self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        self._queue.put_nowait(item)


class AssistantMessageEventStream(EventStream[AssistantMessageEvent, AssistantMessage]):
    def __init__(
        self, *, max_queue_size: int = DEFAULT_EVENT_STREAM_QUEUE_SIZE
    ) -> None:
        super().__init__(
            is_terminal=lambda event: event["type"] in {"done", "error"},
            extract_result=_extract_assistant_message_result,
            max_queue_size=max_queue_size,
        )

    def push(self, event: AssistantMessageEvent) -> None:
        self._validate_event(event)
        super().push(event)

    async def emit(self, event: AssistantMessageEvent) -> None:
        self._validate_event(event)
        await super().emit(event)

    def _validate_event(self, event: AssistantMessageEvent) -> None:
        event_type = event["type"]
        if event_type not in {
            "start",
            "text_start",
            "text_delta",
            "text_end",
            "thinking_start",
            "thinking_delta",
            "thinking_end",
            "toolcall_start",
            "toolcall_delta",
            "toolcall_end",
            "image_start",
            "image_end",
            "done",
            "error",
        }:
            raise ValueError(f"Unsupported event type: {event_type}")

    def end(self, message: AssistantMessage | None = None) -> None:
        if self._ended:
            return
        self._ended = True
        if message is not None:
            self._final_result = message
            done_event: DoneEvent = {
                "type": "done",
                "reason": "stop",
                "message": message,
            }
            self._put_nowait_force(done_event)
        self._put_nowait_force(None)


def _extract_assistant_message_result(event: AssistantMessageEvent) -> AssistantMessage:
    if event["type"] == "done":
        return event["message"]
    return cast(ErrorEvent, event)["error"]

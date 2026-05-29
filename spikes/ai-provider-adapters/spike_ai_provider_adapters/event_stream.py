from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .types import AssistantMessage, AssistantMessageEvent

_SENTINEL = object()


@dataclass(slots=True)
class _StreamWriter:
    _stream: "AssistantMessageEventStream"

    def push(self, event: AssistantMessageEvent) -> None:
        self._stream._queue.put_nowait(event)

    def finish(self, message: AssistantMessage) -> None:
        final = self._stream._ensure_future()
        if not final.done():
            final.set_result(message)
        self._stream._queue.put_nowait(AssistantMessageEvent(type="done"))
        self._stream._queue.put_nowait(_SENTINEL)

    def fail(self, message: AssistantMessage) -> None:
        final = self._stream._ensure_future()
        if not final.done():
            final.set_result(message)
        self._stream._queue.put_nowait(
            AssistantMessageEvent(type="error", reason=message.stop_reason, message=message.error_message)
        )
        self._stream._queue.put_nowait(_SENTINEL)


class AssistantMessageEventStream:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._final: asyncio.Future[AssistantMessage] | None = None

    def _ensure_future(self) -> asyncio.Future[AssistantMessage]:
        if self._final is None:
            self._final = asyncio.get_running_loop().create_future()
        return self._final

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                return
            yield item

    async def result(self) -> AssistantMessage:
        return await self._ensure_future()


def create_assistant_message_event_stream() -> tuple[AssistantMessageEventStream, _StreamWriter]:
    stream = AssistantMessageEventStream()
    return stream, _StreamWriter(stream)

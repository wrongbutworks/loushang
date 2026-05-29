from __future__ import annotations

from dataclasses import dataclass

from spike_abort_signal import AbortSignalLike
from spike_event_stream import _StreamWriter
from spike_types import (
    AssistantMessage,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    StopReason,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
)


@dataclass(slots=True)
class RawTextPart:
    delta: str


@dataclass(slots=True)
class RawFinish:
    reason: StopReason


class AssistantMessageAssembler:
    def __init__(self, writer: _StreamWriter, signal: AbortSignalLike | None = None) -> None:
        self._writer = writer
        self._signal = signal
        self._message = AssistantMessage(content=[])
        self._current_text_index: int | None = None
        self._current_text = ""
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._writer.push(StartEvent(partial=self._partial()))

    def feed(self, part: RawTextPart) -> None:
        self._ensure_not_cancelled()
        self.start()
        if self._current_text_index is None:
            self._current_text_index = len(self._message.content or [])
            self._message.content = self._message.content or []
            self._message.content.append(TextContent(text=""))
            self._writer.push(
                TextStartEvent(content_index=self._current_text_index, partial=self._partial())
            )
        self._current_text += part.delta
        self._message.content[-1].text = self._current_text
        self._writer.push(
            TextDeltaEvent(
                content_index=self._current_text_index,
                delta=part.delta,
                partial=self._partial(),
            )
        )

    def finish(self, finish: RawFinish) -> None:
        self._ensure_not_cancelled()
        self.start()
        if self._current_text_index is not None:
            self._writer.push(
                TextEndEvent(
                    content_index=self._current_text_index,
                    content=self._current_text,
                    partial=self._partial(),
                )
            )
        self._message.stop_reason = finish.reason
        final_message = self._final_message()
        self._writer.push(DoneEvent(reason=finish.reason, message=final_message))
        self._writer.finish(final_message)

    def abort(self, reason: StopReason = "aborted") -> None:
        self._message.stop_reason = reason
        self._message.error_message = "cancelled"
        final_message = self._final_message()
        self._writer.push(ErrorEvent(reason="aborted", error=final_message))
        self._writer.fail(final_message)

    def _ensure_not_cancelled(self) -> None:
        if self._signal is not None and self._signal.cancelled:
            self.abort("aborted")
            raise RuntimeError("aborted")

    def _partial(self) -> AssistantMessage:
        return AssistantMessage(
            content=list(self._message.content or []),
            stop_reason=self._message.stop_reason,
            error_message=self._message.error_message,
            timestamp=self._message.timestamp,
        )

    def _final_message(self) -> AssistantMessage:
        return AssistantMessage(
            content=list(self._message.content or []),
            stop_reason=self._message.stop_reason,
            error_message=self._message.error_message,
            timestamp=self._message.timestamp,
        )


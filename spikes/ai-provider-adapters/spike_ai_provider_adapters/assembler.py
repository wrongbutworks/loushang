from __future__ import annotations

from dataclasses import dataclass, field

from .event_stream import _StreamWriter
from .raw_parts import RawDone, RawError, RawTextDelta
from .types import AssistantMessage, AssistantMessageEvent, Context, Model, TextContent, Usage


@dataclass
class TextAssembler:
    writer: _StreamWriter
    model: Model
    context: Context
    provider_name: str
    _buffer: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.writer.push(AssistantMessageEvent(type="start"))

    def emit_text(self, part: RawTextDelta) -> None:
        self._buffer.append(part.text)
        self.writer.push(AssistantMessageEvent(type="text_delta", text=part.text))

    def finish(self, part: RawDone) -> None:
        message = AssistantMessage(
            content=[TextContent(text="".join(self._buffer))],
            api=self.model.api,
            provider=self.provider_name,
            model=self.model.id,
            response_id=part.response_id,
            usage=_build_usage(part.usage),
            stop_reason=part.stop_reason,  # type: ignore[assignment]
        )
        self.writer.finish(message)

    def fail(self, part: RawError) -> None:
        message = AssistantMessage(
            content=[TextContent(text="".join(self._buffer))],
            api=self.model.api,
            provider=self.provider_name,
            model=self.model.id,
            response_id=part.response_id,
            usage=_build_usage(part.usage),
            stop_reason="aborted" if "aborted" in part.message.lower() else "error",
            error_message=part.message,
        )
        self.writer.fail(message)


def _build_usage(payload: dict[str, int] | None) -> Usage:
    if not payload:
        return Usage()
    input_tokens = payload.get("input_tokens", 0)
    output_tokens = payload.get("output_tokens", 0)
    cache_read = payload.get("cache_read_input_tokens", 0)
    cache_write = payload.get("cache_creation_input_tokens", 0)
    return Usage(
        input=input_tokens,
        output=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        total_tokens=input_tokens + output_tokens + cache_read + cache_write,
        cost={},
    )

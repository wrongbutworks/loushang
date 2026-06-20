from __future__ import annotations

from typing import cast

from loushang.ai.event_stream.raw_parts import (
    AbortedPart,
    ImagePartRaw,
    RawPart,
    RedactedThinkingPart,
    ResponseDonePart,
    ResponseErrorPart,
    ResponseStartPart,
    StopReasonPart,
    TextDeltaPart,
    TextSignatureDeltaPart,
    ThinkingDeltaPart,
    ThinkingSignatureDeltaPart,
    ToolCallArgsDeltaPart,
    ToolCallDonePart,
    ToolCallStartPart,
    ToolCallThoughtSignaturePart,
    UsageCostMultiplierPart,
    UsageDeltaPart,
)
from loushang.ai.event_stream.stream import AssistantMessageEventStream
from loushang.ai.pricing import calculate_usage_cost
from loushang.ai.provider.errors import is_http_status_code
from loushang.ai.types import (
    AssistantMessage,
    DoneEvent,
    ErrorEvent,
    ImageEndEvent,
    ImagePart,
    ImageStartEvent,
    StartEvent,
    StopReason,
    TextDeltaEvent,
    TextEndEvent,
    TextPart,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingPart,
    ThinkingStartEvent,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    Usage,
)
from loushang.ai.utils.json_parse import parse_streaming_json


class RawAssembler:
    def __init__(
        self,
        *,
        stream: AssistantMessageEventStream,
        api: str,
        provider: str,
        model: str,
        pricing=None,
    ) -> None:
        self._stream = stream
        self._api = api
        self._provider = provider
        self._model = model
        self._pricing = pricing
        self._response_id: str | None = None
        self._text_chunks: list[str] = []
        self._text_signature: str | None = None
        self._thinking_chunks: list[str] = []
        self._thinking_signature_chunks: list[str] = []
        self._thinking_redacted = False
        self._images: list[ImagePart] = []
        self._tool_calls: list[ToolCall] = []
        self._tool_calls_by_id: dict[str, ToolCall] = {}
        self._active_tool_call_id: str | None = None
        self._active_tool_call_name: str | None = None
        self._active_tool_call_args_chunks: list[str] = []
        self._active_tool_call_thought_signature: str | None = None
        self._content_order: list[tuple[str, str | None]] = []
        self._stop_reason = "stop"
        self._usage = Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost=None,
        )
        self._usage_cost_multiplier = 1.0
        self._final_message: AssistantMessage | None = None
        self._started = False
        self._text_started = False
        self._thinking_started = False
        self._tool_call_started = False

    def feed(self, part: RawPart) -> None:
        part_type = part["type"]

        if part_type == "response_start":
            response_part = cast(ResponseStartPart, part)
            self._response_id = response_part["response_id"]
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            return

        if part_type == "text_delta":
            text_part = cast(TextDeltaPart, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            if not self._text_started:
                self._text_started = True
                content_index = self._ensure_content_block("text")
                self._stream.push(
                    cast(
                        TextStartEvent,
                        {
                            "type": "text_start",
                            "content_index": content_index,
                            "partial": self._build_partial_message(),
                        },
                    )
                )
            self._text_chunks.append(text_part["text"])
            self._stream.push(
                cast(
                    TextDeltaEvent,
                    {
                        "type": "text_delta",
                        "content_index": self._text_content_index(),
                        "delta": text_part["text"],
                        "partial": self._build_partial_message(),
                    },
                )
            )
            return

        if part_type == "text_signature_delta":
            text_signature_part = cast(TextSignatureDeltaPart, part)
            self._text_signature = text_signature_part["signature"]
            return

        if part_type == "thinking_delta":
            thinking_part = cast(ThinkingDeltaPart, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            if not self._thinking_started:
                self._thinking_started = True
                content_index = self._ensure_content_block("thinking")
                self._stream.push(
                    cast(
                        ThinkingStartEvent,
                        {
                            "type": "thinking_start",
                            "content_index": content_index,
                            "partial": self._build_partial_message(),
                        },
                    )
                )
            self._thinking_chunks.append(thinking_part["text"])
            self._stream.push(
                cast(
                    ThinkingDeltaEvent,
                    {
                        "type": "thinking_delta",
                        "content_index": self._thinking_content_index(),
                        "delta": thinking_part["text"],
                        "partial": self._build_partial_message(),
                    },
                )
            )
            return

        if part_type == "thinking_signature_delta":
            thinking_signature_part = cast(ThinkingSignatureDeltaPart, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            if not self._thinking_started:
                self._thinking_started = True
                content_index = self._ensure_content_block("thinking")
                self._stream.push(
                    cast(
                        ThinkingStartEvent,
                        {
                            "type": "thinking_start",
                            "content_index": content_index,
                            "partial": self._build_partial_message(),
                        },
                    )
                )
            self._thinking_signature_chunks.append(thinking_signature_part["signature"])
            return

        if part_type == "redacted_thinking":
            redacted_part = cast(RedactedThinkingPart, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            if not self._thinking_started:
                self._thinking_started = True
                content_index = self._ensure_content_block("thinking")
                self._stream.push(
                    cast(
                        ThinkingStartEvent,
                        {
                            "type": "thinking_start",
                            "content_index": content_index,
                            "partial": self._build_partial_message(),
                        },
                    )
                )
            if not self._thinking_chunks:
                self._thinking_chunks.append("[Reasoning redacted]")
            self._thinking_redacted = True
            self._thinking_signature_chunks = [redacted_part["signature"]]
            return

        if part_type == "tool_call_start":
            tool_call_start_part = cast(ToolCallStartPart, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            self._active_tool_call_id = tool_call_start_part["id"]
            self._active_tool_call_name = tool_call_start_part["name"]
            self._active_tool_call_args_chunks = []
            self._active_tool_call_thought_signature = None
            self._tool_call_started = True
            content_index = self._ensure_content_block(
                "tool", tool_call_start_part["id"]
            )
            self._stream.push(
                cast(
                    ToolCallStartEvent,
                    {
                        "type": "toolcall_start",
                        "content_index": content_index,
                        "partial": self._build_partial_message(),
                    },
                )
            )
            return

        if part_type == "tool_call_args_delta":
            tool_call_args_part = cast(ToolCallArgsDeltaPart, part)
            if (
                not self._tool_call_started
                or self._active_tool_call_id is None
                or self._active_tool_call_name is None
            ):
                raise RuntimeError("tool call delta received before tool call start")
            self._active_tool_call_args_chunks.append(tool_call_args_part["delta"])
            self._stream.push(
                cast(
                    ToolCallDeltaEvent,
                    {
                        "type": "toolcall_delta",
                        "content_index": self._toolcall_content_index(),
                        "delta": tool_call_args_part["delta"],
                        "partial": self._build_partial_message(),
                    },
                )
            )
            return

        if part_type == "tool_call_done":
            cast(ToolCallDonePart, part)
            if (
                not self._tool_call_started
                or self._active_tool_call_id is None
                or self._active_tool_call_name is None
            ):
                raise RuntimeError("tool call done received before tool call start")
            tool_call = self._build_active_tool_call()
            self._stream.push(
                cast(
                    ToolCallEndEvent,
                    {
                        "type": "toolcall_end",
                        "content_index": self._toolcall_content_index(),
                        "tool_call": tool_call,
                        "partial": self._build_partial_message(),
                    },
                )
            )
            self._tool_calls.append(tool_call)
            self._tool_calls_by_id[tool_call.id] = tool_call
            self._active_tool_call_id = None
            self._active_tool_call_name = None
            self._active_tool_call_args_chunks = []
            self._active_tool_call_thought_signature = None
            self._tool_call_started = False
            return

        if part_type == "tool_call_thought_signature":
            tool_call_signature_part = cast(ToolCallThoughtSignaturePart, part)
            if (
                self._tool_call_started
                and self._active_tool_call_id
                == tool_call_signature_part["tool_call_id"]
            ):
                self._active_tool_call_thought_signature = tool_call_signature_part[
                    "thought_signature"
                ]
                return
            for index, tool_call in enumerate(self._tool_calls):
                if tool_call.id == tool_call_signature_part["tool_call_id"]:
                    updated_tool_call = ToolCall(
                        type=tool_call.type,
                        id=tool_call.id,
                        name=tool_call.name,
                        arguments=tool_call.arguments,
                        thought_signature=tool_call_signature_part["thought_signature"],
                    )
                    self._tool_calls[index] = updated_tool_call
                    self._tool_calls_by_id[updated_tool_call.id] = updated_tool_call
                    return
            return

        if part_type == "image_part":
            image_part = cast(ImagePartRaw, part)
            if not self._started:
                self._stream.push(
                    cast(
                        StartEvent,
                        {"type": "start", "partial": self._build_partial_message()},
                    )
                )
                self._started = True
            image = ImagePart(
                type="image",
                data=image_part["data"],
                mime_type=image_part["mime_type"],
            )
            self._images.append(image)
            content_index = self._ensure_content_block(
                "image", str(len(self._images) - 1)
            )
            partial = self._build_partial_message()
            self._stream.push(
                cast(
                    ImageStartEvent,
                    {
                        "type": "image_start",
                        "content_index": content_index,
                        "partial": partial,
                    },
                )
            )
            self._stream.push(
                cast(
                    ImageEndEvent,
                    {
                        "type": "image_end",
                        "content_index": content_index,
                        "image": image,
                        "partial": partial,
                    },
                )
            )
            return

        if part_type == "usage_delta":
            usage_part = cast(UsageDeltaPart, part)
            input_tokens = usage_part.get("input", self._usage.input)
            output_tokens = usage_part.get("output", self._usage.output)
            cache_read_tokens = usage_part.get("cache_read", self._usage.cache_read)
            cache_write_tokens = usage_part.get("cache_write", self._usage.cache_write)
            derived_total_tokens = _derive_total_tokens(
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
            )
            total_tokens = usage_part.get("total_tokens", 0)
            if "total_tokens" not in usage_part or total_tokens <= 0:
                total_tokens = derived_total_tokens
            else:
                total_tokens = max(total_tokens, derived_total_tokens)
            self._usage = Usage(
                input=input_tokens,
                output=output_tokens,
                cache_read=cache_read_tokens,
                cache_write=cache_write_tokens,
                total_tokens=total_tokens,
                cost=self._usage.cost,
            )
            return

        if part_type == "usage_cost_multiplier":
            usage_multiplier_part = cast(UsageCostMultiplierPart, part)
            self._usage_cost_multiplier = float(usage_multiplier_part["multiplier"])
            return

        if part_type == "stop_reason":
            stop_reason_part = cast(StopReasonPart, part)
            self._stop_reason = stop_reason_part["stop_reason"]
            return

        if part_type == "response_done":
            cast(ResponseDonePart, part)
            self._finalize_usage_cost()
            for kind, _key in self._content_order:
                if kind == "text" and self._text_started:
                    self._stream.push(
                        cast(
                            TextEndEvent,
                            {
                                "type": "text_end",
                                "content_index": self._text_content_index(),
                                "content": "".join(self._text_chunks),
                                "partial": self._build_partial_message(),
                            },
                        )
                    )
                elif kind == "thinking" and self._thinking_started:
                    self._stream.push(
                        cast(
                            ThinkingEndEvent,
                            {
                                "type": "thinking_end",
                                "content_index": self._thinking_content_index(),
                                "content": "".join(self._thinking_chunks),
                                "partial": self._build_partial_message(),
                            },
                        )
                    )
            message = self._build_message(
                stop_reason=self._stop_reason, error_message=None
            )
            self._final_message = message
            self._stream.push(
                cast(
                    DoneEvent,
                    {
                        "type": "done",
                        "reason": _done_reason(self._stop_reason),
                        "message": message,
                    },
                )
            )
            return

        if part_type == "aborted":
            cast(AbortedPart, part)
            message = self._build_message(
                stop_reason="aborted", error_message="aborted"
            )
            self._final_message = message
            self._stream.push(
                cast(
                    ErrorEvent,
                    {"type": "error", "reason": "aborted", "error": message},
                )
            )
            return

        if part_type == "response_error":
            response_error_part = cast(ResponseErrorPart, part)
            message = self._build_message(
                stop_reason="error",
                error_message=response_error_part.get("message", "Unknown error"),
            )
            error_event: ErrorEvent = {
                "type": "error",
                "reason": "error",
                "error": message,
            }
            code = _http_status_code(response_error_part.get("code"))
            if code is not None:
                error_event["code"] = code
            self._final_message = message
            self._stream.push(error_event)
            return

        raise ValueError(f"Unsupported raw part type: {part_type}")

    def result_nowait(self) -> AssistantMessage:
        if self._final_message is None:
            raise RuntimeError("Raw assembler has not produced a final message yet")
        return self._final_message

    def _finalize_usage_cost(self) -> None:
        if self._pricing is None:
            return
        try:
            computed = calculate_usage_cost(
                self._pricing,
                self._usage,
                multiplier=self._usage_cost_multiplier,
            )
            if computed is None:
                return
            self._usage = Usage(
                input=self._usage.input,
                output=self._usage.output,
                cache_read=self._usage.cache_read,
                cache_write=self._usage.cache_write,
                total_tokens=self._usage.total_tokens,
                cost=computed,
            )
        except Exception:
            pass

    def _build_message(
        self, *, stop_reason: str, error_message: str | None
    ) -> AssistantMessage:
        return AssistantMessage(
            role="assistant",
            content=self._build_content(),
            api=self._api,
            provider=self._provider,
            model=self._model,
            response_id=self._response_id,
            usage=self._usage,
            stop_reason=_assistant_stop_reason(stop_reason),
            error_message=error_message,
            timestamp=0.0,
        )

    def _build_partial_message(self) -> AssistantMessage:
        return self._build_message(stop_reason=self._stop_reason, error_message=None)

    def _build_content(self) -> list[TextPart | ThinkingPart | ToolCall | ImagePart]:
        content: list[TextPart | ThinkingPart | ToolCall | ImagePart] = []
        for kind, key in self._content_order:
            if kind == "text" and self._has_text_content():
                content.append(
                    TextPart(
                        type="text",
                        text="".join(self._text_chunks),
                        text_signature=self._text_signature,
                    )
                )
            elif kind == "thinking" and self._has_thinking_content():
                thinking_signature = "".join(self._thinking_signature_chunks) or None
                content.append(
                    ThinkingPart(
                        type="thinking",
                        thinking="".join(self._thinking_chunks),
                        thinking_signature=thinking_signature,
                        redacted=self._thinking_redacted,
                    )
                )
            elif kind == "tool" and key is not None:
                tool_call = self._tool_calls_by_id.get(key)
                if tool_call is not None:
                    content.append(tool_call)
                elif key == self._active_tool_call_id and self._tool_call_started:
                    content.append(self._build_active_tool_call())
            elif kind == "image" and key is not None:
                image_index = int(key)
                if image_index < len(self._images):
                    content.append(self._images[image_index])
        return content

    def _build_active_tool_call(self) -> ToolCall:
        if self._active_tool_call_id is None or self._active_tool_call_name is None:
            raise RuntimeError("tool call has not started")
        return ToolCall(
            type="toolCall",
            id=self._active_tool_call_id,
            name=self._active_tool_call_name,
            arguments=self._parse_active_tool_call_arguments(),
            thought_signature=self._active_tool_call_thought_signature,
        )

    def _parse_active_tool_call_arguments(self) -> dict:
        raw = "".join(self._active_tool_call_args_chunks)
        return parse_streaming_json(raw)

    def _toolcall_content_index(self) -> int:
        if self._active_tool_call_id is None:
            return len(self._build_content()) - 1
        return self._content_block_index("tool", self._active_tool_call_id)

    def _text_content_index(self) -> int:
        return self._content_block_index("text")

    def _thinking_content_index(self) -> int:
        return self._content_block_index("thinking")

    def _image_content_index(self) -> int:
        return len(self._build_content()) - 1

    def _ensure_content_block(self, kind: str, key: str | None = None) -> int:
        marker = (kind, key)
        if marker not in self._content_order:
            self._content_order.append(marker)
        return self._content_block_index(kind, key)

    def _content_block_index(self, kind: str, key: str | None = None) -> int:
        marker = (kind, key)
        try:
            return self._content_order.index(marker)
        except ValueError as exc:
            raise RuntimeError(f"content block has not started: {kind}") from exc

    def _has_text_content(self) -> bool:
        return bool(self._text_started or self._text_chunks or self._text_signature)

    def _has_thinking_content(self) -> bool:
        return bool(
            self._thinking_started
            or self._thinking_chunks
            or self._thinking_signature_chunks
            or self._thinking_redacted
        )


def _http_status_code(value: object) -> int | None:
    if is_http_status_code(value):
        assert isinstance(value, int)
        return value
    return None


def _done_reason(stop_reason: str) -> str:
    if stop_reason in {"stop", "length", "toolUse"}:
        return stop_reason
    return "stop"


def _assistant_stop_reason(stop_reason: str) -> StopReason:
    if stop_reason in {"stop", "length", "toolUse", "error", "aborted"}:
        return cast(StopReason, stop_reason)
    return "stop"


def _derive_total_tokens(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> int:
    return input_tokens + output_tokens + cache_read_tokens + cache_write_tokens

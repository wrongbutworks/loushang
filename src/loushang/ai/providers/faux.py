from __future__ import annotations

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.options import is_reasoning_requested
from loushang.ai.provider import resolve_provider_request
from loushang.ai.types import TextPart, ToolResultMessage


class FauxProvider:
    api = "anthropic-messages"

    async def stream(self, model, context, options, request=None):
        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
        normalized = context
        stream = AssistantMessageEventStream()
        assembler = RawAssembler(
            stream=stream,
            api=resolved.api,
            provider=model.provider_id,
            model=model.id,
            pricing=getattr(model, "pricing", None),
        )
        assembler.feed({"type": "response_start", "response_id": "faux-response"})
        tool_result_text = self._extract_tool_result_text(
            normalized.get("messages", [])
        )
        if normalized.get("emit_thinking") or is_reasoning_requested(options):
            assembler.feed({"type": "thinking_delta", "text": "reasoning trace"})
        if normalized.get("emit_tool_call"):
            assembler.feed({"type": "tool_call_start", "id": "tc_1", "name": "calc"})
            assembler.feed({"type": "tool_call_args_delta", "delta": '{"x":1}'})
            assembler.feed({"type": "tool_call_done"})
        if normalized.get("emit_image"):
            assembler.feed(
                {"type": "image_part", "data": "aGVsbG8=", "mime_type": "image/png"}
            )
        if tool_result_text is not None:
            assembler.feed(
                {
                    "type": "text_delta",
                    "text": f"faux saw tool result: {tool_result_text}",
                }
            )
        else:
            assembler.feed(
                {"type": "text_delta", "text": "mock hello from faux provider"}
            )

        if normalized.get("abort_after_first_delta"):
            assembler.feed({"type": "aborted"})
            return stream

        assembler.feed({"type": "stop_reason", "stop_reason": "stop"})
        assembler.feed({"type": "response_done"})
        return stream

    def _extract_tool_result_text(self, messages: list[object]) -> str | None:
        for message in reversed(messages):
            if isinstance(message, ToolResultMessage):
                text_parts = [
                    part.text for part in message.content if isinstance(part, TextPart)
                ]
                if text_parts:
                    return "\n".join(text_parts)
                return "<non-text-tool-result>"
        return None

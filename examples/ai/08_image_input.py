"""Offline image input and image tool-result example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import (
    AssistantMessage,
    CallOptions,
    Context,
    ImagePart,
    Model,
    TextPart,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
    complete,
)
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry


class _ImageEchoProvider:
    api = "openai-responses"

    async def stream_raw(self, model, context, options, request):
        del model, options, request
        summary = _summarize_images(context.get("messages", []))
        yield {"type": "response_start", "response_id": "image-input-demo"}
        yield {"type": "text_delta", "text": json.dumps(summary, sort_keys=True)}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


async def inspect_image_input() -> dict[str, object]:
    model_registry = _build_model_registry()
    model = model_registry.get_model(
        "image-input-demo",
        "openai-responses",
        "image-input-demo",
    )
    registry = ApiProviderRegistry()
    registry.register_api_provider(_ImageEchoProvider())
    message = await complete(
        model,
        _build_context(),
        CallOptions(),
        registry=registry,
    )
    text = "".join(
        part.text for part in message.content if getattr(part, "type", None) == "text"
    )
    return json.loads(text)


def main() -> None:
    print(json.dumps(asyncio.run(inspect_image_input()), indent=2, sort_keys=True))


def _summarize_images(messages: list[object]) -> dict[str, object]:
    user_images = 0
    tool_result_images = 0
    tool_result_texts: list[str] = []
    for message in messages:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role == "user" and isinstance(content, list):
            user_images += sum(1 for part in content if isinstance(part, ImagePart))
        if role == "toolResult" and isinstance(content, list):
            tool_result_images += sum(
                1 for part in content if isinstance(part, ImagePart)
            )
            tool_result_texts.extend(
                part.text for part in content if isinstance(part, TextPart)
            )
    return {
        "userImages": user_images,
        "toolResultImages": tool_result_images,
        "toolResultText": "\n".join(tool_result_texts),
    }


def _build_context() -> Context:
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(
                type="toolCall",
                id="call_read_image",
                name="read_image",
                arguments={"path": "chart.png"},
            )
        ],
        api="openai-responses",
        provider="image-input-demo",
        model="image-input-demo",
        response_id="resp_1",
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost={},
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )
    return Context(
        messages=[
            UserMessage(
                role="user",
                content=[
                    TextPart(type="text", text="What does this image show?"),
                    ImagePart(
                        type="image", data="dXNlci1pbWFnZQ==", mime_type="image/png"
                    ),
                ],
                timestamp=0.0,
            ),
            assistant,
            ToolResultMessage(
                role="toolResult",
                tool_call_id="call_read_image",
                tool_name="read_image",
                content=[
                    TextPart(type="text", text="chart shows growth"),
                    ImagePart(
                        type="image", data="dG9vbC1pbWFnZQ==", mime_type="image/png"
                    ),
                ],
                is_error=False,
                timestamp=0.0,
            ),
        ]
    )


def _build_model() -> Model:
    return Model(
        id="image-input-demo",
        provider="image-input-demo",
        endpoint="openai-responses",
        capabilities=Capabilities(stream=True, input=("text", "image")),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        "image-input-demo",
        Endpoint(
            id="openai-responses",
            provider="image-input-demo",
            api="openai-responses",
            models={"image-input-demo": _build_model()},
        ),
    )
    return registry


if __name__ == "__main__":
    main()

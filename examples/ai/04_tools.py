"""Offline tool-call example."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable

from loushang.ai import (
    CallOptions,
    Model,
    TextPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    complete,
)
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.tool import validate_tool_arguments, validate_tool_arguments_result

PROVIDER_ID = "tool-demo"
ENDPOINT_ID = "anthropic-messages"
MODEL_ID = "tool-demo"
USER_PROMPT = "只调用工具，不要心算：使用 add 计算 78 + 35，并返回结果。"
MAX_TOKENS = 1024


class _ToolProvider:
    api = "anthropic-messages"

    async def stream_raw(self, model, context, options, request):
        del model, options, request
        tool_result_text = _extract_tool_result_text(context.get("messages", []))
        yield {"type": "response_start", "response_id": "tool-demo-response"}
        if tool_result_text is None:
            yield {"type": "tool_call_start", "id": "call_add", "name": "add"}
            yield {"type": "tool_call_args_delta", "delta": '{"a":78,"b":35}'}
            yield {"type": "tool_call_done"}
            yield {"type": "stop_reason", "stop_reason": "toolUse"}
        else:
            yield {
                "type": "text_delta",
                "text": f"工具返回 {tool_result_text}，所以答案是 {tool_result_text}。",
            }
            yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


def _extract_tool_result_text(messages: Iterable[object]) -> str | None:
    for message in reversed(list(messages)):
        if isinstance(message, ToolResultMessage):
            text_parts = [
                part.text for part in message.content if isinstance(part, TextPart)
            ]
            if text_parts:
                return "\n".join(text_parts)
            return "<non-text-tool-result>"
    return None


def _build_model() -> Model:
    return Model(
        id=MODEL_ID,
        provider=PROVIDER_ID,
        endpoint=ENDPOINT_ID,
        capabilities=Capabilities(stream=True, tool_use=True),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        PROVIDER_ID,
        Endpoint(
            id=ENDPOINT_ID,
            provider=PROVIDER_ID,
            api="anthropic-messages",
            models={MODEL_ID: _build_model()},
        ),
    )
    return registry


def _build_provider_registry() -> ApiProviderRegistry:
    registry = ApiProviderRegistry()
    registry.register_api_provider(_ToolProvider())
    return registry


def _add_tool() -> Tool:
    return Tool(
        name="add",
        description="Return the sum of two numbers a and b.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "first number"},
                "b": {"type": "number", "description": "second number"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )


def _tool_payload(tool: Tool) -> dict[str, object]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def _build_tools() -> list[dict[str, object]]:
    return [_tool_payload(_add_tool())]


def _inspect_tool_validation() -> dict[str, object]:
    tool = _add_tool()
    strict_call = ToolCall(
        type="toolCall",
        id="tc_strict",
        name="add",
        arguments={"a": 2, "b": 3},
    )
    coerce_call = ToolCall(
        type="toolCall",
        id="tc_coerce",
        name="add",
        arguments={"a": "2", "b": "3"},
    )

    strict_arguments = validate_tool_arguments(tool, strict_call)
    try:
        validate_tool_arguments(tool, coerce_call)
    except ValueError as error:
        strict_error = str(error).splitlines()[0]
    else:  # pragma: no cover - defensive example guard
        strict_error = ""

    coerce_result = validate_tool_arguments_result(
        tool,
        coerce_call,
        validation_policy="coerce",
    )
    return {
        "strict": strict_arguments,
        "strictError": strict_error,
        "coerce": coerce_result.arguments,
        "diagnostics": [
            {
                "code": diagnostic.code,
                "path": diagnostic.path,
                "fromType": diagnostic.from_type,
                "toType": diagnostic.to_type,
            }
            for diagnostic in coerce_result.diagnostics
        ],
    }


def _build_options() -> CallOptions:
    return CallOptions(max_output_tokens=MAX_TOKENS)


def _iter_text(parts: Iterable[object]) -> str:
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def inspect_tools() -> dict[str, object]:
    model = _build_model_registry().get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    tool = _add_tool()
    tools = [_tool_payload(tool)]
    registry = _build_provider_registry()

    first = await complete(
        model,
        {
            "system_prompt": "当需要外部计算时，请优先调用工具；收到工具结果后请用中文一句话回答。",
            "messages": [{"role": "user", "content": USER_PROMPT}],
            "tools": tools,
        },
        _build_options(),
        registry=registry,
    )

    tool_call = next(
        (part for part in first.content if getattr(part, "type", None) == "toolCall"),
        None,
    )
    if tool_call is None:
        raise RuntimeError("Provider did not emit a structured tool call.")

    args = validate_tool_arguments(tool, tool_call)
    result_text = str(args["a"] + args["b"])

    second = await complete(
        model,
        {
            "system_prompt": "你已经拿到工具结果，请用中文一句话给出最终答案。",
            "messages": [
                {"role": "user", "content": USER_PROMPT},
                first,
                ToolResultMessage(
                    role="toolResult",
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    content=[TextPart(type="text", text=result_text)],
                    is_error=False,
                    timestamp=0.0,
                ),
            ],
            "tools": tools,
        },
        _build_options(),
        registry=registry,
    )

    return {
        "toolCall": {
            "id": tool_call.id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        },
        "toolResult": result_text,
        "validation": _inspect_tool_validation(),
        "finalText": _iter_text(second.content),
    }


def main() -> None:
    print(json.dumps(asyncio.run(inspect_tools()), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

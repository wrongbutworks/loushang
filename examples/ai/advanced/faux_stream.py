"""高级示例：本地 faux provider 的流式协议演示。

适用场景：
- 调试统一事件流协议
- 不依赖真实厂商网络，直接观察 assembler 输出

不适合：
- 作为真实 provider 接入示例
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from loushang.ai import ApiProviderRegistry, Model, stream
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import get_default_model_registry
from loushang.ai.providers.faux import FauxProvider


def _build_model() -> Model:
    # faux 模型用于稳定产出多种事件，方便观察统一事件流协议。
    return Model(
        id="faux-model",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(stream=True, reasoning=True),
    )


def _register_model() -> None:
    # 这个示例依赖本地 faux 模型，因此需要先注册模型定义。
    get_default_model_registry().register_endpoint(
        "faux",
        Endpoint(
            id="anthropic-messages",
            provider="faux",
            api="anthropic-messages",
            models={"faux-model": _build_model()},
        ),
    )


def _build_context() -> dict:
    # faux provider 支持这些测试开关，用来稳定产出 thinking / tool / image 事件。
    return {
        "messages": [],
        "emit_thinking": True,
        "emit_tool_call": True,
        "emit_image": True,
    }


def _iter_text(parts: Iterable[object]) -> str:
    # 最终消息依然按公共 content 协议返回，这里只提取 text 片段。
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def _main() -> None:
    # 高级路径：手动注入 faux provider，而不是走 builtin provider。
    _register_model()
    registry = ApiProviderRegistry()
    registry.register_api_provider(FauxProvider())

    event_stream = await stream(
        _build_model(),
        _build_context(),
        registry=registry,
    )

    # 运行时可观察不同事件类型如何被统一协议表达。
    print("MODE faux-stream")
    async for event in event_stream:
        event_type = event["type"]
        if event_type == "text_delta":
            print(f"EVENT {event_type} delta={event['delta']!r}")
        elif event_type == "thinking_delta":
            part = event["partial"].content[event["content_index"]]
            print(f"EVENT {event_type} thinking={part.thinking!r}")
        elif event_type == "toolcall_delta":
            part = event["partial"].content[event["content_index"]]
            print(f"EVENT {event_type} args={part.arguments!r}")
        elif event_type == "image_end":
            print(f"EVENT {event_type} mime_type={event['image'].mime_type!r}")
        else:
            print(f"EVENT {event_type}")

    message = await event_stream.result()
    print(f"FINAL stop_reason={message.stop_reason!r}")
    print(f"FINAL text={_iter_text(message.content)!r}")


if __name__ == "__main__":
    asyncio.run(_main())

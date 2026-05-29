"""高级示例：形式化 Context 与 Tool 类型的最小演示。

这个示例主要用于说明：
- `Context` / `Tool` / `UserMessage` 这些显式类型如何组合
- 自定义 faux provider 时，如何在本地构造可运行示例

它不是第一次接入 `loushang.ai` 的推荐入口。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from loushang.ai import ApiProviderRegistry, Context, Model, Tool, UserMessage, stream
from loushang.ai.model import Endpoint
from loushang.ai.model.registry import get_default_model_registry
from loushang.ai.providers.faux import FauxProvider


def _build_model() -> Model:
    # 这个 faux 模型只用于演示正式类型对象如何参与调用，不代表真实线上模型。
    return Model(
        id="faux-model",
        provider="faux",
        endpoint="anthropic-messages",
    )


def _register_model() -> None:
    # 这个示例依赖本地 faux 模型，因此需要先把模型注册进默认模型目录。
    get_default_model_registry().register_endpoint(
        "faux",
        Endpoint(
            id="anthropic-messages",
            provider="faux",
            api="anthropic-messages",
            models={"faux-model": _build_model()},
        ),
    )


def _build_context() -> Context:
    # 这里刻意使用显式 Context / Tool / UserMessage 类型，
    # 用来演示正式类型对象如何构造，而不是走最短 dict 形式。
    return Context(
        system_prompt="You are a tool-using assistant.",
        messages=[UserMessage(role="user", content="Please solve this.", timestamp=0.0)],
        tools=[
            Tool(
                name="calc",
                description="Calculate numeric expressions",
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                    },
                    "required": ["expression"],
                },
            )
        ],
    )


def _iter_text(parts: Iterable[object]) -> str:
    # 把最终消息中的 text 片段拼接起来，便于终端输出。
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def _main() -> None:
    # 这是高级场景：本地注册 faux 模型并手动注入 faux provider。
    _register_model()
    registry = ApiProviderRegistry()
    registry.register_api_provider(FauxProvider())

    event_stream = await stream(
        _build_model(),
        _build_context(),
        registry=registry,
    )

    # 运行时主要观察 event 类型，确认 context 和 tools 已被正确消费。
    print("MODE context-tools-minimal")
    async for event in event_stream:
        print(f"EVENT {event['type']}")

    message = await event_stream.result()
    print(f"FINAL stop_reason={message.stop_reason!r}")
    print(f"FINAL text={_iter_text(message.content)!r}")


if __name__ == "__main__":
    asyncio.run(_main())

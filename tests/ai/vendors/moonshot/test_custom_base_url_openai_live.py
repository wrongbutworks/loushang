"""高级示例：全局覆盖 OpenAI-compatible provider 的 base URL。

适用场景：
- 代理网关
- 自建兼容端点
- 需要临时把 builtin OpenAI-compatible provider 指向别的地址

不适合：
- 第一次接入 `loushang.ai`
- 只想调用默认模型目录配置
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable

import pytest

from loushang.ai import get_model
from loushang.ai.advanced import OpenAICompletionsOptions
from loushang.ai.advanced.registry import reset_api_providers

# 用户可直接修改的配置。
# 这是高级示例；默认正式示例不需要覆盖 `BASE_URL`。
API_KEY = ""
BASE_URL = "https://api.moonshot.cn/v1"
MODEL_ID = "kimi-k2.5"
SYSTEM_PROMPT = "你是 Kimi，由 Moonshot AI 提供。回答要简洁、准确，优先使用中文。"
USER_PROMPT = "请用一句话介绍你自己。"
MAX_TOKENS = 256

PROVIDER_ID = "moonshot"
ENDPOINT_ID = "openai-completions"

pytestmark = [
    pytest.mark.live,
    pytest.mark.vendor_verification,
    pytest.mark.skipif(
        not (API_KEY or os.getenv("MOONSHOT_API_KEY")),
        reason="MOONSHOT_API_KEY not set; live Moonshot verification skipped",
    ),
]


def _resolve_api_key() -> str:
    # 即使覆盖了 base URL，认证入口仍然保持与主示例一致。
    value = API_KEY or os.getenv("MOONSHOT_API_KEY")
    if value:
        return value
    raise RuntimeError(
        "Set API_KEY at the top of this file, or export MOONSHOT_API_KEY."
    )


def _build_context() -> dict:
    # 这里故意保持普通 context 结构，用来突出“变化的只有 provider base URL”。
    return {
        "system_prompt": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": USER_PROMPT}],
    }


def _build_options(api_key: str) -> OpenAICompletionsOptions:
    # 仍然使用显式 api_key，避免把 base URL 覆盖与认证来源混在一起。
    return OpenAICompletionsOptions(api_key=api_key, max_tokens=MAX_TOKENS)


def _iter_text(parts: Iterable[object]) -> str:
    # 与主 complete 示例保持相同文本提取方式，便于对比差异只在 BASE_URL。
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def _main() -> None:
    api_key = _resolve_api_key()

    # 这里使用根包暴露的高级入口，而不是手动构造 registry。
    # 原因是这个场景本质上是“全局 provider 配置覆盖”，不是普通业务调用路径。
    reset_api_providers(openai_base_url=BASE_URL)
    try:
        model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
        message = await model.complete(
            _build_context(),
            _build_options(api_key),
        )
    finally:
        # 还原默认 provider registry，避免污染同进程内其他验证。
        reset_api_providers()

    # 运行后同时确认模型句柄与最终生效的 BASE_URL。
    print(f"MODEL {model.provider_id}:{model.endpoint_id}:{model.id}")
    print(f"BASE_URL {BASE_URL}")
    print(f"FINAL stop_reason={message.stop_reason!r}")
    print(f"FINAL response_id={message.response_id!r}")
    print(f"FINAL text={_iter_text(message.content)!r}")


def test_custom_base_url_openai_live() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - example path
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)

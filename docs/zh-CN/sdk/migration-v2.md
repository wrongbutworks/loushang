# AI SDK v2 迁移指南

[English](../../en/sdk/migration-v2.md) | 中文

本文说明从旧版 `loushang.ai` 包形态迁移到 v2 curated SDK surface 的方式，
覆盖 catalog、根包 API、错误语义和 provider 边界变化。

## 变化概览

v2 仍然把 `loushang.ai` 定位为底层模型调用包。它不负责 agent loop、会话、
UI、RAG、MCP 编排或产品级配置。

主要变化：

- 内置 catalog 切换为 `models.json`。
- 旧的完整 catalog 只作为审计归档保留。
- 普通应用代码优先从根包 `loushang.ai` 导入。
- provider registry 接线进入 advanced 边界；可选集成保留自己的 contrib options。
- 错误统一归一化为 `AIError` 子类和稳定 JSON-safe payload。
- core builtin adapter 是协议 adapter，不再按厂商横向堆 adapter。
- OpenAI Codex 移到显式 `loushang.ai.contrib.openai_codex` 注册路径。

## Catalog 迁移

### 旧内置 catalog

旧版代码可能依赖较大的内置 `models.json`，其中包含很多验证程度不一致的 provider
事实。

v2 运行时包数据使用 curated catalog：

```text
src/loushang/ai/model/models.json
```

旧完整 catalog 只保留为压缩审计归档：

```text
backup/ai/models-legacy-full.json.gz
```

这个归档只能用于检查或手工恢复数据，不应恢复到运行时包路径。

### 选择模型

用本地 `provider:endpoint:model` 三元组定位模型：

```python
from loushang.ai import get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
```

如果 provider 侧真实模型名不同于本地 model id，在自定义 catalog 中用
`upstreamId` 表达。Provider 发送请求时优先使用
`ResolvedRequest.upstream_model_id`，没有时回退到 `model.id`。

### 长尾 provider

本地部署、私有 endpoint 或长尾 provider 不应继续扩大内置 catalog。应加载自定义
schema v2 catalog：

```python
from loushang.ai.model import load_model_registry_from_file

registry = load_model_registry_from_file("local-models.json")
model = registry.get_model("local", "openai-completions", "my-model")
```

可运行参考：
[examples/ai/advanced/custom_catalog.py](../../../examples/ai/advanced/custom_catalog.py)。

## 根包 API 迁移

普通应用代码使用根包稳定导出：

```python
from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    StructuredOutputOptions,
    complete,
    complete_structured,
    get_model,
    list_models,
    stream,
)
```

旧的宽根包 surface 已收窄。下列名称不再作为根包导出：

| 旧访问方式 | v2 路径 |
|---|---|
| `loushang.ai.ModelCallOptions` | `loushang.ai.CallOptions` |
| `loushang.ai.StreamOptions` | `loushang.ai.CallOptions` |
| `loushang.ai.AnthropicOptions` | `loushang.ai.CallOptions` |
| `loushang.ai.OpenAICompletionsOptions` | `loushang.ai.CallOptions` |
| `loushang.ai.OpenAIResponsesOptions` | `loushang.ai.CallOptions` |
| `loushang.ai.ApiProviderRegistry` | `loushang.ai.advanced.registry.ApiProviderRegistry` |
| `loushang.ai.OpenAICodexResponsesOptions` | `loushang.ai.contrib.openai_codex.OpenAICodexResponsesOptions` |

普通调用优先使用 provider-neutral 的 `CallOptions`：

```python
from loushang.ai import CallOptions, complete, get_model

model = get_model("openai", "openai-responses", "gpt-5.4-mini")
message = await complete(
    model,
    {"messages": [{"role": "user", "content": "Say hello."}]},
    CallOptions(api_key="...", max_output_tokens=128),
)
```

core provider-specific option class 已移除。核心 provider 使用 `CallOptions`；
只有显式 contrib 集成继续使用自己的 contrib option class。

字段级替换：

| 旧 option 形状 | v2 替换方式 |
|---|---|
| `max_tokens` | `CallOptions(max_output_tokens=...)` |
| 数字 `timeout` | `CallOptions(timeout=TimeoutOptions(total_seconds=...))` |
| `retries` | `CallOptions(retry=RetryOptions(max_attempts=...))` |
| `max_retry_delay_ms` | `CallOptions(retry=RetryOptions(max_delay_seconds=...))` |
| 字符串 `reasoning` | `CallOptions(reasoning=ReasoningOptions(effort=...))` |
| `reasoning_summary` | `ReasoningOptions(expose_summary=True)` |
| provider hooks、`service_tier` 和 provider-only 控制项 | 不再是 core `CallOptions` 字段；迁移到 contrib 集成或 provider/runtime 配置 |

## 错误迁移

公共契约不再要求调用方捕获 provider SDK 异常。捕获 `AIError` 或其子类：

```python
from loushang.ai import AIError, CallOptions, complete

try:
    message = await complete(
        model,
        {"messages": [{"role": "user", "content": "hello"}]},
        CallOptions(api_key="..."),
    )
except AIError as error:
    payload = error.to_dict()
    print(payload["code"], payload["retryable"], payload["statusCode"])
```

稳定错误 payload 包含：

| 字段 | 含义 |
|---|---|
| `code` | 稳定 SDK 错误码，例如 `authentication`、`rate_limit`、`timeout`、`unsupported_capability` |
| `message` | 面向调用方的错误信息 |
| `source` | `loushang.ai`、`provider` 或产生错误的协议来源 |
| `retryable` | SDK 判断该失败是否适合重试 |
| `provider` / `endpoint` / `model` | 可用时的模型解析身份 |
| `statusCode` | provider 报告的 HTTP 状态码 |
| `requestId` | provider request id |
| `details` | JSON-safe 细节，credential 和 token 会脱敏 |

`complete()` 和 `event_stream.result()` 会对 terminal error event 抛 typed error。
retry 只会在产生可见输出前尝试。

## Provider 边界迁移

core builtin adapter 现在只保留协议级 adapter：

| Protocol API | Core adapter |
|---|---|
| `anthropic-messages` | `loushang.ai.providers.anthropic.AnthropicProvider` |
| `openai-completions` | `loushang.ai.providers.openai_completions.OpenAICompletionsProvider` |
| `openai-responses` | `loushang.ai.providers.openai_responses.OpenAIResponsesProvider` |

Azure OpenAI 和 Amazon Bedrock 不再是 v2 core adapter。若现有兼容协议足够，使用自定义
catalog；若需要专用逻辑，应在外部包或 contrib 中显式注册 adapter。

OpenAI Codex 是显式 contrib 集成：

```python
from loushang.ai import get_model
from loushang.ai.contrib.openai_codex import register_openai_codex_contrib

register_openai_codex_contrib()
model = get_model("openai-codex", "openai-codex-responses", "gpt-5.3-codex")
```

可运行参考：
[examples/ai/advanced/openai_codex_contrib.py](../../../examples/ai/advanced/openai_codex_contrib.py)。

## 迁移后验证

运行 AI 包使用的同一组 gate：

```bash
make check-ai
uv run pytest tests/examples/test_ai_examples.py -q
uv run python scripts/ai/check_catalog.py
uv run python scripts/ai/check_examples.py
uv run python scripts/ai/check_import_boundaries.py
```

live provider smoke 需要有效 provider credential，并应记录到对应 provider evidence 文件。
离线 gate 不能用来声称 live provider 兼容性已验证。

内部 release readiness 记录在
[Final Scorecard](../../internals/architecture/ai/final-scorecard.md)。

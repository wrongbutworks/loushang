# AI SDK

[English](../../en/sdk/) | 中文

`loushang.ai` 是用于模型调用的底层 Python SDK。它负责模型查询、
provider 请求归一化、消息、工具调用载荷、流式事件、认证材料解析、错误、
usage 和 provider adapter。它不负责 agent 编排、会话持久化、UI 行为或
coding 工具策略。

## 公开入口

普通应用代码优先使用根包：

```python
from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    StructuredOutputOptions,
    TextPart,
    ImagePart,
    Tool,
    ToolResultMessage,
    complete,
    complete_structured,
    get_model,
    list_models,
    stream,
)
```

只有进入高级边界时再使用子包：

- `loushang.ai.model`：自定义模型 catalog、registry 检查。
- `loushang.ai.auth`：OAuth credential 存储和 provider 登录辅助。
- `loushang.ai.advanced`：provider-specific options 和 registry 接线。
- `loushang.ai.contrib.openai_codex`：可选 OpenAI Codex 集成。

## 模型与 Catalog

内置 catalog 是 `models.json`。它刻意保持为小型 provider 集合，不再把归档的完整
legacy catalog 放在运行时包路径上。

模型用本地 `provider:endpoint:model` 三元组定位：

```python
from loushang.ai import get_model, list_models

for model in list_models(provider="moonshot", endpoint="openai-completions"):
    print(model.provider_id, model.endpoint_id, model.id)

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
```

运行 [examples/ai/11_provider_matrix.py](../../../examples/ai/11_provider_matrix.py)
或 [examples/ai/12_provider_smoke.py](../../../examples/ai/12_provider_smoke.py)
可以离线查看当前内置 provider 集合。

如果要从 legacy catalog 或旧的宽根包 API 迁移，请先阅读
[v2 迁移指南](./migration-v2.md)。

本地部署或长尾 provider 应通过 schema v2 自定义 catalog 接入，而不是扩大内置
catalog。参考
[examples/ai/advanced/custom_catalog.py](../../../examples/ai/advanced/custom_catalog.py)。
当 provider 侧真实模型名不同于本地模型 ID 时，自定义 catalog 可以写
`upstreamId`。

## 认证

常规路径是 API key。可以通过 `CallOptions` 显式传入，也可以使用 catalog
声明的 provider 环境变量。

```python
from loushang.ai import CallOptions, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
options = CallOptions(api_key="...", max_output_tokens=512)
```

如果没有传 `api_key`，`loushang.ai` 会根据 catalog 和环境变量解析认证材料。
curated provider 常用环境变量如下：

| Provider | 主要环境变量 |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `baidu-qianfan` | `QIANFAN_API_KEY`, `BAIDU_QIANFAN_API_KEY` |
| `dashscope` | `DASHSCOPE_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `minimax` | `MINIMAX_API_KEY` |
| `moonshot` | `MOONSHOT_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `stepfun` | `STEP_API_KEY`, `STEPFUN_API_KEY` |
| `tencent-hunyuan` | `HUNYUAN_API_KEY` |
| `volcano-ark` | `ARK_API_KEY` |
| `zai` | `ZAI_API_KEY` |

OAuth 能力位于 `loushang.ai.auth`，并由 `openai-codex` 这类显式 contrib 集成使用。
内置 curated API-key provider 路径不要求 OAuth。

## 完整返回调用

最短路径是先 `get_model(...)`，再调用 `model.complete(...)` 或根包
`complete(...)`。

```python
from loushang.ai import CallOptions, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
message = await model.complete(
    {"messages": [{"role": "user", "content": "用一句话打个招呼。"}]},
    CallOptions(api_key="...", max_output_tokens=128),
)

print(message.stop_reason)
print("".join(part.text for part in message.content if part.type == "text"))
```

可运行示例：[examples/ai/01_complete.py](../../../examples/ai/01_complete.py)。

## 流式输出

`stream(...)` 返回 `AssistantMessageEventStream`。先遍历事件，再调用
`result()` 取得最终 `AssistantMessage`。

```python
from loushang.ai import CallOptions, get_model, stream

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
events = await stream(
    model,
    {"messages": [{"role": "user", "content": "数到三。"}]},
    CallOptions(api_key="..."),
)

async for event in events:
    if event["type"] == "text_delta":
        print(event["delta"], end="")

message = await events.result()
```

可运行示例：[examples/ai/02_stream.py](../../../examples/ai/02_stream.py)。

## 工具

`loushang.ai` 定义工具 schema、校验工具参数、承载 tool-call part，并将工具载荷映射到
provider 协议。它不替调用方执行工具；调用方或 agent 层负责执行 `ToolCall`，再把
`ToolResultMessage` 送回模型上下文。

```python
from loushang.ai import Tool

tools = [
    Tool(
        name="add",
        description="Return the sum of two numbers.",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )
]
```

默认使用 strict 参数校验；只有需要修复用户或工具输入并读取 diagnostics 时，才使用
coerce 校验辅助。可运行示例：
[examples/ai/04_tools.py](../../../examples/ai/04_tools.py) 和
[examples/ai/05_parallel_tools.py](../../../examples/ai/05_parallel_tools.py)。

## Reasoning

当所选模型支持 reasoning 时，在 `CallOptions` 中传 `ReasoningOptions`。
resolver 会在 provider 调用前检查模型能力。

```python
from loushang.ai import CallOptions, ReasoningOptions

options = CallOptions(
    api_key="...",
    reasoning=ReasoningOptions(enabled=True, effort="medium", expose_summary=True),
)
```

如果只需要简单入口，`SimpleCallOptions(reasoning="medium")` 会映射到同一套内部
call options。可运行示例：
[examples/ai/06_reasoning.py](../../../examples/ai/06_reasoning.py)。

## Structured Output

使用 `StructuredOutputOptions` 和 `complete_structured(...)`。SDK 会在 provider
有稳定映射时请求结构化输出，并把最终 assistant 文本解析成 `StructuredOutputResult`。

```python
from loushang.ai import (
    CallOptions,
    StructuredOutputOptions,
    complete_structured,
    get_model,
)

model = get_model("openai", "openai-responses", "gpt-5.4-mini")
result = await complete_structured(
    model,
    {"messages": [{"role": "user", "content": "返回一个 city 和 score。"}]},
    StructuredOutputOptions(
        mode="json_schema",
        schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["city", "score"],
            "additionalProperties": False,
        },
    ),
    options=CallOptions(api_key="..."),
)

print(result.parsed)
```

可运行示例：
[examples/ai/07_structured_output.py](../../../examples/ai/07_structured_output.py)。

## Image

用户消息或工具结果消息可以携带 `ImagePart`。模型必须声明支持 image input；
不支持的 image 请求会在 provider 调用前失败。

```python
from loushang.ai import ImagePart, TextPart, UserMessage

context = {
    "messages": [
        UserMessage(
            role="user",
            content=[
                TextPart(type="text", text="描述这张图片。"),
                ImagePart(type="image", data=image_base64, mime_type="image/png"),
            ],
            timestamp=0.0,
        )
    ]
}
```

可运行示例：[examples/ai/08_image_input.py](../../../examples/ai/08_image_input.py)。

## 错误与重试

provider、校验、能力、超时、取消和流式失败会归一化为 `AIError` 子类。
`error.to_dict()` 返回稳定、JSON-safe 的错误载荷，并会脱敏凭证和 token。

```python
from loushang.ai import AIError, CallOptions, RetryOptions

try:
    message = await model.complete(
        {"messages": [{"role": "user", "content": "hello"}]},
        CallOptions(api_key="...", retry=RetryOptions(max_attempts=2)),
    )
except AIError as error:
    print(error.to_dict())
```

retry 只在尚未产生可见输出前是安全的。可运行示例：
[examples/ai/09_errors_retry.py](../../../examples/ai/09_errors_retry.py)。

## Usage 与成本

最终 `AssistantMessage.usage` 是 response 级别的 `UsageObservation`。当 catalog
没有可信 pricing 事实时，cost 为 `None`。

```python
usage = message.usage
print(usage.input, usage.output, usage.total_tokens, usage.cost)
```

账号或平台额度与单次 response usage 是不同概念。可运行示例：
[examples/ai/10_usage.py](../../../examples/ai/10_usage.py)、
[examples/ai/advanced/usage_online.py](../../../examples/ai/advanced/usage_online.py) 和
[examples/ai/advanced/platform_quota.py](../../../examples/ai/advanced/platform_quota.py)。

## 示例索引

建议阅读顺序：

1. [01_complete.py](../../../examples/ai/01_complete.py)
2. [02_stream.py](../../../examples/ai/02_stream.py)
3. [03_typed_context.py](../../../examples/ai/03_typed_context.py)
4. [04_tools.py](../../../examples/ai/04_tools.py)
5. [05_parallel_tools.py](../../../examples/ai/05_parallel_tools.py)
6. [06_reasoning.py](../../../examples/ai/06_reasoning.py)
7. [07_structured_output.py](../../../examples/ai/07_structured_output.py)
8. [08_image_input.py](../../../examples/ai/08_image_input.py)
9. [09_errors_retry.py](../../../examples/ai/09_errors_retry.py)
10. [10_usage.py](../../../examples/ai/10_usage.py)
11. [11_provider_matrix.py](../../../examples/ai/11_provider_matrix.py)
12. [12_provider_smoke.py](../../../examples/ai/12_provider_smoke.py)

高级示例位于 [examples/ai/advanced](../../../examples/ai/advanced/)。

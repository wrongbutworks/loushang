# `loushang.ai`

`loushang.ai` 是底层 AI SDK，不是 agent 编排层。

它当前负责：

- 模型领域定义与装载
- provider 请求解析与兼容性处理
- 统一的消息、工具、流式事件协议
- auth 解析
- 不同 provider 的具体调用实现

它当前不负责：

- agent 生命周期
- 会话管理与恢复
- 产品级配置聚合
- HTTP / RPC 服务层

整体分层参考 `pi-mono`，原则是少层次、职责直、不要把中间投影对象过度公开。

## 包结构

### `model/`

模型事实源与运行时索引。

- `domain.py`
  - 领域对象：`Provider`、`Endpoint`、`Model`
  - 配套对象：`Auth`、`Capabilities`、`Compat`、`Defaults`、`Pricing`
- `registry.py`
  - 运行时查询容器：`ModelRegistry`
  - 默认入口：`get_default_model_registry()`
- `loader.py`
  - 从内置 `models.json` 或显式文件/目录路径装载 registry
  - 显式文件、目录和外部 overlay 的 `*_with_diagnostics()` 变体返回 legacy `compat` 到类型化字段的 deprecation diagnostics；内置 catalog 自身的迁移 warning 不向普通装载调用暴露
- `models.json`
  - 内置模型事实源

当前 `model` 包的稳定心智是：

- `domain` 负责定义对象
- `registry` 负责组织和查询
- `loader` 只负责初始化装载

模型 ID 规则：

- catalog 中的 `provider`、`endpoint`、`model` 三段用于本地查询和 CLI 展示
- 上游模型 ID 如果包含 `:`，catalog 的公开 `model` ID 使用 `_` 替换 `:`
- 真实上游 ID 存在 `model.upstream_id`
- provider 解析层输出 `ResolvedRequest.upstream_model_id`
- provider adapter 发请求时使用 `ResolvedRequest.upstream_model_id`，没有该字段时使用 `model.id`

例如 OpenRouter 上游模型 `openai/gpt-oss-120b:free` 在本地写作 `openai/gpt-oss-120b_free`。

### `provider/`

统一 provider 边界层。

- `resolution.py`
  - 从 `Model + options` 解析 `ResolvedEndpoint` / `ResolvedRequest`
- `transforms.py`
  - 通用 provider payload helper
- `protocol.py`
  - `ApiProvider` 协议
- `carrier.py` / `transport.py` / `errors.py`
  - 通用运行时辅助

`provider/` 负责统一边界，不负责具体厂商实现。

### `providers/`

具体厂商适配层。

- `anthropic.py`
- `openai_completions.py`
- `openai_responses.py`
- `openai_codex_responses.py`
- `azure_openai_responses.py`
- `bedrock_converse.py`
- `faux.py`

这里负责真正发请求、消费 SDK、映射 raw stream events。

当前内置 provider family：

- OpenAI-compatible chat completions：`openai-completions`
- OpenAI Responses：`openai-responses`
- Anthropic Messages：`anthropic-messages`
- Azure OpenAI Responses：`azure-openai-responses`
- Amazon Bedrock Converse：`bedrock-converse-stream`

其中 Mistral、Google Gemini API、Google Vertex OpenAI-compatible、Cloudflare AI Gateway / Workers AI 通过现有 OpenAI-compatible 或 Anthropic Messages adapter 接入。Cloudflare 和 Vertex 的 `baseUrl` 可以包含 `{ENV_NAME}` 模板，运行时由 `provider.resolution` 从环境变量展开；缺少变量时直接报错。

### `context.py` 与 `messages.py`

这两层已经分开：

- `context.py`
  - 只负责 `Context` 形状整理
  - 提取 `system_prompt`
  - 规范化 `tools`
  - 产出公开的 `NormalizedContext` 不可变 snapshot，provider 只读取这个归一化边界
  - `normalize_context_result(...)` 返回 `NormalizationResult`，其中 diagnostics 会稳定报告 repair、downgrade 和 signature-removal
  - 默认使用 strict tool-call/tool-result pairing；缺失或孤立的 tool result 会直接报错
  - 历史兼容修复需要调用方显式传入 `pairing_mode="repair"`
  - `provider.invocation` 是 provider handoff 的最终归一化 guard；内置 adapter 不再二次 normalize
- `messages.py`
  - 负责消息规范化
  - 将输入 dict 一次性转换为 `UserMessage` / `AssistantMessage` / `ToolResultMessage`
  - 负责 user content canonicalize，adapter 不再读取 dict message/part fallback
  - 负责跨 provider assistant message 处理
  - diagnostic 顺序按 transcript path 稳定排序；同一路径内保留处理顺序

这个分法直接参考 `pi-mono` 的 `core/messages.ts` 思路。

### `event_stream/`

统一流式输出协议。

- `stream.py`
  - 通用 `EventStream`
  - `AssistantMessageEventStream`
- `assembler.py`
  - `RawAssembler`
  - 只负责 raw part -> event / message 拼装
- `raw_parts.py`
  - provider 到 assembler 的中间流协议

`assembler.py` 当前不再反查 model registry。pricing enrich 由 provider 传入 pricing 元信息后完成。

### `auth/`

认证与 OAuth 支持。

- `support.py`
  - auth merge
  - header material 解析
  - model auth resolve
- `facade.py`
  - OAuth provider 管理入口
- `registry.py`
  - OAuth provider registry
- `oauth.py` / `storage.py` / `types.py`
  - OAuth 具体支持

### 其它

- `api/`
  - `stream / complete / stream_simple / complete_simple`
- `api_registry.py`
  - API provider registry
- `pricing.py`
  - usage cost 计算
- `tool/`
  - tool schema、校验、provider-specific tool payload 转换
- `types.py`
  - 消息、usage、event 等基础协议
- `options.py`
  - options dataclass 定义

## 根包 API

根包 `loushang.ai` 是稳定 SDK 门面，只导出最常用的模型调用、模型访问、消息/事件类型和通用 options。
Provider 管理、provider-specific options、归一化诊断、pricing、tool transform 和 JSON repair 等能力必须从
对应子模块或 `loushang.ai.advanced` 进入。

主要导出分为：

### 调用入口

- `stream(...)`
- `complete(...)`
- `stream_simple(...)`
- `complete_simple(...)`
- `Model.stream(...)`
- `Model.complete(...)`
- `Model.stream_simple(...)`
- `Model.complete_simple(...)`

调用入口会在 Provider handoff 前校验已解析模型能力。`stream` 路径要求
`stream` capability；`tools`、reasoning、structured output、temperature、image
input 和 attachment 请求也会在模型未声明支持时直接失败。

通用调用参数使用 `CallOptions`。旧的 `ModelCallOptions`、`StreamOptions` 和
provider-specific options 仍保留在 `loushang.ai.options` / `loushang.ai.advanced` 作为兼容入口，
但不再属于根包稳定门面；新示例应优先使用 `CallOptions`。
`stream_simple` / `complete_simple` 使用更窄的 `SimpleCallOptions`；核心 API 会先
把 simple reasoning 选项映射为 `CallOptions.reasoning`，provider adapter 只需要
实现普通 `stream`。

### 模型访问

- `Model`
- `get_model(...)`
- `list_models(...)`

### 基础类型

- `Context`
- `Message`
- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`
- `Tool`
- `ToolCall`
- `TextPart`
- `ImagePart`
- `ThinkingPart`
- `Usage`
- `UsageCost`
- `StopReason`
- `AssistantMessageEvent`
- `AssistantMessageEventStream`

### 错误入口

- `AIError`
- `AIErrorCode`
- `AIErrorInfo`

`AIErrorInfo.to_dict()` 返回稳定、JSON-safe 的错误载荷，并递归脱敏
`Authorization`、API key、OAuth token、refresh token、secret、credential 等敏感字段。
完整异常层级位于 `loushang.ai.errors`；Provider 失败到 typed error 的迁移会在后续 runtime/error 工作包中完成。

### 通用 Options

- `CallOptions`
- `SimpleCallOptions`
- `ReasoningOptions`
- `RetryOptions`
- `TimeoutOptions`
- `ThinkingLevel`
- `ThinkingBudgets`

### Deprecation policy

本轮契约收敛把根包 `__all__` 视为稳定 API 快照。此前从根包导出的高级能力不再继续占用稳定门面：

- Provider registry 管理入口移到 `loushang.ai.advanced.registry`。
- Provider-specific options 只从 `loushang.ai.advanced` 或 `loushang.ai.options` 进入。
- Context normalization helper 从 `loushang.ai.context` 进入。
- Tool transform / validation 从 `loushang.ai.tool` 进入。
- Cost helper 从 `loushang.ai.pricing` 进入。
- Overflow 和 streaming JSON repair helper 从 `loushang.ai.utils` 进入。

### 子模块 helper

- `loushang.ai.context.normalize_context(...)`
  - returns the public `NormalizedContext` immutable mapping contract instead of a marker-tagged dict
  - accepts pi-style dict messages, including camelCase assistant/tool-result fields such as `toolCallId`, `thinkingSignature`, `thoughtSignature`, `mimeType`, and `stopReason`
- `loushang.ai.context.normalize_context_result(...)`
  - returns the same normalized context plus stable `NormalizationDiagnostic` entries for repairs, cross-provider downgrades, and provider-specific signature removal
  - defaults to strict tool-call/tool-result pairing; pass `pairing_mode="repair"` to synthesize missing tool results for legacy transcripts
  - consumers should treat `code`, `path`, and `level` as the stable machine-readable diagnostic contract; `message` is human-readable guidance
  - stable `NormalizationDiagnosticCode` values are `aborted_assistant_repaired`, `empty_thinking_dropped`, `error_assistant_dropped`, `missing_tool_result_repaired`, `redacted_thinking_dropped`, `text_signature_removed`, `thinking_downgraded_to_text`, `thinking_signature_removed`, `tool_call_id_normalized`, `tool_call_thought_signature_removed`, and `tool_result_id_normalized`
- `loushang.ai.tool.transform_messages(...)`
  - enforces strict tool-call/tool-result pairing by default
  - repairs missing tool results with synthetic error tool results only when `pairing_mode="repair"` is explicit
  - normalizes tool call ids for provider handoff and applies the same mapping to matching tool results
  - converts provider-specific thinking blocks to text and removes tool-call thought signatures when crossing provider API boundaries
- `loushang.ai.tool.to_openai_responses_tool_result_input(...)`
  - preserves image tool results as `input_image` blocks in function-call outputs
- `loushang.ai.tool.to_openai_completions_tool_result_message(...)`
  - degrades image-only tool results to the pi-style `(see attached image)` placeholder
- OpenAI concrete providers use the same placeholder when a tool result contains images but the target model cannot accept image input.
- OpenAI concrete providers remove unpaired Unicode surrogate code points from outgoing payload text, matching pi's provider JSON-safety behavior.
- Anthropic concrete provider applies the same outgoing text sanitization for system, user, assistant, thinking, and tool-result payload text.
- `loushang.ai.tool.validate_tool_call(...)`
- `loushang.ai.tool.validate_tool_arguments(...)`
- `loushang.ai.tool.normalize_tool_call_id_for_model(...)`
- `loushang.ai.pricing.calculate_cost(...)`
- `loushang.ai.pricing.models_are_equal(...)`

`calculate_cost(model, usage)` returns `None` when the model has no pricing
metadata, or when a used token component has no known price. Explicit zero
prices remain valid and produce a zero cost.

## Advanced API

以下能力建议从子包进入，不把它们当根包稳定边界：

### `loushang.ai.model`

- `ModelRegistry`
- `get_default_model_registry()`
- `Provider`
- `Endpoint`
- `Auth`
- `Capabilities`
- `Compat`
- `Defaults`
- `Pricing`

### `loushang.ai.advanced.registry`

- `ApiProviderRegistry`
- `register_api_provider(...)`
- `get_api_provider(...)`
- `list_api_providers()`
- `clear_api_providers()`
- `reset_api_providers(...)`
- `register_builtin_ai_providers(...)`

Custom providers registered through `ApiProviderRegistry` receive a canonical
`NormalizedContext`: user, assistant, and tool-result messages are dataclasses,
and tools are `Tool` dataclasses with validated dict parameters. Custom provider
code should use attribute access instead of dict-style message access.

### `loushang.ai.provider`

- `ResolvedEndpoint`
- `ResolvedRequest`
- `resolve_endpoint_for_model(...)`
- `resolve_request_for_model(...)`

### `loushang.ai.auth`

- `resolve_auth_material(...)`
- `resolve_auth_for_model(...)`
- OAuth provider 与 credential 相关接口

## 当前边界约定

### `Model`

`Model` 是上层直接持有和调用的句柄。

它当前承载：

- 基本标识：`id` / `provider` / `endpoint`
- 能力：`capabilities`
- 兼容项：`compat`
- 默认值：`defaults`
- 价格：`pricing`
  - `None` 表示价格未知；缺失的 price component 不会被当成 0

其中：

- `capabilities` 表示模型本体能力
- `defaults` 表示默认请求值
- `compat` 表示协议兼容项

`Model` 不再独立持有 `api` 事实。

稳定心智是：

- `Provider` 是服务提供方
- `Endpoint` 是 provider 暴露的具体调用入口
- `Model` 是该 endpoint 下的可调用模型句柄
- `api` 属于 `Endpoint`，不是 `Model`

因此：

- 一个 provider 可以有多个 endpoint
- 一个 endpoint 可以有多个 model
- 同一个模型名可以在多个 endpoint 下分别出现
- 每个 `Model` 只通过自己的 `endpoint` 被调用

运行时 provider 路由由 `endpoint.api` 决定。

例如：

- `moonshot:openai-completions:kimi-k2.5`
- `moonshot:openai-responses:kimi-k2.5`
- `moonshot:anthropic-messages:kimi-k2.5`

是三个不同的可调用 `Model` 句柄。

### `ResolvedRequest`

`ResolvedRequest` 是进入具体 provider 实现前的请求边界对象。

它负责把：

- `Model`
- runtime `options`
- auth / typed protocol/dialect / capabilities / defaults

收敛为 provider 侧可直接消费的请求解析结果。

它当前主要承载：

- `provider`
- `endpoint`
- `api`
- `base_url`
- `headers`
- `protocol`
- `dialect`
- `capabilities`
- `adapter_protocol`
- `adapter_dialect`
- `adapter_compat`
- `adapter_config`
- `defaults`
- `transport`
- `routing`
- `max_tokens`
- `reasoning_effort`
- `temperature`

AIQ-012 起，`ResolvedEndpoint` / `ResolvedRequest` 的推荐字段改为 typed
`protocol` / `dialect` / `capabilities` / `transport` / `routing`；构造参数
仍兼容接受 `compat`，但它只是已弃用的 `adapter_compat` 初始化别名。旧的
`.compat` 也只保留为只读、已弃用的 `adapter_compat` 读取别名。
`protocol` / `dialect` 只表达 catalog / programmatic
contract 中显式声明或由 legacy compat 迁移得到的事实；provider / base URL
推断出的 runtime heuristic 不会投射为 public contract。

provider adapter 侧的执行事实单独放在 `adapter_protocol` / `adapter_dialect` /
`adapter_compat` / `adapter_config`。其中 `adapter_config` 是
provider adapter 调用 `resolve_provider_request()` 时通过自己的 runtime config
resolver 生成或校验后的 provider 专有 typed runtime 配置，承载无法放入通用
protocol/dialect 的执行参数；具体配置类型由对应 provider 模块拥有。手写
`ResolvedRequest` 时，如果同时提供 `adapter_compat` 和 provider-specific
`adapter_config`，二者必须在该 provider 的 runtime key 上投影一致；冲突会在
resolution 边界报错。无关 compat key 不参与
`adapter_config` 一致性检查。`adapter_compat` 是核心 adapter 迁移完成前的内部
桥接字段，provider adapter 新代码应依赖 typed `adapter_protocol` /
`adapter_dialect` / `adapter_config`，不要读取 raw compat。

## 最小调用链

最简单的调用方式是直接从 `Model` 实例发起：

```python
from loushang.ai import get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.5")

message = await model.complete(
    {
        "messages": [
            {"role": "user", "content": "用一句话介绍 loushang.ai"}
        ]
    }
)
```

也可以继续使用顶层函数：

```python
from loushang.ai import complete, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.5")
message = await complete(model, {"messages": [{"role": "user", "content": "hi"}]})
```

默认情况下，调用入口会自动使用默认 provider registry，并在首次调用时自动注册内置 providers。

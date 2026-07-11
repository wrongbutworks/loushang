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
  - 配套对象：`Auth`、`Capabilities`、`Defaults`、`Pricing`、三类 `AdapterConfig`
- `registry.py`
  - 装载后只读的运行时查询容器：`ModelRegistry`
  - 默认入口：`get_default_model_registry()`
- `loader.py`
  - 从内置 `models.json` 或显式文件/目录路径一次性构造 registry
- `models.json`
  - 内置模型事实源；完整 legacy catalog 已备份到 `backup/ai/models-legacy-full.json.gz`

当前 `model` 包的稳定心智是：

- `domain` 负责定义对象
- `registry` 负责组织和查询
- `loader` 只负责初始化装载

模型 ID 规则：

- catalog 中的 `provider`、`endpoint`、`model` 三段用于本地查询和诊断展示
- 自定义 catalog 可以用 `upstreamId` 记录与本地 model ID 不同的真实上游模型 ID
- 真实上游 ID 存在 `model.upstream_id`
- provider 解析层输出 `ProviderRequest.upstream_model_id`
- provider adapter 发请求时使用 `ProviderRequest.upstream_model_id`，没有该字段时使用 `model.id`

内置 curated catalog 当前不依赖 `upstreamId`；长尾 provider 或带特殊上游 ID 的模型应通过外部自定义 catalog 加入。

### `provider/`

统一 provider 边界层。

- `resolution.py`
  - 从 `Model + context + options` 解析 `ProviderRequest`
- `protocol.py`
  - `ApiProvider` 协议
- `runtime.py` / `invocation.py`
  - 统一 provider 调用、重试、取消、raw stream 组装入口
- `cancellation.py` / `output_budget.py` / `errors.py`
  - 通用运行时辅助

`provider/` 负责统一边界，不负责具体厂商实现。

### `providers/`

核心协议适配层。

- `anthropic.py`
- `openai_completions.py`
- `openai_responses.py`
- `faux.py`

这里负责真正发请求、消费 SDK、映射 raw stream events。

当前内置 provider family：

- OpenAI-compatible chat completions：`openai-completions`
- OpenAI Responses：`openai-responses`
- Anthropic Messages：`anthropic-messages`

内置 curated model catalog 只发布当前维护的小型 provider 集。Mistral、Google Gemini API、Google Vertex OpenAI-compatible、Cloudflare AI Gateway / Workers AI 等长尾接入不在默认 catalog 中；需要时应通过自定义模型文件或外部包复用现有 OpenAI-compatible / Anthropic Messages adapter 边界。外部 catalog 的 `baseUrl` 可以包含 `{ENV_NAME}` 模板，运行时由 `provider.resolution` 从环境变量展开；缺少变量时直接报错。

核心 adapter 集合由 `docs/internals/architecture/ai/core-provider-adapter-contract-matrix.md`
锁定。产品或账号场景必须优先通过 catalog 数据复用这些协议 adapter，不能增加产品专用
provider。ChatGPT Coding Plan 路径使用
`openai:openai-responses-chatgpt:gpt-5.5-chatgpt`，其上游模型 ID 是 `gpt-5.5`，
`api` 仍是 `openai-responses`。

Azure OpenAI Responses 不再作为 core adapter 发布；需要 Azure 私有部署时，
请使用自定义 catalog 和通用 OpenAI-compatible 协议边界，或在外部包中注册专用 adapter。
Amazon Bedrock Converse 不再作为 core adapter 发布；本包不再声明 Bedrock stream 支持。

### `context.py` 与 `messages.py`

这两层已经分开：

- `context.py`
  - 只负责 `Context` 形状整理
  - 提取 `system_prompt`
  - 规范化 `tools`
  - 产出公开的 `NormalizedContext` frozen dataclass boundary，provider 只读取这个归一化边界
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

request-level 认证解析。

core auth 只负责把本次调用的认证材料解析为 provider request headers。
`models.json.auth` 声明缺省 API-key 行为；`CallOptions.oauth_credentials` 接收调用方
已经通过 `loushang.auth` 取得的单个 `OAuthCredentials`，本次请求需要的附加认证头通过
`CallOptions.headers` 传入。OAuth 登录、refresh、credential store、账号选择、quota、
billing 和产品级认证策略不属于 `loushang.ai`。

- `support.py`
  - auth merge
  - request auth resolve
  - `models.json.auth` default resolve
- `credentials.py`
  - 保留现有调用方使用的 request-level `CallOptions.auth` 输入类型
  - 不包含 login、refresh 或 credential store 行为；新调用应使用明确的
    `api_key` / `oauth_credentials` / `headers` 字段

### 其它

- `api/`
  - `stream / complete / complete_structured`
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
Provider 管理、归一化诊断、pricing、tool transform 和 JSON repair 等能力必须从
对应子模块进入。

主要导出分为：

### 调用入口

- `stream(...)`
- `complete(...)`
- `complete_structured(...)`

调用入口会在 Provider handoff 前校验已解析模型能力。`stream` 路径要求
`stream` capability；`tools`、reasoning、structured output、temperature、image
input 和 attachment 请求也会在模型未声明支持时直接失败。

通用调用参数使用 `CallOptions`。核心 provider 不再有 provider-specific option
class；普通调用只通过 `CallOptions`、`ReasoningOptions`、`RetryOptions` 和
`TimeoutOptions` 这组根包契约表达。

`CallOptions.cache_key` 是调用方提供的、不透明且在相关请求之间稳定的缓存/亲和键。
协议 adapter 可以把它映射为上游 `prompt_cache_key`、真实 `session_id` header、
client-request 或 affinity header，但 AI 包不把它解释成 session，也不据此恢复
历史消息。`cache_retention="none"` 时不发送由该键派生的字段。

`CallOptions` 不承载 provider、endpoint、model、region、fallback 或 routing 选择。
这些事实必须在调用 `complete()` / `stream()` 前由具体 `Model` 确定。

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
完整异常层级位于 `loushang.ai.errors`；provider adapter 失败会在 runtime 边界归一化为
稳定的 `AIErrorInfo` / `response_error` 语义，保留 HTTP status、source 和 retryable
判断。

### 通用 Options

- `CallOptions`
- `ReasoningOptions`
- `RetryOptions`
- `StructuredOutputOptions`
- `StructuredOutputResult`
- `TimeoutOptions`
- `ThinkingLevel`

### Deprecation policy

本轮契约收敛把根包 `__all__` 视为稳定 API 快照。此前从根包导出的高级能力不再继续占用稳定门面：

- Provider registry 管理入口移到 `loushang.ai.advanced.registry`。
- AI CLI 和产品专用的 OpenAI Codex contrib 已删除；产品场景通过 catalog 复用协议
  adapter。现有调用方依赖的 Moonshot quota helper 暂保留在 legacy contrib 路径。
- Context normalization helper 从 `loushang.ai.context` 进入。
- Tool transform / validation 从 `loushang.ai.tool` 进入。
- Cost helper 从 `loushang.ai.pricing` 进入。
- Account、billing 和 platform quota 不属于 `loushang.ai` core architecture
  边界；core `loushang.ai.usage` 只保留 response usage payload helper。
- Overflow 和 streaming JSON repair helper 从 `loushang.ai.utils` 进入。

### 子模块 helper

- `loushang.ai.context.normalize_context(...)`
  - returns the public `NormalizedContext` frozen dataclass contract with attribute access
  - freezes the context shell and message/tool tuples; it does not deep-freeze
    nested message content or tool parameter schemas
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
- Built-in model modalities are limited to implemented `text` and `image` declarations. Image input and image tool-result feedback are supported through provider-native payloads when the resolved model supports image input; unsupported image tool-result feedback degrades to the stable `(see attached image)` placeholder.
- `loushang.ai.tool.validate_tool_call(...)`
- `loushang.ai.tool.validate_tool_arguments(...)`
- `loushang.ai.tool.validate_tool_call_result(...)`
- `loushang.ai.tool.validate_tool_arguments_result(...)`
  - tool argument validation defaults to `validation_policy="strict"` and never performs implicit type conversion
  - pass `validation_policy="coerce"` only for legacy-compatible paths that need audited primitive conversions; the result helpers return `ToolValidationDiagnostic` entries with `code`, `path`, `from_type`, `to_type`, and `level`
  - the enforced JSON Schema subset is: `type`, `properties`, `required`, `additionalProperties`, `items`, `prefixItems`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `enum`, `oneOf`, `anyOf`, and `allOf`
  - unsupported JSON Schema keywords are not enforced by this lightweight helper
- `loushang.ai.tool.normalize_tool_call_id_for_model(...)`
- `loushang.ai.pricing.calculate_cost(...)`
- `loushang.ai.pricing.models_are_equal(...)`
- `loushang.ai.usage_from_message(...)`
- `loushang.ai.usage_payload(...)`
- `loushang.ai.complete_structured(model, context, output, options=...)`
  - sends `StructuredOutputOptions` through provider-native structured output payloads where the adapter has a stable mapping
  - returns `StructuredOutputResult(raw=AssistantMessage, parsed=...)`
  - `mode="json_object"` parses the assistant text as a JSON object
  - `mode="json_schema"` accepts a JSON Schema mapping or a Pydantic-like type with `model_json_schema()` and `model_validate(...)`
  - unsupported adapter mappings fail before provider invocation instead of silently ignoring the structured output request

`calculate_cost(model, usage)` returns `None` when the model has no pricing
metadata, or when a used token component has no known price. Explicit zero
prices remain valid and produce a zero cost.

`Usage` is response-level accounting produced by model response events. Provider
account quota, billing, entitlement, and account control-plane helpers live
outside the `loushang.ai` core architecture boundary and must not be treated as
auth or usage responsibilities.

## Advanced API

以下能力建议从子包进入，不把它们当根包稳定边界：

### `loushang.ai.model`

- `ModelRegistry`
- `get_default_model_registry()`
- `load_model_registry_from_file(...)`
- `load_model_registry_from_directory(...)`
- `Provider`
- `Endpoint`
- `Auth`
- `Capabilities`
- `OpenAICompletionsConfig`
- `OpenAIResponsesConfig`
- `AnthropicMessagesConfig`
- `Defaults`
- `Pricing`

`ModelRegistry` 在 loader 构造完成后只提供查询，不提供运行期 catalog mutation。
默认 builtin + user directory 的 layered 装配是内部策略；高级调用方只使用明确的
file/directory loader。

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
code should use attribute access instead of dict-style message access. The
boundary is canonical provider input, not a deep immutable clone of all nested
values. Providers with provider-specific adapter config can also implement the
optional `ProviderRequestValidator` protocol; `validate_request(request)` runs
after core request normalization and before `invoke_raw(request)`.

### `loushang.ai.provider`

- `ProviderRequest`
- `ProviderRequestValidator`
- `resolve_endpoint_for_model(...)`
- `resolve_request_for_model(...)`

### OAuth 调用输入

- `loushang.auth.OAuthCredentials`
- `CallOptions.oauth_credentials`
- `CallOptions.headers`

`OAuthCredentials` 表示调用方已经取得的 credential；request-specific headers 不扩展
credential DTO，而是通过 `CallOptions.headers` 传入。AI 包不读取 credential store，
也不登录或刷新 token。完整真实调用见
[`examples/ai/chatgpt_coding_plan.py`](../../../examples/ai/chatgpt_coding_plan.py)。

## 当前边界约定

### `Model`

`Model` 是上层持有的 concrete/effective 模型句柄。

它当前承载：

- 基本标识：`id` / `provider` / `endpoint`
- 有效调用入口：`api` / `base_url` / `base_url_env`
- 能力：`capabilities`
- 适配配置：`adapter`
- 默认值：`defaults`
- 价格：`pricing`
  - `None` 表示价格未知；缺失的 price component 不会被当成 0

其中：

- `capabilities` 表示模型本体能力
- `adapter` 表示当前外部 API 协议的最小适配配置
- `defaults` 表示默认请求值

Registry 返回的 `Model` 会带上继承后的 endpoint 调用事实。

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

运行时 provider dispatch 由模型继承后的 `api` 决定。`complete()` 和 `stream()`
不会查询 registry、切换 preferred endpoint、读取 `LOUSHANG_REGION`、根据 region
改选 endpoint 或执行 fallback。

例如 `moonshot:openai-completions:kimi-k2.6` 是一个可调用 `Model` 句柄。
如果同一个上游模型通过多个 endpoint 暴露，catalog 仍会把它们表达为不同的
`provider:endpoint:model` 句柄。

### `ProviderRequest`

`ProviderRequest` 是进入具体 provider 实现前的请求边界对象。

它负责把：

- `Model`
- normalized `context`
- runtime `options`
- auth / adapter config / capabilities / defaults

收敛为 provider 侧可直接消费的单一请求对象。

`model: Model` 是必填字段，并且保持为本次实际调用的同一个 effective model 对象。
request 的 `provider`、`endpoint`、`api`、`region`、`capabilities`、`defaults`、
`adapter_config`、`transport`、`routing`、`upstream_model_id` 和 `base_url` 都从这一个
model 派生，不允许拼接 caller model 与另一个 endpoint model 的事实。

它当前主要承载：

- `provider`
- `endpoint`
- `api`
- `base_url`
- `headers`
- `capabilities`
- `adapter_config`
- `defaults`
- `transport`
- `routing`
- `max_tokens`
- `reasoning_effort`
  - `temperature`

`resolve_request_for_model()` 只解析已选模型的 base URL 环境变量、auth 和单次调用
参数，不承担 catalog/model selection。缺少 provider、endpoint 或 `api` 的 unbound
model 会在 provider 调用前失败。

冻结后的 request resolution 只携带一份 `adapter_config`。核心 provider 使用
`OpenAICompletionsConfig`、`OpenAIResponsesConfig`、`AnthropicMessagesConfig`
三类配置；非核心 provider 可以实现可选 `ProviderRequestValidator`，在
`validate_request(request)` 中生成或校验 provider 专有配置。catalog 只声明
`adapter`，resolution 不再保留历史字段迁移层。

## 最小调用链

最简单的调用方式是用 `get_model(...)` 取得模型句柄，再调用根包函数：

```python
from loushang.ai import complete, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")

message = await complete(
    model,
    {
        "messages": [
            {"role": "user", "content": "用一句话介绍 loushang.ai"}
        ]
    }
)
```

这里的 `get_model(provider, endpoint, model_id)` 已经在 invocation 前精确确定调用
路径。endpoint 的 `region` 只作为 catalog/model metadata 保留。

流式调用同样使用根包函数：

```python
from loushang.ai import get_model, stream

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
events = await stream(model, {"messages": [{"role": "user", "content": "hi"}]})
```

默认情况下，调用入口会自动使用默认 provider registry，并在首次调用时自动注册内置 providers。

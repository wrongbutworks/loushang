# Loushang-AI Architecture

## Current Design

说明：

- 本目录同时包含当前架构说明、历史设计草案、验证记录。
- 名称里带 `V1`、`round-1`、`blueprint`、`validation` 的文档，很多是阶段性方案，不一定代表当前代码事实。
- 当前代码事实优先参考 [`src/loushang/ai/README.md`](../../../../src/loushang/ai/README.md) 与本页后半部分。

- [Loushang-AI ARD List](./ARD-list.md)
- [ARD-001: Async Public Streaming Surface](./ARD-001-async-public-streaming-surface.md)
- [Loushang AI Quality Hardening Charter](../../plans/2026-06-20-loushang-ai-quality-hardening-charter.md)
- [Loushang-AI Adaptability NFR](./loushang-ai-adaptability-NFR.md)
- [Loushang-AI Adaptability Design V1](./loushang-ai-adaptability-design-v1.md)
  - 已补充 `code plan` / `codex-like` 账号态认证接入约束、resolved auth view 约束与 `loushang-ai` 边界说明
- [Loushang-AI Legacy Model Design Note](./loushang-ai-model-catalog-design-v1.md)
- [Loushang AI System Context](./loushang-ai-system-context.md)
- [Loushang AI Physical System Context](./loushang-ai-physical-system-context.md)
- [Loushang AI ApiProvider Registry](./loushang-ai-api-provider-registry.md)
- [Loushang AI Provider Adapter Strategy](./loushang-ai-provider-adapter-strategy.md)
- [Loushang AI OpenAI-Compatible Compat](./loushang-ai-openai-compat.md)
- [Loushang AI Top-Level API Signatures](./loushang-ai-top-level-api-signatures.md)
- [Loushang AI Streaming and Cancellation](./loushang-ai-streaming-and-cancellation.md)
- [Loushang AI Raw Part Design V1](./loushang-ai-raw-part-design-v1.md)
- [Loushang AI Streaming Semantics](./loushang-ai-streaming-semantics.md)
- [Loushang AI Record & Replay](./loushang-ai-stream-record-replay.md)

## Whitebox Design

- [Loushang Design Method: Identify Component](../loushang-design-method-identify-component.md)
- [Loushang-AI Whitebox Candidate Functions](./loushang-ai-whitebox-candidate-functions.md)
- [Loushang-AI Whitebox Candidate Components](./loushang-ai-whitebox-candidate-components.md)
- [Loushang-AI Function To Component Mapping](./loushang-ai-function-component-mapping.md)
- [Loushang-AI Component Refinement Round 1](./loushang-ai-component-refinement-round-1.md)
- [Loushang-AI Component Structure V1](./loushang-ai-component-structure-v1.md)
- [Loushang-AI Component Interfaces V1](./loushang-ai-component-interfaces-v1.md)
- [Loushang-AI Component Interactions V1](./loushang-ai-component-interactions-v1.md)

## Validation

- [Loushang AI Streaming Validation](./validation/loushang-ai-streaming-validation.md)
- [Loushang AI Provider Adapter Validation](./validation/loushang-ai-provider-adapter-validation.md)
- [Loushang AI Implementation Status Round 1](./validation/loushang-ai-implementation-status-round-1.md)
- [Loushang AI Gap vs Reference AI SDK Round 1](./validation/loushang-ai-gap-vs-reference-ai-sdk-round-1.md)

## Observability

- [Loushang-AI Trace Events](./loushang-ai-trace-events.md)
  - 支持 transport/sessionId/ws 复用/回退(fallback)/自动重连(reconnect)/attempt/错误分类 等事件

## CLI

- 设计文档见《[Loushang-AI CLI](./loushang-ai-cli.md)》
- 运行方式：
  - `uv run python -m loushang.ai.cli --help`
  - 示例：`uv run python -m loushang.ai.cli models list`
  - 示例：`uv run python -m loushang.ai.cli chat --model kimi-k2.5 --message "你好" --json`

## Utils

- Context Overflow Detection
  - `from loushang.ai.utils import is_context_overflow`
  - 用法：`is_context_overflow(message, context_window=cap.context_window)`
  - 说明：匹配多厂商错误文案；对静默溢出，基于 usage.input 与 context_window 比较
## Current Code Domains

- `src/loushang/ai/api/`
- `src/loushang/ai/model/`
- `src/loushang/ai/provider/`
- `src/loushang/ai/auth/`
- `src/loushang/ai/event_stream/`
- `src/loushang/ai/tool/`
- `src/loushang/ai/providers/`
- `src/loushang/ai/messages.py`
- `src/loushang/ai/context.py`
- `src/loushang/ai/pricing.py`

当前 `model/` 组件已包含：

- `models.json`
- `domain.py`
- `loader.py`
- `registry.py`

当前分工：

- `model/`
  - 领域对象、registry、装载
- `provider/`
  - 统一 provider 边界、请求解析、payload helper
- `providers/`
  - 各厂商具体适配实现
- `messages.py`
  - 消息规范化与 user content canonicalization
- `context.py`
  - `Context` 形状整理
- `event_stream/`
  - raw part 与统一流式事件组装
- `pricing.py`
  - usage/cost 计算

## Current Public API

当前 `loushang.ai` 对外 public surface 可分成以下几组：

- `Invocation API`
  - `stream`
  - `complete`
  - `stream_simple`
  - `complete_simple`
- `AI Input Semantics`
  - `Context`
  - `Message`
  - `Tool`
- `Model Access API`
  - `get_model`
  - `list_models`
  - `get_providers`
  - `find_model(...)` 当前仅存在于 `ModelRegistry`，不属于根包 `loushang.ai` public surface
- `Provider Registry API`
  - `register_api_provider`
  - `get_api_provider`
  - `list_api_providers`
  - `clear_api_providers`
- `Bootstrap API`
  - `reset_api_providers`
  - `register_builtin_ai_providers`
- `Option Types`
  - `StreamOptions`
  - `SimpleStreamOptions`
  - `AnthropicOptions`
  - `OpenAICompletionsOptions`
  - `OpenAIResponsesOptions`
  - `OpenAICodexResponsesOptions`
  - `ThinkingLevel`
  - `ThinkingBudgets`
  - `CacheRetention`
  - `Transport`
- `Auth Helper API`
  - 当前仍未正式对外补齐
  - 只在系统环境图与适应性设计中保留为下一阶段入口
- `Advanced Subpackages`
  - `loushang.ai.provider`
  - `loushang.ai.auth`
  - `loushang.ai.event_stream`

当前内部状态补充：

- `ModelRegistry` 装载已支持：
  - built-in `models.json`
- `Auth Support` 已接入 provider 主链
  - provider / endpoint / model 级 auth config 会参与请求头解析
- `Provider Boundary Support` 已开始接入 provider 主链
  - provider 现在可从 endpoint config 读取 `baseUrl`
  - endpoint `defaults` 已可进入 provider payload
  - `openai-completions` / `openai-responses` 现可从 endpoint `compat/defaults` 吸收
    - `reasoningEffort`
    - `maxOutputTokens`
    - `temperature`
  - `OpenAIResponsesOptions` 现还可直接进入 payload
    - `reasoning_summary`
    - `service_tier`
- `openai-completions` 现还可按 endpoint compat 吸收
  - `supportsUsageInStreaming`
  - `maxTokensField`
  - `requiresAssistantAfterToolResult`
  - `requiresToolResultName`
  - `supportsDeveloperRole`
  - `anthropic-messages` 现已在输入侧支持将连续的 `ToolResultMessage` 合并为单个 `user` 消息块（与 Anthropic 协议对齐），并已加入回归测试
  - OpenAI-compatible provider 现共用一层 provider-boundary request 解析
  - `anthropic-messages` 现也共用同一层 request 解析
    - `maxTokens`
  - `AnthropicOptions` 现已开始进入 payload
    - `thinking_enabled`
    - `thinking_budget_tokens`
    - `effort`
    - `tool_choice`
  - `Context` 现已作为正式 AI 输入语义进入主链
    - `system_prompt`
    - `messages`
    - `tools`
  - provider 现会消费正式 `Context` 语义
  - `anthropic-messages` 读取 `system_prompt` 与 `tools`
  - `openai-completions` 读取 `system_prompt` 与 `tools`
  - `openai-responses` 读取 `system_prompt` 与 `tools`
  - `tool/` 代码域现已包含共享 tool semantic helpers
    - provider tool schema conversion
    - tool argument validation
    - tool message transformation
  - `normalize_context(...)` 现在只负责 `Context` 形状整理并返回公开的 `NormalizedContext` 不可变 snapshot
  - `provider.invocation` 是 provider handoff 的最终归一化 guard；内置 adapter 不再二次 normalize
  - 消息规范化与 canonicalization 由 `messages.py` 负责，provider adapters 只消费 canonical message dataclass
  - `event_stream/assembler.py` 不再反查 model registry 做 cost enrich
  - `reset_api_providers()` / `register_builtin_ai_providers()` 会按 built-in model registry 自动注册 built-ins

## Examples

正式 example 默认演示最短 public path：

- `get_model(...)`
- `model.complete(...)` / `model.stream(...)`
- 显式 `Options(api_key=...)`

以下场景应视为 advanced：

- 自定义 `base_url`
- 手动构造 `ApiProviderRegistry`
- protocol 级 tool roundtrip

- [Model Lookup Example](../../../../examples/ai/model_lookup.py)
- [Complete Example](../../../../examples/ai/complete.py)
- [Stream Example](../../../../examples/ai/stream.py)
- [Tools Example](../../../../examples/ai/tools.py)
- [Typed Context Example](../../../../examples/ai/03_typed_context.py)
- [Faux Stream Example (Advanced)](../../../../examples/ai/advanced/faux_stream.py)
- [Context And Tool Minimal Example (Advanced)](../../../../examples/ai/advanced/context_tools_minimal.py)
- [Tool Result Roundtrip Example (Advanced)](../../../../examples/ai/advanced/tool_result_roundtrip.py)
- [Moonshot Anthropic Stream Vendor Verification](../../../../tests/ai/vendors/moonshot/test_kimi_anthropic_stream_live.py)
- [Moonshot Anthropic Complete Vendor Verification](../../../../tests/ai/vendors/moonshot/test_kimi_anthropic_complete_live.py)
- [Moonshot Anthropic Tools Vendor Verification](../../../../tests/ai/vendors/moonshot/test_kimi_anthropic_tools_live.py)
- [Moonshot OpenAI-Compatible Stream Vendor Verification](../../../../tests/ai/vendors/moonshot/test_kimi_openai_stream_live.py)
- [Moonshot OpenAI-Compatible Complete Vendor Verification](../../../../tests/ai/vendors/moonshot/test_kimi_openai_complete_live.py)
- [DashScope OpenAI-Compatible Responses Stream Vendor Verification](../../../../tests/ai/vendors/dashscope/test_openai_responses_stream_live.py)
- [DashScope OpenAI-Compatible Responses Tools Vendor Verification](../../../../tests/ai/vendors/dashscope/test_openai_responses_tools_live.py)
- [Moonshot Custom OpenAI-Compatible Base URL Verification](../../../../tests/ai/vendors/moonshot/test_custom_base_url_openai_live.py)

说明：

- `openai-completions` 已在 Kimi OpenAI-compatible 端点上验证通过
- 厂商相关验证现暂放在 `tests/ai/vendors/`，并按厂商目录维护
- 顶层 `examples/ai/` 只保留公开 API 样例，协议调试类内容下沉到 `examples/ai/advanced/`
- 主示例不再在 example 内回写环境变量，环境变量仅作为 `api_key` 的可选读取来源

## Reference

- [Reference AI SDK Reference](./reference/reference-ai-sdk/)
- [Reference AI SDK Streaming Semantics](./reference/reference-ai-sdk/reference-ai-sdk-streaming-semantics.md)
- [Reference AI SDK Adaptability NFR](./reference/reference-ai-sdk/reference-ai-sdk-adaptability-NFR.md)
- [Reference AI SDK Abstraction Variation Strategy](./reference/reference-ai-sdk/reference-ai-sdk-abstraction-variation-strategy.md)
- [Kimi-CLI Reference](./reference/kimi-cli/)
- [Claude Code Borrowing Notes](./reference/cc/cc-ai-borrowing-notes.md)

## History

- [Loushang AI Historical Handoff Summary](./history/loushang-ai-historical-handoff.md)
- [Loushang Method Notes](../loushang-method-notes.md)

## Cost Estimation

详见《[Loushang-AI Cost Estimation](./loushang-ai-cost-estimation.md)》。

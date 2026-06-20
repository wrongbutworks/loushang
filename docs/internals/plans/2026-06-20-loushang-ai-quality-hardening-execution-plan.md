# Loushang AI 包质量强化与能力收敛执行方案

> 文档定位：本文件是交给本地 Codex 执行的规范性实施计划。
>
> 执行原则：一次只完成一个工作包；每个工作包形成一个可独立验证的 commit；commit 后启动只读评审 Agent；P0/P1 问题必须修复并 amend 原 commit；通过评审后才进入下一项。
>
> 适用基线：`zhnt/loushang` 当前 `main`，执行开始时必须重新同步最新 `origin/main`。
>
> 目标版本：建议以 `0.2.0` 作为本轮契约收敛版本；是否正式修改版本号由最终发布 commit 决定。

---

## 1. 总目标

本轮不是继续横向堆积 Provider、模型条目和兼容特判，而是把 `loushang.ai` 收敛成一个边界清晰、契约可信、可验证、可扩展的通用 AI SDK。

最终必须同时达到以下结果：

1. `loushang.ai` 仍然只负责底层模型调用，不侵入 Agent 生命周期、会话管理、工具执行循环和产品级配置。
2. 稳定 API 面更小、更一致，Provider-specific 细节不泄漏到根包。
3. 消息、工具、错误、流事件、Usage、认证和请求参数都只有一个规范化入口。
4. `compat` 不再是无边界的 magic-string 字典，而是有类型、有层级、有来源、有默认规则的 Endpoint 契约。
5. Provider 运行链只有一套统一的错误、重试、取消、流关闭和事件装配语义。
6. 内置模型目录显著缩减，只保留少量核心国内外 Provider 和主力模型。
7. Issue #101 中列出的国产 Provider 均有明确处理结果：进入内置目录，或因官方稳定协议/事实不足而保守延期；不得猜测元数据。
8. Bedrock、Azure 等非本轮核心能力从核心包移除；OpenAI Codex 专有协议移到显式 `contrib` 边界。
9. 每项用户可见能力都有行为测试；关键能力都有可执行 example；每个 Provider 条目都有官方事实证据记录。
10. 每个 commit 都通过 `make check-ai` 和独立 Codex 评审。

---

## 2. 非目标

本轮明确不做：

- Agent loop、会话恢复、记忆、RAG、MCP 编排。
- HTTP/RPC 服务层。
- 全量模型数据库。
- 原生 Bedrock、Azure、Vertex、Gemini、Mistral 等专用适配器。
- 音频、视频、Embedding、图像生成等尚未形成完整公共协议的模态。
- 为每个国产厂商编写独立 Provider Adapter；优先复用标准协议适配器。
- 在没有官方文档或真实凭证验证的情况下填写价格、上下文窗口、工具、Reasoning、Structured Output 等事实。
- 在同一个 commit 中顺手重构无关模块。

---

## 3. 最终质量目标与量化门禁

### 3.1 目标评分

| 维度 | 当前静态评估 | 本轮目标 |
|---|---:|---:|
| 架构边界 | 8.0 | 9.0 |
| Stable API 一致性 | 6.0 | 8.5 |
| 消息与工具规范化 | 7.5 | 9.0 |
| Compat/Endpoint 契约 | 5.5 | 9.0 |
| 错误与可靠性 | 5.5 | 8.5 |
| Streaming/取消 | 7.0 | 8.5 |
| Provider 一致性 | 6.0 | 8.5 |
| 认证安全 | 5.5 | 8.0 |
| 模型目录治理 | 6.0 | 9.0 |
| 测试、示例、文档 | 6.5 | 9.0 |

最终综合目标不低于 **8.5/10**，且必须满足：

- P0/P1 未解决问题为 0。
- `make check-ai` 全绿。
- 全仓测试通过。
- 所有保留适配器通过同一套 Provider Contract Tests。
- Stable API 有快照测试。
- 归一化、错误和流式协议有不变量测试。
- 内置 catalog 不超过既定预算。

### 3.2 代码质量硬指标

核心目录 `src/loushang/ai` 最终满足：

- 不允许 Tab 缩进。
- 核心契约函数必须有完整参数和返回类型。
- `Any` 只能出现在厂商 SDK 边界的局部变量中，不得出现在核心 Protocol 和 Stable API 中。
- 核心层不得使用裸 `except Exception: pass`。
- Provider Adapter 不得重复实现统一 stream runner。
- Provider ID、Base URL 不得用于核心运行时兼容性猜测。
- Provider-specific SDK 类型不得出现在公共消息、事件或错误对象中。
- Built-in catalog 不得出现 legacy `compat` 字段。
- 用户可见 capability 一旦声明为支持，就必须有实现和测试。

---

## 4. 目标架构

### 4.1 保留的总体调用链

```text
Model
  -> normalize Context and Messages exactly once
  -> validate requested capabilities
  -> resolve typed EndpointContract and auth
  -> build ProviderRequest
  -> core ProviderRuntime
       -> retry before first visible output only
       -> cancellation/deadline/idle timeout
       -> adapter.stream_raw()
       -> RawAssembler
       -> AssistantMessageEventStream
  -> result or typed error
```

### 4.2 Provider Adapter 的最终职责

最终 `ApiProvider` 不再负责创建 `AssistantMessageEventStream`、启动 task、捕获通用异常和装配最终消息。Adapter 只负责：

1. 把 `ProviderRequest` 转成厂商请求。
2. 调用 SDK/HTTP transport。
3. 把厂商流事件映射为统一 `RawPart`。
4. 关闭自己创建的厂商资源。

建议目标 Protocol：

```python
class ApiProvider(Protocol):
    api: ApiFamily

    async def stream_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[RawPart]: ...
```

`stream_simple` 不应继续存在于 Provider Protocol；Simple 语义必须在核心 API 层先转成统一 `CallOptions`。

### 4.3 稳定 API 目标

根包只保留最常用稳定能力：

```text
Invocation
- stream
- complete
- stream_simple
- complete_simple

Model access
- Model
- get_model
- list_models

Unified input/output
- Context
- Message
- UserMessage
- AssistantMessage
- ToolResultMessage
- Tool
- ToolCall
- TextPart
- ImagePart
- ThinkingPart
- UsageObservation
- AssistantMessageEvent
- AssistantMessageEventStream

Options and errors
- CallOptions
- SimpleCallOptions
- ReasoningOptions
- RetryOptions
- TimeoutOptions
- AIError
- AIErrorInfo
```

以下能力移入 Advanced 子包，不再作为根包稳定门面：

- Provider Registry 管理细节。
- RawPart、Assembler、JSON 流解析。
- Provider-specific payload 转换函数。
- OAuth Registry 和 Credential Store 细节。
- Catalog Loader 和 Endpoint Resolution 细节。
- OpenAI Codex 专有 Options。

---

## 5. Compat 能力层重构

## 5.1 当前问题

现有 `compat` 同时混合：

- 模型能力。
- 标准协议支持情况。
- 请求字段差异。
- 厂商怪癖。
- Transport。
- Session Header。
- Routing。
- 上游 Model ID。
- Codex 专有配置。

这导致：

- Magic string 到处传播。
- 同一事实可能同时存在于 capabilities、defaults 和 compat。
- 运行时按 provider ID 或 base URL 猜测行为。
- 未知事实常被错误当成 false 或 true。
- 新增 Provider 容易继续堆特判。

## 5.2 新的五层事实模型

### A. `ModelCapabilities`

只描述调用方可以要求模型做什么：

- 输入模态。
- 输出模态。
- Streaming。
- Tool Use。
- Reasoning。
- Structured Output 模式。
- Temperature。
- Attachment。
- Context Window。
- Max Output Tokens。

建议使用显式支持状态：

```python
class SupportStatus(Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
```

规则：

- 内置 catalog 的核心能力不得长期保持 `UNKNOWN`。
- 自定义 catalog 可以使用 `UNKNOWN`。
- 默认运行策略对高级能力保守：`UNKNOWN` 不等于支持。

### B. `EndpointProtocolFeatures`

描述 Endpoint 对标准协议功能的支持：

- Developer role。
- Streaming usage。
- Reasoning effort。
- Reasoning delta。
- Strict tool schema。
- Eager tool input streaming。
- Cache control on tools。
- Long cache retention。
- Session ID/Affinity 支持。
- Store 参数。

### C. `EndpointWireDialect`

只描述“协议看起来相同，但线格式不同”的差异：

- 最大输出 Token 字段名。
- Thinking wire format。
- Tool Result 是否要求 name。
- Tool Result 后是否需要 assistant bridge。
- Thinking 是否必须降级成 text。
- Assistant replay 是否要求 reasoning content。
- Cache Control 格式。
- 特殊 tool stream 字段。

### D. `EndpointTransport`

只描述调用方式：

- SDK family。
- HTTP/SSE/WebSocket。
- 默认流 transport。
- 是否允许 transport fallback。
- Timeout 能力。

### E. `EndpointRouting` 与 `ModelBinding`

只描述路由事实：

- Base URL。
- Region/Lane。
- 上游 Model ID。
- Gateway 请求路由参数。
- Deployment/Namespace。

`upstreamModelId` 必须移出 compat，成为模型绑定的一等字段。

## 5.3 Legacy compat 映射表

| Legacy key | 新位置 |
|---|---|
| `supportsStore` | `protocol.store` |
| `supportsDeveloperRole` | `protocol.roles.developer` |
| `supportsReasoningEffort` | `protocol.reasoning.effort` |
| `reasoningEffortMap` | `protocol.reasoning.effort_map` |
| `supportsUsageInStreaming` | `protocol.streaming.usage` |
| `supportsStreamReasoningDelta` | `protocol.streaming.reasoning_delta` |
| `maxTokensField` | `dialect.max_output_tokens_field` |
| `requiresToolResultName` | `dialect.tools.result_name_required` |
| `requiresAssistantAfterToolResult` | `dialect.tools.assistant_bridge_required` |
| `requiresThinkingAsText` | `dialect.reasoning.thinking_as_text` |
| `thinkingFormat` | `dialect.reasoning.wire_format` |
| `supportsStrictMode` | `protocol.tools.strict_schema` |
| `requiresReasoningContentOnAssistantMessages` | `dialect.reasoning.assistant_content_required` |
| `openRouterRouting` | `routing.request_overrides` |
| `vercelGatewayRouting` | `routing.request_overrides` |
| `zaiToolStream` | `dialect.tools.stream_flag` |
| `cacheControlFormat` | `dialect.cache.control_format` |
| `sendSessionAffinityHeaders` | `protocol.session.affinity_headers` |
| `sendSessionIdHeader` | `protocol.session.id_header` |
| `supportsLongCacheRetention` | `protocol.cache.long_retention` |
| `supportsEagerToolInputStreaming` | `protocol.tools.eager_input_stream` |
| `supportsCacheControlOnTools` | `protocol.cache.on_tools` |
| `fineGrainedTools` | `protocol.tools.fine_grained` |
| `interleavedThinking` | `protocol.reasoning.interleaved` |
| `providerTransport` | `transport.kind` |
| `supportsJsonSchemaStructuredOutput` | `capabilities.structured_output_modes` |
| `upstreamModelId` | `model.upstream_id` |
| `codex*` | `loushang.ai.contrib.openai_codex` 专有配置 |

## 5.4 Catalog Schema v2 示例

以下只是结构示意，不代表真实 Provider 事实：

```json
{
  "schemaVersion": 2,
  "providers": {
    "example": {
      "displayName": "Example",
      "auth": {
        "kind": "apiKey",
        "apiKeyEnv": "EXAMPLE_API_KEY"
      },
      "endpoints": {
        "chat": {
          "api": "openai-completions",
          "profile": "openai-compatible",
          "baseUrl": "https://example.invalid/v1",
          "protocol": {
            "roles": {"developer": "unsupported"},
            "streaming": {
              "usage": "supported",
              "reasoningDelta": "supported"
            },
            "tools": {
              "strictSchema": "unsupported"
            }
          },
          "dialect": {
            "maxOutputTokensField": "max_completion_tokens",
            "reasoning": {"wireFormat": "vendor-specific"}
          },
          "transport": {
            "kind": "openai-sdk",
            "stream": "sse"
          },
          "models": {
            "public-model-id": {
              "upstreamId": "real-upstream-id",
              "capabilities": {
                "input": ["text"],
                "output": ["text"],
                "stream": "supported",
                "toolUse": "supported",
                "reasoning": "supported",
                "structuredOutput": ["json_schema"]
              }
            }
          }
        }
      }
    }
  }
}
```

## 5.5 Compat 重构不变量

必须新增自动测试保证：

1. Built-in v2 catalog 不含 `compat`。
2. 核心 Provider 不直接读取 magic compat key。
3. 核心运行时不按 provider ID 或 base URL 推断兼容行为。
4. Legacy catalog 只能在 Loader 边界转换一次。
5. Legacy 转换产生诊断信息，不得静默。
6. Model capabilities 与 Endpoint protocol facts 不得相互覆盖。
7. Defaults 不能改变 Capability；只提供请求默认值。
8. 未知价格不得按 0 成本处理。

---

## 6. 消息和 Context 归一化

## 6.1 最终对象

建议引入：

```python
@dataclass(frozen=True, slots=True)
class NormalizedContext:
    system_prompt: str | None
    messages: tuple[CanonicalMessage, ...]
    tools: tuple[Tool, ...]

@dataclass(frozen=True, slots=True)
class NormalizationDiagnostic:
    code: str
    severity: Literal["info", "warning", "error"]
    message_index: int | None
    detail: Mapping[str, JSONValue]

@dataclass(frozen=True, slots=True)
class NormalizationResult:
    context: NormalizedContext
    diagnostics: tuple[NormalizationDiagnostic, ...]
```

## 6.2 规则

- 外部可以传 Typed Object 或兼容字典。
- 进入核心后全部变成 Canonical dataclass。
- Provider Adapter 只接受 `NormalizedContext`。
- 删除 `_loushang_normalized_context` marker 字段。
- 删除 Adapter 内部的二次 `ensure_normalized_context()`。
- `normalize_context(NormalizedContext)` 必须幂等。
- System/Developer 合并顺序固定且有测试。
- camelCase/snake_case 只在输入 Parser 边界兼容。
- 未知消息角色和内容 part 必须明确报错。
- 跨 Provider Thinking/Signature 降级必须产生 diagnostic。
- Tool Result repair 必须产生 diagnostic。
- SDK 默认 tool pairing policy 使用 strict；repair 只用于历史导入和恢复，由上层显式选择。

## 6.3 Tool 消息规则

- Tool Call ID 规范化映射必须同步应用到对应 Tool Result。
- 重复、迟到、孤立和名称不匹配的结果有稳定错误码。
- Parallel Tool Call 使用 `dict[call_id, buffer]`，不能只维护一个 active call。
- 流事件必须保留 Provider 提供的 call index/item ID，避免交错增量串线。

---

## 7. 统一错误模型

## 7.1 异常层级

```text
AIError
├── AIConfigurationError
│   ├── ModelNotFoundError
│   ├── AmbiguousModelError
│   └── UnsupportedCapabilityError
├── AIAuthenticationError
├── AIRequestValidationError
│   └── ToolValidationError
├── AIProviderError
│   ├── AIRateLimitError
│   ├── AITimeoutError
│   ├── AIServiceUnavailableError
│   ├── AIContextOverflowError
│   └── AIProviderProtocolError
├── AIStreamError
└── AICancelledError
```

## 7.2 稳定错误信息

```python
@dataclass(frozen=True, slots=True)
class AIErrorInfo:
    code: AIErrorCode
    message: str
    source: str
    retryable: bool
    provider: str | None = None
    endpoint: str | None = None
    model: str | None = None
    status_code: int | None = None
    request_id: str | None = None
    details: Mapping[str, JSONValue] = field(default_factory=dict)
```

要求：

- `details` 不得包含 token、Authorization、API key、refresh token。
- Vendor 原始异常保留为 `__cause__`，不直接进入序列化结果。
- 错误码稳定，错误文案允许优化。
- Provider HTTP 状态、SDK 异常和流事件错误统一映射。
- Context overflow 从字符串识别结果升级为正式错误分类。

## 7.3 流式错误语义

- Stream 创建前的配置、能力和鉴权错误直接 raise。
- Stream 开始后的错误产生且只产生一个 terminal `error` event。
- `AssistantMessageEventStream.result()` 默认 raise 对应 typed error。
- 另提供 `final_message()` 或等价高级接口取得错误终止消息。
- `complete()` 不返回 `stop_reason="error"` 的伪成功结果。
- 所有流必须恰好一个 terminal event。

---

## 8. 统一 Call Options

建议用一组 Provider-neutral Options 取代根包中的多套 Provider-specific Options：

```python
@dataclass(frozen=True, slots=True)
class ReasoningOptions:
    enabled: bool | None = None
    effort: ThinkingLevel | None = None
    budget_tokens: int | None = None
    expose_summary: bool = False

@dataclass(frozen=True, slots=True)
class RetryOptions:
    max_attempts: int = 1
    max_delay_seconds: float = 30.0
    retryable_codes: frozenset[AIErrorCode] = ...

@dataclass(frozen=True, slots=True)
class TimeoutOptions:
    connect_seconds: float | None = None
    total_seconds: float | None = None
    idle_seconds: float | None = None

@dataclass(frozen=True, slots=True)
class CallOptions:
    api_key: str | None = None
    headers: Mapping[str, str] = ...
    max_output_tokens: int | None = None
    temperature: float | None = None
    reasoning: ReasoningOptions | None = None
    retry: RetryOptions = ...
    timeout: TimeoutOptions = ...
    cache_retention: CacheRetention | None = None
    session_id: str | None = None
    tool_choice: ToolChoice | None = None
    output: StructuredOutputOptions | None = None
    metadata: Mapping[str, JSONValue] = ...
    hooks: CallHooks | None = None
    cancellation: CancellationSignal | None = None
    provider_options: Mapping[str, JSONValue] = ...
```

规则：

- 通用字段由核心处理。
- `provider_options` 只用于 Advanced 场景，并由具体 Adapter 验证。
- 不支持的显式参数必须报 `UnsupportedCapabilityError`，不得静默忽略。
- `stream_simple` 只接受更窄的 `SimpleCallOptions`，并在核心层映射到 `CallOptions`。

---

## 9. Streaming、重试和取消

## 9.1 Core Provider Runtime

统一 Runtime 负责：

- 创建 EventStream 和 RawAssembler。
- 绑定 Producer Task。
- Provider Error 分类。
- Trace。
- Cancellation。
- Deadline 和 Idle Timeout。
- Retry。
- 资源关闭。

## 9.2 Retry 规则

- 只允许在第一个用户可见 event 产生之前自动重试。
- 已经输出 text、thinking、tool call 或 image 后不得透明重试，防止重复副作用。
- 尊重 `Retry-After`。
- 指数退避加 jitter。
- Auth、Validation、Unsupported Capability 默认不可重试。
- Rate Limit、Timeout、5xx 可按策略重试。
- Retry 行为必须产生 trace event。

## 9.3 Backpressure

- Event queue 必须有界。
- Producer 使用可等待的 `emit()`，而不是无界 `put_nowait()`。
- 消费者退出后取消 Producer 并关闭上游。
- 测试慢消费者、大量 delta、提前 break 和 result-only 四种模式。

## 9.4 Cancellation

定义正式 Protocol：

```python
class CancellationSignal(Protocol):
    def is_cancelled(self) -> bool: ...
    async def wait(self) -> None: ...
```

支持标准适配器：

- `asyncio.Event`。
- 当前带 `cancelled`/`aborted` 属性的兼容对象。

取消必须：

- 关闭 HTTP Response/SDK stream。
- 取消 Producer task。
- 发出一个 `aborted` terminal error。
- 不泄漏 task。

---

## 10. Tool、Structured Output 和多模态完整化

## 10.1 Tool Validation

拆成两种明确策略：

```text
strict  -> 不做隐式类型转换
coerce  -> 允许可审计的基础转换，并返回 diagnostics
```

SDK 默认 tool validation policy 使用 `strict`。历史兼容场景由调用方显式选择 `coerce`。

## 10.2 Parallel Tool Calls

必须支持：

- 多个 Tool Call 顺序出现。
- 多个 Tool Call 增量交错。
- Tool Result 任意合法顺序回流。
- 单个 Tool 失败不破坏其他 Tool Call 的配对。
- call ID 和 index 同时可用时优先 call ID。

## 10.3 Structured Output

引入统一：

```python
@dataclass(frozen=True, slots=True)
class StructuredOutputOptions:
    mode: Literal["json_object", "json_schema"]
    schema: Mapping[str, JSONValue] | type | None = None
    strict: bool = True
```

输出应包含：

- 原始 `AssistantMessage`。
- 解析后的 JSON/Pydantic 对象。
- 解析错误的 typed exception。

关键规则：

- 模型和 Endpoint 均确认支持后才发送。
- Chat Completions 不得伪装成 Responses 能力。
- Provider-specific schema payload 只在 Adapter 内生成。

## 10.4 多模态范围

本轮只承诺：

- Text input/output。
- Image input。
- Image Tool Result 回流。
- Image output event 的统一表示，仅在 Provider 实际支持时声明。

Built-in catalog 必须删除没有完整实现的 `video`、`audio`、`vector` 声明。

---

## 11. Auth 和凭据安全

## 11.1 Credential Store 抽象

```python
class CredentialStore(Protocol):
    def load(...) -> OAuthCredentials | None: ...
    def save(...) -> None: ...
    def delete(...) -> None: ...
```

核心提供安全 File Store：

- `~/.loushang/ai` 目录权限尽可能收紧。
- Unix 文件权限 `0600`。
- 原子替换。
- 文件锁或等价并发保护。
- 损坏文件明确报错，不静默回退。
- 不在 trace 中打印 secret。

OS Keyring 可作为后续可选实现，不应阻塞本轮核心收敛。

## 11.2 Auth Resolution

解析优先级必须文档化并测试：

1. 显式 OAuth credential。
2. 显式 API key。
3. 环境 OAuth。
4. Scoped stored OAuth。
5. Catalog API key env。

OAuth refresh 失败不得被吞掉后伪装成“没有凭据”。

---

## 12. Usage、Cost 与 Platform Quota

分离两类完全不同的事实：

```text
UsageObservation
- 单次模型响应的 input/output/cache token 和成本

PlatformQuota
- 账号级 limit/used/remaining/resetTime
```

要求：

- `UsageObservation` 由响应事件产生。
- `PlatformQuota` 通过 Endpoint 级可选查询能力产生。
- 不在 example 中硬编码 `/usages`。
- 未知价格返回 `cost=None`，不得返回 0 伪装免费。
- Pricing 带 currency、source 和 verifiedAt；不确定就省略。
- Cost 内部优先使用 `Decimal`，序列化时再转换。

---

## 13. Provider 和模型范围收缩

## 13.1 核心协议适配器

最终 Core Built-in Adapter 只保留：

1. `openai-completions`
2. `openai-responses`
3. `anthropic-messages`

另外：

- `FauxProvider` 只用于测试，不进入生产目录。
- `openai-codex-responses` 移到 `loushang.ai.contrib.openai_codex`，显式注册，不进入 Stable API 和默认 catalog。
- 删除核心 `azure-openai-responses`。
- 删除核心 `bedrock-converse-stream`。

## 13.2 Built-in catalog 预算

硬限制：

- Provider ID：最多 11。
- Endpoint：最多 16。
- Model：最多 20。
- 每个 Provider 默认最多 2 个模型。
- 每个 Provider/Model 最多一个 preferred Endpoint。
- 非必要地域副本不进入 Built-in catalog。

## 13.3 目标 Provider 清单

### 核心国际

| Provider | 模型预算 | 目标协议 |
|---|---:|---|
| OpenAI | 2 | Responses 优先 |
| Anthropic | 2 | Anthropic Messages |

### 已有核心国产

| Provider | 模型预算 | 目标协议 |
|---|---:|---|
| Moonshot/Kimi | 2 | Chat Completions + 官方 Coding 协议 |
| DashScope/Qwen | 2 | Responses 或官方稳定兼容协议 |

### Issue #101 国产 Provider

| Issue | Provider | 模型预算 |
|---|---|---:|
| #102 | Tencent Hunyuan | 1 |
| #103 | Zhipu GLM | 2 |
| #104 | DeepSeek | 2 |
| #105 | MiniMax | 1 |
| #106 | Doubao / Volcano Ark | 1 |
| #107 | Baidu Qianfan / Wenxin | 1 |
| #108 | StepFun | 1 |

目标总量：约 17 个模型。

## 13.4 模型选择规则

每家只选择：

- 一个主力通用/旗舰模型。
- 只有在产品价值明显时再加一个轻量或 Reasoning/Coding 模型。

执行时必须由 Catalog Review Agent 根据官方文档确定实际 Model ID；本计划不预写容易过期的具体 ID。

必须核对：

- Official Base URL。
- Official API protocol。
- Model ID。
- API key env。
- Streaming。
- Tool Use。
- Reasoning。
- Structured Output。
- Image input。
- Context window。
- Max output tokens。
- Pricing；不确定则不填。

## 13.5 删除范围

从 Built-in catalog 删除：

- OpenRouter 大量镜像模型。
- Cloudflare、Vercel、Vertex、Mistral 等非核心入口。
- 重复地域 Endpoint。
- 无官方稳定事实的模型。
- 过时版本和全量模型系列。
- 未完整实现的音频、视频、向量能力声明。

这些 Provider 仍可以通过用户自定义 catalog 接入。

---

## 14. 当前 models.json 的备份方案

Git 历史不是本轮唯一备份。执行以下确定性归档：

```bash
mkdir -p docs/internals/archive/ai/model-catalog
cp src/loushang/ai/model/models.json /tmp/loushang-models-v1-full.json
sha256sum /tmp/loushang-models-v1-full.json \
  > docs/internals/archive/ai/model-catalog/models-v1-full.sha256
gzip -9 -n -c /tmp/loushang-models-v1-full.json \
  > docs/internals/archive/ai/model-catalog/models-v1-full.json.gz
```

同时写入：

```text
docs/internals/archive/ai/model-catalog/README.md
```

内容包括：

- 来源 commit SHA。
- 原始文件路径。
- SHA-256。
- 解压恢复命令。
- 为什么缩减。
- 删除内容通过 custom catalog 恢复的方法。

归档 commit 必须验证：

```bash
gzip -dc docs/internals/archive/ai/model-catalog/models-v1-full.json.gz \
  | sha256sum
```

不得把备份继续放入 Python package data。

---

## 15. Provider 事实证据制度

每个 Built-in Provider 必须有：

```text
docs/internals/architecture/ai/catalog-evidence/<provider>.md
```

模板：

```markdown
# Provider evidence: <provider>

- Verified at: YYYY-MM-DD
- Issue: #...
- Official docs:
  - ...
- Authentication:
  - env: ...
  - header: ...
- Endpoint:
  - base URL: ...
  - protocol: ...
- Included models:
  - id: ...
  - reason for inclusion: ...
- Verified capabilities:
  - streaming: source
  - tools: source
  - reasoning: source
  - structured output: source
  - image: source
- Unknown/omitted facts:
  - ...
- Contract tests:
  - ...
- Manual live smoke:
  - not run / passed / failed
  - command and date
```

规则：

- 只接受官方厂商文档、官方 SDK 或真实 API 响应作为事实来源。
- Blog、聚合站和模型榜单不能作为 Catalog 事实来源。
- 无法证实的能力标记 unknown 或省略。
- 无凭证时不伪造 live passed。
- Issue 只有在其 Acceptance Criteria 真正满足后关闭；没有凭证就保留 open 并说明剩余项。

---

## 16. 测试体系

## 16.1 分层

```text
tests/ai/unit/
- domain/options/normalization/error/retry/tool validation

tests/ai/contracts/
- public API contract
- provider adapter contract
- stream terminal contract
- catalog contract

tests/ai/integration/
- Faux/fixture provider end-to-end
- custom catalog loading
- contrib registration

tests/providers/
- vendor event fixtures and payload mapping

tests/ai/vendors/
- manual live smoke, marker=live
```

无需为了目录美观一次性搬迁全部测试；按修改模块逐步迁移。

## 16.2 Provider Contract Suite

所有保留 Adapter 必须运行同一套参数化测试：

- Text complete。
- Text stream 顺序。
- Tool call。
- Tool result replay。
- Parallel tool call。
- Usage。
- Error mapping。
- Cancellation。
- Retry before output。
- No retry after output。
- Resource close。
- Capability rejection。
- Structured output；仅支持者运行。
- Image input；仅支持者运行。

## 16.3 关键不变量测试

- Normalization idempotent。
- Normalized Provider boundary 不含 raw dict message。
- Exactly one terminal stream event。
- `complete == stream.result`。
- Error result raises typed error。
- No secret in trace。
- No unbounded queue。
- No legacy compat in built-in catalog。
- No unsupported modality in built-in catalog。
- No duplicate preferred endpoint。
- Catalog count within budget。
- Root `__all__` snapshot。

## 16.4 Coverage

建议增加 `pytest-cov` 开发依赖：

- AI core statement coverage >= 90%。
- Provider adapters aggregate >= 85%。
- 新增模块不得低于 90%。

Coverage 不替代行为测试。

---

## 17. Examples 与文档

## 17.1 最终 Example 清单

```text
examples/ai/
01_complete.py
02_stream.py
03_typed_context.py
04_tools.py
05_parallel_tools.py
06_reasoning.py
07_structured_output.py
08_image_input.py
09_errors_retry.py
10_usage.py
11_custom_catalog.py
12_provider_smoke.py

examples/ai/advanced/
inspect_endpoint_contract.py
oauth_login.py
openai_codex_contrib.py
platform_quota.py
```

规则：

- 主 examples 只使用 Stable API。
- Advanced examples 才允许子包 API。
- 每个 example 默认可使用 Faux/fixture 模式离线运行。
- 需要真实凭证的部分必须显式提示环境变量，不得在导入时发请求。
- CI 执行所有离线 examples。

## 17.2 每项能力的文档要求

每个用户可见能力必须文档化：

- Contract。
- 最小示例。
- 错误语义。
- Provider 支持矩阵。
- 已知限制。
- 迁移说明。

中英文公开文档同步；Internal ADR 可以只写中文，但代码符号保持英文。

---

## 18. 本地 Codex 工作模式

## 18.1 Worktree 和分支

按仓库 `AGENTS.md` 使用 AI lane：

```bash
cd /home/chester/Workspace/ai/loushang
git status --short
git fetch --prune origin
test -d .worktrees/ai || git worktree add -b ai/quality-hardening-v2 .worktrees/ai origin/main
cd .worktrees/ai
make bootstrap
make check-ai
uv run pytest tests -q
```

若 worktree 有用户未提交修改：

- 不执行 reset/clean。
- 先记录和保护现有修改。
- 不覆盖用户文件。

只在 Phase 边界 rebase 最新 main；rebase 后运行 full suite 和 `git range-diff`。

## 18.2 项目级 Codex Agent 配置

新增：

```toml
# .codex/config.toml
[agents]
max_threads = 5
max_depth = 1
```

### `.codex/agents/ai-architect.toml`

```toml
name = "ai_architect"
description = "Read-only reviewer for loushang.ai architecture and API boundaries."
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review loushang.ai as a general-purpose lower-level AI SDK.
Check package boundaries, stable vs advanced API, typed contracts, dependency direction,
and whether the change introduces provider-specific behavior into core layers.
Do not edit files. Return only concrete findings with file/symbol evidence.
"""
```

### `.codex/agents/ai-reviewer.toml`

```toml
name = "ai_reviewer"
description = "Read-only correctness and security reviewer for one atomic AI commit."
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review one commit against its parent.
Prioritize correctness, behavior regressions, error semantics, resource leaks,
secret exposure, concurrency, and public API compatibility.
Do not make edits. Ignore style-only observations unless they hide a defect.
Return P0/P1/P2 findings with file and symbol references.
"""
```

### `.codex/agents/ai-test-reviewer.toml`

```toml
name = "ai_test_reviewer"
description = "Read-only reviewer for tests, examples, and missing edge cases."
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review the changed behavior and its tests.
Look for missing negative tests, contract tests, cancellation/error paths,
provider fixture gaps, flaky assertions, and examples that do not use public APIs.
Do not edit files.
"""
```

### `.codex/agents/ai-catalog-reviewer.toml`

```toml
name = "ai_catalog_reviewer"
description = "Read-only reviewer for provider catalog facts and protocol claims."
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review model catalog changes conservatively.
Require official evidence for model IDs, endpoints, auth, capabilities, context limits,
pricing, streaming, tools, reasoning, images, and structured output.
Do not infer unsupported facts from similar providers.
Do not edit files. Mark uncertain claims as blockers or recommend omission.
"""
```

### `.codex/agents/ai-docs-reviewer.toml`

```toml
name = "ai_docs_reviewer"
description = "Read-only reviewer for public docs and executable examples."
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = """
Check that docs and examples match the current stable public API,
show the shortest supported path, document errors and limitations,
and do not depend on internal provider wiring unless marked advanced.
Do not edit files.
"""
```

## 18.3 AI 子目录指导文件

新增 `src/loushang/ai/AGENTS.md`：

```markdown
# loushang.ai working agreement

- This package is a lower-level AI SDK, not an agent orchestrator.
- Do not import loushang.agent or loushang.coding from loushang.ai.
- Normalize input once before provider adapters.
- Provider adapters emit RawPart and must not expose vendor SDK objects.
- Core behavior must not branch on provider id or base URL.
- Built-in catalog facts require official evidence.
- Unknown capability is not supported capability.
- Every behavior change includes tests; user-visible changes include examples/docs.
- Run make check-ai before every commit.
- One plan item per commit; do not mix unrelated cleanup.
```

## 18.4 首次交给 Codex 的协调 Prompt

```text
Read AGENTS.md, src/loushang/ai/AGENTS.md, and
docs/internals/plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md completely.
Before AIQ-002 creates src/loushang/ai/AGENTS.md, read AGENTS.md and the
execution plan, then continue with the current package only.

Act as the implementation coordinator for this plan.
Work only in the AI worktree and current task branch.
Do not execute more than one AIQ work package at a time.
For the selected package:
1. inspect the real code paths;
2. state the exact behavioral contract and files to change;
3. implement the smallest vertical slice;
4. add/update focused tests;
5. add/update the required example or docs when user-visible;
6. run targeted checks and make check-ai;
7. create exactly one commit with the specified Plan-ID;
8. spawn the required read-only review agents, wait for all, and summarize findings;
9. fix P0/P1 findings by amending the same commit, rerun checks and review;
10. stop after the package passes and report the commit SHA.

Never let parallel agents write code. Use subagents only for read-heavy exploration and review.
Do not guess provider/model facts. Use official evidence or omit the fact.
```

## 18.5 每个 commit 的评审 Prompt

```text
Review commit HEAD against HEAD^ as one atomic loushang.ai change.
Spawn ai_reviewer and ai_test_reviewer.
Also spawn:
- ai_architect for core/API/normalization/runtime changes;
- ai_catalog_reviewer for catalog/provider metadata changes;
- ai_docs_reviewer for public docs/examples changes.

All agents must be read-only. Wait for all agents.
Return a consolidated report grouped by P0, P1, P2.
Each finding must include file/symbol, evidence, impact, and minimal fix.
Check that implementation, tests, examples, and docs form one complete vertical slice.
Do not modify files.
```

交互式 CLI 中还要执行：

```text
/review
/diff
```

使用 `/agent` 检查各子 Agent 线程。

## 18.6 非交互评审脚本

由 AIQ-002 新增 `scripts/ai/review_commit.sh`，默认 Codex `exec` 使用只读 sandbox：

```bash
#!/usr/bin/env bash
set -euo pipefail

base="${1:-HEAD^}"
head="${2:-HEAD}"
sha="$(git rev-parse --short "$head")"
out=".artifacts/ai-reviews/${sha}.md"
mkdir -p "$(dirname "$out")"

codex exec --ephemeral \
  "Review commit ${head} against ${base}. Spawn ai_reviewer and ai_test_reviewer, plus the relevant domain reviewer. All agents are read-only. Wait for all. Report P0/P1/P2 findings with file and symbol evidence. Do not edit files." \
  -o "$out"

cat "$out"
```

`.artifacts/` 也由 AIQ-002 加入 `.gitignore`。评审报告默认不进入产品 commit。

---

## 19. 单 commit 标准操作程序

每个 AIQ 工作包严格执行：

### Step 1：前置检查

```bash
git status --short
git log -1 --oneline
```

工作区必须干净。

### Step 2：只实现当前工作包

- 不实现下一个工作包。
- 不顺带格式化整个目录。
- 不修改无关 Provider。
- 实现、测试、示例、必要文档作为一个 vertical slice。

### Step 3：验证

```bash
uv run pytest <targeted-tests> -q
uv run ruff check <changed-paths>
uv run mypy
make check-ai
git diff --check
```

用户可见能力还要运行对应 example。

### Step 4：commit

格式：

```text
<type>(ai-scope): <imperative summary>

Plan-ID: AIQ-XXX
Checks: make check-ai
```

### Step 5：commit 后评审

- 启动规定的只读 Agent。
- 执行 `/review`。
- P0/P1 必须修复。
- 修复使用：

```bash
git commit --amend --no-edit
```

这样始终保持“一个修改点一个 commit”。

### Step 6：复验

AIQ-001 在 `scripts/ai/review_commit.sh` 落地前，使用当前可用的只读评审机制复验。
AIQ-002 及之后的工作包必须运行：

```bash
make check-ai
scripts/ai/review_commit.sh HEAD^ HEAD
```

直到：

- P0 = 0。
- P1 = 0。
- P2 已修复，或有明确 issue/ADR 和理由。

### Step 7：停止

报告：

- Plan-ID。
- Commit SHA。
- Tests。
- Example。
- Review Agents。
- Review result。
- 下一工作包，但不要自动开始。

---

## 20. 原子 Commit 执行清单

以下顺序是强制顺序。迁移采用 dual-read/dual-catalog，确保每个中间 commit 都可运行。

### Phase 0：治理、基线与备份

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-001 | `docs(ai): add quality hardening charter` | 将本计划和架构决策摘要加入 `docs/internals/plans/`，声明目标版本、范围、非目标和质量门禁 | 文档链接检查 | architect + docs |
| AIQ-002 | `chore(codex): add AI review agents` | 增加 `.codex/config.toml`、5 个只读 Agent、`src/loushang/ai/AGENTS.md`、`scripts/ai/review_commit.sh`，并将 `.artifacts/` 加入 `.gitignore` | Codex 配置解析；review 脚本 dry-run/help 检查；无 Python 改动 | architect |
| AIQ-003 | `test(ai): capture baseline contracts` | 增加 root exports、Provider API、catalog 数量、测试数量和已知问题的基线快照；增加 `scripts/ai/plan_status.py` | `tests/ai/test_baseline_contracts.py` | reviewer + test |
| AIQ-004 | `chore(ai-model): archive the full legacy catalog` | 确定性 gzip 备份当前 `models.json`、SHA、README、恢复验证 | 解压 SHA 校验 | catalog + reviewer |

**Phase Gate 0**

```bash
make check-ai
uv run pytest tests -q
```

### Phase 1：Catalog v2 与 Compat 类型化

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-005 | `feat(ai-model): add versioned catalog schemas` | Loader 支持 `schemaVersion=1/2`；未知版本明确报错；不切换默认 catalog | loader v1/v2/unknown tests | architect + test |
| AIQ-006 | `refactor(ai-model): add typed protocol features` | 增加 `SupportStatus` 和 `EndpointProtocolFeatures`；保持 legacy 读取 | domain round-trip tests；advanced inspect example 更新 | architect |
| AIQ-007 | `refactor(ai-model): add typed wire dialects` | 增加 `EndpointWireDialect`，覆盖 token field、tools、thinking、cache 差异 | dialect parse/serialize tests | architect + test |
| AIQ-008 | `refactor(ai-model): separate transport and routing` | 增加 `EndpointTransport`、`EndpointRouting`；不再把 transport/routing 放 compat | resolution tests | architect |
| AIQ-009 | `refactor(ai-model): promote upstream model bindings` | `Model.upstream_id` 一等字段；Provider payload 使用统一 resolver | model binding tests；custom catalog example | architect + test |
| AIQ-010 | `fix(ai-pricing): represent unknown prices explicitly` | `Pricing | None` 或明确 unknown；cost 未知返回 None；禁止默认 0 | pricing tests；usage example | reviewer + test |
| AIQ-011 | `feat(ai-model): translate legacy compat with diagnostics` | 旧 compat 只在 Loader 转换；返回 deprecation diagnostics；转换表全覆盖 | table-driven mapping tests | architect + test |
| AIQ-012 | `refactor(ai-provider): resolve typed provider requests` | `ResolvedRequest` 改用 typed contract；核心不再暴露 compat dict | provider resolution tests；inspect example | architect |
| AIQ-013 | `refactor(ai-model): remove runtime compatibility heuristics` | 删除 provider/base URL 自动猜测；引入标准 protocol profile 和显式 override | negative search/contract tests | architect + reviewer |

**Phase Gate 1**

- 搜索核心代码中 legacy compat key，只允许 Translator 和迁移测试出现。
- v1 catalog 仍能加载。
- v2 fixture 可完整 round-trip。

### Phase 2：三个核心 Adapter 迁移

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-014 | `refactor(ai-openai): migrate chat completions contracts` | OpenAI Completions 只读取 typed protocol/dialect/routing | payload/event fixtures；tools/reasoning tests | architect + reviewer + test |
| AIQ-015 | `refactor(ai-openai): migrate responses contracts` | Responses 只读取 typed contract；统一 schema/tools/cache/session | responses fixtures；structured/tool/image tests | architect + reviewer + test |
| AIQ-016 | `refactor(ai-anthropic): migrate messages contracts` | Anthropic 只读取 typed contract；thinking/cache/tools beta 显式化 | anthropic fixtures；thinking/tool/image tests | architect + reviewer + test |
| AIQ-017 | `refactor(ai-compat): remove legacy access from core adapters` | 核心 Provider 无 `compat_bool/compat_str`；legacy helper 限定 Loader 内部 | import/search guard tests | architect |

**Phase Gate 2**

```bash
uv run pytest tests/providers -q
make check-ai
```

### Phase 3：Context、消息、Tool 归一化与 API

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-018 | `refactor(ai-context): add immutable normalized context` | 引入 `NormalizedContext/NormalizationResult`；删除 marker 依赖但暂留兼容入口 | idempotence tests；`03_typed_context.py` | architect + test |
| AIQ-019 | `refactor(ai-messages): canonicalize message inputs once` | 所有 dict 在 Parser 边界转 canonical 类型；Adapter 不再 normalize | camel/snake、role、part negative tests | architect + test |
| AIQ-020 | `feat(ai-messages): expose normalization diagnostics` | 修复、降级、签名移除产生稳定 diagnostic | diagnostic snapshot tests；advanced inspect example | architect + reviewer |
| AIQ-021 | `refactor(ai-tools): make pairing policy explicit` | strict/repair 分离；SDK 默认 pairing policy strict；repair 由调用方显式选择并产生 diagnostic | missing/orphan/duplicate/late tests；tools example | reviewer + test |
| AIQ-022 | `feat(ai-api): enforce complete capability checks` | 检查 stream/tools/reasoning/structured/temperature/image/attachment | capability matrix tests；capability failure example | architect + test |
| AIQ-023 | `refactor(ai-options): consolidate call options` | 增加通用 CallOptions；Provider-specific options 移 Advanced/deprecated | signature/type tests；complete/stream examples | architect + reviewer |
| AIQ-024 | `feat(ai-api): implement simple reasoning semantics` | Simple options 在核心映射到 CallOptions；Provider 不再有 stream_simple | cross-provider mapping tests；`06_reasoning.py` | architect + test |
| AIQ-025 | `refactor(ai-public): narrow stable root exports` | 收缩 `__all__`；Internal/Advanced 移子包；明确 deprecation policy | root API snapshot；所有主 examples | architect + docs + reviewer |

**Phase Gate 3**

- 主 examples 只 import `loushang.ai` Stable API。
- Provider Adapter 参数中不存在 raw dict context。
- Normalization 幂等测试通过。

### Phase 4：错误、Runtime、Streaming 与可观测性

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-026 | `feat(ai-errors): add a stable AI error taxonomy` | 增加异常层级和 AIErrorInfo；不迁移 Provider | serialization/redaction tests；errors example skeleton | architect + reviewer |
| AIQ-027 | `refactor(ai-errors): normalize provider failures` | HTTP/SDK/stream errors 映射 typed error；删除 `map_provider_error=str` | 401/403/429/408/5xx/unknown tests | reviewer + test |
| AIQ-028 | `refactor(ai-runtime): centralize stream execution` | ProviderRuntime 统一 task、assembler、错误和关闭；Adapter 实现 stream_raw | 三 Adapter contract tests | architect + reviewer |
| AIQ-029 | `feat(ai-runtime): add safe retry policies` | 仅首个 visible event 前重试；Retry-After、backoff、jitter | retry/no-retry tests；`09_errors_retry.py` | architect + reviewer + test |
| AIQ-030 | `feat(ai-stream): add bounded backpressure` | 有界 queue 和 async emit；慢消费者不爆内存 | stress/slow consumer tests | architect + test |
| AIQ-031 | `feat(ai-stream): add cancellation and upstream closing` | CancellationSignal；退出/取消关闭 HTTP/SDK stream | task leak/resource close tests；stream cancel example | architect + reviewer + test |
| AIQ-032 | `fix(ai-stream): stabilize terminal and result semantics` | Exactly one terminal；result raise；final_message；真实 timestamp/request ID | terminal contract tests | reviewer + test |
| AIQ-033 | `feat(ai-observability): standardize trace events` | 版本化 trace、统一 request/retry/error/cancel 事件、强制脱敏 | trace schema/redaction tests；advanced trace example | architect + reviewer |

**Phase Gate 4**

- 运行 asyncio debug 模式测试。
- 检查无 pending task warning。
- Error example 展示 typed error，不解析字符串。

### Phase 5：能力完整化

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-034 | `feat(ai-tools): support interleaved parallel calls` | 多 active tool buffers；按 ID/index 组装 | interleaved fixture tests；`05_parallel_tools.py` | architect + reviewer + test |
| AIQ-035 | `feat(ai-tools): split strict and coercing validation` | strict 默认；coerce 返回 diagnostics；补 JSON Schema 子集文档 | validation matrix tests；`04_tools.py` | reviewer + test + docs |
| AIQ-036 | `feat(ai-structured): add structured output contracts` | StructuredOutputOptions、Provider 映射、解析结果/错误 | schema/json-object tests；`07_structured_output.py` | architect + reviewer + test |
| AIQ-037 | `refactor(ai-multimodal): align text and image declarations` | 完成 image tool result；删除未实现 modality 声明 | image-only/mixed tool result tests；`08_image_input.py` | reviewer + test |
| AIQ-038 | `feat(ai-auth): secure credential storage` | CredentialStore、0600、atomic、locking、明确错误 | permission/concurrency/corrupt-file tests；advanced OAuth example | architect + reviewer + test |
| AIQ-039 | `refactor(ai-usage): separate usage and quota` | UsageObservation、PlatformQuota、Endpoint query abstraction | usage/quota fixtures；`10_usage.py` 和 advanced quota example | architect + test |

**Phase Gate 5**

```bash
uv run pytest tests/ai/contracts tests/providers -q
make check-ai
```

### Phase 6：Provider 核心收缩

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-040 | `refactor(ai-contrib): isolate OpenAI Codex integration` | Codex Provider/Auth/Options 移 `contrib`；显式注册；核心无自动依赖 | contrib registration tests；advanced Codex example | architect + reviewer |
| AIQ-041 | `remove(ai-provider): remove Azure OpenAI from core` | 删除 Adapter、Options、bootstrap、tests/catalog/docs 引用；迁移说明 | negative registration/import tests | architect + reviewer + docs |
| AIQ-042 | `remove(ai-provider): remove Bedrock from core` | 删除轻量 Bedrock 实现及引用；不再声称 stream 支持 | negative registration/import tests | architect + reviewer + docs |
| AIQ-043 | `refactor(ai-provider): freeze core protocol adapters` | Bootstrap 只注册三核心 Adapter；增加 Adapter Contract Matrix | complete provider contract suite | architect + test |

**Phase Gate 6**

- `src/loushang/ai/providers` 只含三核心生产 Adapter 及 shared helper。
- Faux 明确 test-only。
- Codex 只在显式 contrib 注册后可用。

### Phase 7：Curated Catalog 双目录迁移

先增加 `models.curated.v2.json`，逐家添加；默认仍读取 legacy catalog。全部完成后再切换，保证每个 commit 可用。

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-044 | `feat(ai-catalog): add curated catalog budgets` | 新建 v2 curated 文件、预算测试、evidence 模板；暂不切默认 | empty/skeleton schema tests | catalog + architect |
| AIQ-045 | `feat(ai-catalog): curate OpenAI models` | 加 2 个官方主力模型及 evidence | catalog fixture；generic provider smoke docs | catalog + test |
| AIQ-046 | `feat(ai-catalog): curate Anthropic models` | 加 2 个官方主力模型及 evidence | catalog fixture | catalog + test |
| AIQ-047 | `feat(ai-catalog): curate Moonshot models` | 加通用+coding 最多 2 个；消除重复 Endpoint | catalog/selection tests | catalog + test |
| AIQ-048 | `feat(ai-catalog): curate DashScope models` | 加最多 2 个；只保留一个默认地域 | catalog/selection tests | catalog + test |
| AIQ-049 | `feat(ai-catalog): add Tencent Hunyuan` | 对应 #102；官方稳定兼容 Endpoint；1 模型 | issue acceptance fixtures | catalog + test |
| AIQ-050 | `feat(ai-catalog): add Zhipu GLM` | 对应 #103；最多 2 模型 | issue acceptance fixtures | catalog + test |
| AIQ-051 | `feat(ai-catalog): add DeepSeek` | 对应 #104；最多 2 模型 | issue acceptance fixtures | catalog + test |
| AIQ-052 | `feat(ai-catalog): add MiniMax` | 对应 #105；1 模型 | issue acceptance fixtures | catalog + test |
| AIQ-053 | `feat(ai-catalog): add Doubao Volcano Ark` | 对应 #106；1 模型 | issue acceptance fixtures | catalog + test |
| AIQ-054 | `feat(ai-catalog): add Baidu Qianfan` | 对应 #107；1 模型 | issue acceptance fixtures | catalog + test |
| AIQ-055 | `feat(ai-catalog): add StepFun` | 对应 #108；1 模型 | issue acceptance fixtures | catalog + test |
| AIQ-056 | `refactor(ai-catalog): switch to the curated catalog` | 默认切 v2；删除 package 内 legacy catalog；保留压缩归档；更新 CLI | full catalog/CLI tests；`12_provider_smoke.py` | catalog + architect + reviewer |

每个 Provider commit 都必须：

- 加 evidence 文档。
- 加 Loader/Selection Fixture。
- 更新 Provider Matrix。
- 运行离线 catalog tests。
- 有凭证时运行手工 live smoke 并记录日期；无凭证不声称通过。

**Phase Gate 7**

```bash
uv run python -m loushang.ai.cli models list --json
uv run pytest tests/ai tests/providers -q
make check-ai
```

检查预算：Provider <= 11，Model <= 20。

### Phase 8：文档、CI 与最终工程门禁

| Plan-ID | Commit message | 修改内容 | 最低测试/示例 | 评审 |
|---|---|---|---|---|
| AIQ-057 | `docs(ai): publish the stable SDK guide` | 重写中英文调用、错误、工具、Reasoning、Structured、Image、Auth、Catalog 文档 | docs link/example checks | docs + reviewer |
| AIQ-058 | `examples(ai): finalize executable capability examples` | 整理编号 examples；删除重复过时示例；离线默认可运行 | 执行全部离线 examples | docs + test |
| AIQ-059 | `ci(ai): add coverage catalog and example gates` | pytest-cov、catalog linter、example runner、import boundary gate | CI 本地等价命令 | architect + test |
| AIQ-060 | `chore(ai): tighten typing and linting` | core 模块逐步 strict mypy；增加 Ruff UP/B/SIM/RUF 等审慎规则；修复而非 blanket ignore | make check-ai/full suite | architect + reviewer |
| AIQ-061 | `docs(ai): add migration guide and final scorecard` | v1->v2 catalog、root API、error semantics、Provider 删除迁移；最终评分和剩余 issue | final release checklist | architect + docs + reviewer |

---

## 21. 每个阶段的回滚点

每个 Phase 完成后创建 annotated tag 或记录 SHA：

```text
aiq-phase-0-baseline
aiq-phase-1-contracts
aiq-phase-2-adapters
aiq-phase-3-normalization
aiq-phase-4-runtime
aiq-phase-5-capabilities
aiq-phase-6-provider-scope
aiq-phase-7-catalog
aiq-phase-8-final
```

是否推送 tag 由维护者决定。不得使用不可审计的工作区备份代替 commit。

迁移策略保证：

- Phase 1：v1/v2 双读。
- Phase 2：Adapter 逐个迁移。
- Phase 7：legacy/curated 双目录，最后切换。
- 任一阶段回滚不依赖手工恢复未提交文件。

---

## 22. Phase 边界评审 Prompt

每个 Phase 完成后进行一次更宽评审：

```text
Review the full branch diff from the previous phase tag to HEAD.
Spawn one read-only subagent for each area:
1. architecture and public API boundaries;
2. correctness and error semantics;
3. streaming/concurrency/resource safety;
4. tests and examples;
5. catalog facts and migration safety, when relevant.
Wait for all agents and consolidate P0/P1/P2 findings.
Also check for cross-commit inconsistencies that one-commit reviews may miss.
Do not modify files.
```

Phase 结束不得存在跨 commit 形成的半迁移状态。

---

## 23. 最终验收清单

### 23.1 代码

- [ ] Core 仅三个协议 Adapter。
- [ ] Bedrock/Azure 不在 Core。
- [ ] Codex 位于 contrib 且显式注册。
- [ ] 核心无 Provider ID/Base URL compat 猜测。
- [ ] Built-in catalog 无 legacy compat。
- [ ] Provider 边界只接受 NormalizedContext/ProviderRequest。
- [ ] Core 无裸 `except Exception: pass`。
- [ ] Stream queue 有界。
- [ ] Cancellation 会关闭上游。
- [ ] Parallel tool calls 可交错。
- [ ] Structured output 可验证。
- [ ] Text/Image 声明和实现一致。
- [ ] OAuth 文件安全。
- [ ] Unknown pricing 不按零成本。

### 23.2 Catalog

- [ ] 原 catalog 已压缩归档并验证 SHA。
- [ ] Provider <= 11。
- [ ] Model <= 20。
- [ ] Issue #102-#108 均有 evidence 和明确状态。
- [ ] 每个模型最多一个 preferred Endpoint。
- [ ] 不含未实现 modality。
- [ ] 不确定事实已省略或标记 unknown。

### 23.3 API

- [ ] Root `__all__` 有快照。
- [ ] Full/Simple 语义明确。
- [ ] 不支持参数不会静默忽略。
- [ ] `complete()` 错误 raise typed error。
- [ ] Stable Error Code 文档化。
- [ ] Migration Guide 完整。

### 23.4 Tests

```bash
make check-ai
uv run pytest tests -q
uv run pytest tests/ai/contracts -q
uv run python scripts/ai/check_catalog.py
uv run python scripts/ai/check_examples.py
uv build
```

- [ ] 所有命令通过。
- [ ] Core coverage >= 90%。
- [ ] Adapter aggregate coverage >= 85%。
- [ ] 无 pending asyncio task。
- [ ] 无 secret trace snapshot。

### 23.5 Examples/Docs

- [ ] 全部离线 examples 可执行。
- [ ] 每项关键能力有 example。
- [ ] 主 examples 只使用 Stable API。
- [ ] Advanced examples 标记清楚。
- [ ] 中英文文档一致。
- [ ] Provider 支持矩阵与 catalog 自动校验一致。

### 23.6 Review

- [ ] 每个 AIQ commit 有一次 commit review。
- [ ] 每个 Phase 有一次 range review。
- [ ] 最终分支有一次全量 review。
- [ ] P0/P1 = 0。
- [ ] P2 全部解决或有独立 issue/ADR。

---

## 24. 最终全量评审 Prompt

```text
Perform the final owner-level review of this branch against origin/main.
Spawn read-only subagents for:
- stable API and architecture;
- message/tool normalization;
- error/retry/streaming/cancellation;
- security and credential handling;
- provider adapter consistency;
- model catalog evidence and issue acceptance;
- tests, examples, docs, and migration safety.

Wait for all agents. Check every requirement in the execution plan.
Run or inspect all final gate commands.
Return:
1. blockers;
2. non-blocking debt;
3. objective score by quality dimension;
4. release recommendation;
5. exact remaining issues.
Do not modify files.
```

---

## 25. 完成后的预期状态

完成后，`loushang.ai` 应具备以下稳定心智：

- Model 表达“调用哪个模型”。
- Capabilities 表达“调用方可以要求什么”。
- EndpointProtocol 表达“标准协议支持什么”。
- WireDialect 表达“线格式与标准有何差异”。
- Routing/Transport 表达“请求去哪里以及怎么发送”。
- NormalizedContext 是 Provider 唯一输入事实。
- Provider Adapter 只做 payload 与 RawPart 映射。
- ProviderRuntime 统一可靠性语义。
- Error、Usage、Events 对所有 Provider 一致。
- Built-in catalog 小而可信；长尾 Provider 使用 custom catalog。
- 每项能力都有测试，关键能力都有 executable example。

这比继续增加 Provider 数量更能提升整个 AI 包的长期质量、通用性和可维护性。

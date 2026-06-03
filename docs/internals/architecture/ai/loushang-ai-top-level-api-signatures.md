# Loushang AI Top-Level API Signatures

## Scope

本文档讨论 `loushang.ai` 四个顶层入口的正式签名方向：

- `stream()`
- `complete()`
- `stream_simple()`
- `complete_simple()`

本文档只讨论：

- 这四个入口的 public 参数与返回值
- full/simple 两组入口的职责关系
- `complete()` 与 `complete_simple()` 如何建立在 stream 语义之上
- cancellation / error / registry resolution 对签名的影响

本文档不讨论：

- provider-specific option types
- 某个 provider 的 payload 映射
- raw part 内部类型体系
- tool call / thinking / image 的完整事件矩阵

---

## Design Question

在当前 `loushang.ai` 已冻结 glossary、types、streaming/cancellation、registry 与 adapter strategy 后，顶层 public API 还需要回答：

1. 四个根入口是否都应存在
2. 它们的参数签名是否保持统一
3. `complete()` 与 `complete_simple()` 是否只作为 `stream().result()` 包装存在
4. `simple` 入口与完整入口之间的职责边界应如何划分

如果这一层定义不清，后续实现会出现两个问题：

- 调用方不知道该选哪组入口
- provider adapter 与 top-level API 会互相吞并职责

---

## Pi-AI Alignment

从 `pi-mono/packages/ai` 源码可以直接确认，`pi-ai` 真实导出了这四个入口：

- `stream`
- `complete`
- `streamSimple`
- `completeSimple`

直接证据包括：

- [index.ts](/home/dev/workspace/pi-mono/packages/ai/src/index.ts)
- [stream.ts](/home/dev/workspace/pi-mono/packages/ai/src/stream.ts)

其中：

- `complete()` 建立在 `stream().result()` 之上
- `completeSimple()` 建立在 `streamSimple().result()` 之上

因此，`loushang.ai` 继续采用四个顶层入口，不是额外扩展，而是与 `pi-ai` 保持对齐。
但 Python 版 `loushang.ai` 不必机械复制 `pi-ai` 的同步 stream 启动形态。

---

## Naming Decision

`loushang.ai` 在 public 函数命名上继续采用轻度 Python 化：

- `stream`
- `complete`
- `stream_simple`
- `complete_simple`

也就是说：

- 保留 `pi-ai` 的双入口语义
- 仅将函数名从 `camelCase` 转为 `snake_case`

不建议改成其他命名，例如：

- `run_stream`
- `generate`
- `generate_simple`

因为这会削弱与 `pi-ai` 的对齐关系，也会让 registry / adapter / simple options 的语义链路变得不稳定。

---

## Core Recommendation

建议冻结如下顶层签名方向：

```python
async def stream(
    model: ModelDefinition,
    context: Context,
    options: object | None = None,
) -> AssistantMessageEventStream: ...


async def complete(
    model: ModelDefinition,
    context: Context,
    options: object | None = None,
) -> AssistantMessage: ...


async def stream_simple(
    model: ModelDefinition,
    context: Context,
    options: object | None = None,
) -> AssistantMessageEventStream: ...


async def complete_simple(
    model: ModelDefinition,
    context: Context,
    options: object | None = None,
) -> AssistantMessage: ...
```

这里的重点不是 Python typing 语法细节，而是四个稳定 public contract 事实：

1. 四个入口都以 `model + context + options` 为统一参数骨架
2. 两个 stream 入口在 `await` 后都返回 `AssistantMessageEventStream`
3. 两个 complete 入口都返回 `AssistantMessage`
4. 当前顶层主签名仍保持 `options: object | None`，但 public surface 已开始导出初步 `StreamOptions` / provider-specific options family

---

## Parameter Structure

### `model`

四个入口都应显式接收 `model: ModelDefinition`。

理由：

- 模型绑定 endpoint 的 `api` 事实是 registry resolution 的唯一稳定主轴；当前实现通过 `resolve_model_api(model)` 读取
- top-level API 不应隐式从 config 或环境推断目标 model

### `context`

四个入口都应显式接收 `context: Context`。

理由：

- `loushang.ai` 的输入语义核心就是统一 `Context`
- 不应把 `system_prompt`、`messages`、`tools` 拆成多个根参数
- `Context` 现已作为正式 AI 输入语义进入代码主链，并与 `pi-ai` 的 `systemPrompt + messages + tools` 语义保持对应

### `options`

四个入口都保留第三参数 `options`，并保持可选。

建议：

- 当前 public surface 先保持 `options: object | None`
- full/simple 两组入口继续共享统一参数骨架
- provider-specific options family 已开始导出，但暂不提升为根入口主签名的一部分

这里的重点是先冻结顶层调用骨架，而不是过早冻结 provider-specific options 类型家族。

---

## Full vs Simple

### Full Entrypoints

`stream()` 与 `complete()` 是完整统一入口。

它们的职责是：

- 提供最稳定、最通用的 public contract
- 直接承接统一 `options`
- 为所有 `ApiProvider` 提供共同最低调用面

因此，full 入口是：

- registry / adapter / streaming contract 的主入口

### Simple Entrypoints

`stream_simple()` 与 `complete_simple()` 是统一简化入口。

它们的职责是：

- 提供 reasoning 等统一简化能力映射
- 把调用方常见需求压缩到一组更窄语义中
- 为跨 provider 的常用调用提供更直接接口

因此，simple 入口不是“更弱版本”的 full 入口，而是：

- 在统一 options family 基础上增加跨 provider 的简化语义

---

## Return Types

### `stream()` / `stream_simple()`

两者都返回：

- `AssistantMessageEventStream`

原因是：

- streaming public contract 已经被前文冻结
- stream 入口不应返回 provider 私有 stream 对象
- event stream 是 `loushang.agent` 未来消费 `loushang.ai` 的主边界

### `complete()` / `complete_simple()`

两者都返回：

- `AssistantMessage`

原因是：

- complete 入口的职责就是直接收敛最终 message
- 调用方不应再从 `complete()` 返回值里自行管理事件流

---

## Completion-On-Stream Rule

建议显式冻结如下规则：

- `complete()` 建立在 `await stream(...); await stream.result()` 之上
- `complete_simple()` 建立在 `await stream_simple(...); await stream.result()` 之上

这条规则已经被 streaming validation 支持：

- [loushang-ai-streaming-validation.md](/home/dev/workspace/loushang/docs/architecture/ai/validation/loushang-ai-streaming-validation.md)

这样设计的价值在于：

1. complete 语义不需要独立维护另一套收敛逻辑
2. mixed consumption 与 result 收敛可以共享同一模型
3. streaming contract 成为统一根语义，而不是附属能力

因此，不建议为 `complete()` 另起一条完全独立的 provider 调用链。

---

## Resolution Rule

四个顶层入口都应遵守同一条 resolution rule：

1. 通过 `resolve_model_api(model)` 读取绑定 endpoint 的 `api`
2. 通过 `ApiProvider registry` 解析 provider
3. `await` 调用对应 `stream()` 或 `stream_simple()` provider method
4. 若是 complete 入口，则再调用 `.result()`

这意味着：

- top-level API 不负责 provider guessing
- top-level API 不按 `provider` 品牌回退
- top-level API 不做多候选动态路由

如果 provider 未注册，应在此层稳定失败，而不是延迟到更深层。

---

## Error and Cancellation Surface

顶层签名层面应明确遵守当前 cancellation 决策：

- 取消通过 `options.signal` 进入
- `signal` 的 public 语义是 `AbortSignalLike`
- 检测到取消后，最终协议语义应收敛为 `aborted`

因此，建议 public 行为保持如下方向：

- `stream()` / `stream_simple()` 返回的 event stream 以协议事件表达错误与终止
- `complete()` / `complete_simple()` 返回的 `AssistantMessage.stop_reason` 可为 `aborted` 或 `error`

这里延续当前已冻结的原则：

- 尽量把失败编码进统一协议结果
- 而不是让 provider/runtime 异常主导 public contract

---

## Sync vs Async Boundary

建议在 Python 版 `loushang.ai` 中采用显式 async-start 边界：

- `stream()` / `stream_simple()` 为 `async def`
- 它们在完成 provider start / stream object 建立后返回 `AssistantMessageEventStream`
- `complete()` / `complete_simple()` 保持 `async def`

这样做的原因是：

1. provider start 在 Python 中本来就是 async 边界
2. 不再要求同步 `stream()` 隐式依赖某个运行中的 event loop
3. provider task / HTTP stream / cancellation 责任更清楚
4. public contract 仍然保持“stream handle + result() 收敛”的统一模型

因此，当前冻结结论是：

- `stream()` 不是普通同步工厂函数
- `stream()` 是显式 async start API
- `complete()` 继续建立在 stream 语义之上，但不再是同步拿到 stream handle

---

## Option Family Boundaries

建议在签名层面保持如下克制：

- full 入口与 simple 入口共享统一 `options` 参数位
- 顶层 public surface 先不冻结独立 options 类型名
- provider-specific option types 不在当前根入口中显式展开

这意味着：

- 顶层文档可以承认 provider options 的扩展方向
- 但不应在当前阶段把 `AnthropicOptions`、`OpenAIResponsesOptions` 等类型直接提升为根入口主签名的一部分

这与当前 handoff 保持一致。

---

## Non-Goals

本阶段明确不进入以下设计：

- 顶层自动选择默认 model
- 顶层 config-driven model injection
- 多 provider fallback
- 顶层 routing policy
- 将 provider-specific options 暴露为根入口 overload

这些都应留给后续实现或上层系统决定。

---

## Recommendation

建议冻结如下方向：

1. `stream` / `complete` / `stream_simple` / `complete_simple` 四个顶层入口全部保留
2. 四者统一采用 `model + context + options` 参数骨架
3. stream 入口统一在 `await` 后返回 `AssistantMessageEventStream`
4. complete 入口统一返回 `AssistantMessage`
5. `complete()` 建立在 `await stream(...); await result()` 之上
6. `complete_simple()` 建立在 `await stream_simple(...); await result()` 之上
7. full/simple 的差异只体现在 options family 与语义层次，不体现在完全不同的调用模型

---

## Open Questions

在进入正式 spike 或实现前，仍有少量问题需要后续细化：

1. `stream_simple()` 在 provider 未实现 simple adapter 时是否允许统一降级
2. 顶层是否需要在后续补出正式 `StreamOptions` / `SimpleStreamOptions` 类型家族
3. 顶层 error family 是否需要独立命名

---

## Next Step

在此基础上，下一步最自然进入：

1. 一个最小 provider spike
2. `raw parts` 内部类型体系
3. tool call / thinking / image 的 assembler 事件矩阵

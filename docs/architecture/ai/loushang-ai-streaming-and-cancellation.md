# Loushang AI Streaming and Cancellation

## Scope

本文档讨论 `loushang.ai` 在 Python 中的 streaming 与 cancellation 设计边界。  
核心问题是：`loushang.ai` 是否应该整体绑定 `asyncio`，以及 public API 应该暴露哪一层语义。

本文档只讨论：

- `AssistantMessageEventStream`
- `stream()` / `complete()`
- cancellation / abort 语义
- `asyncio` 与 public API 的关系

本文档不讨论：

- provider 具体实现细节
- `AgentLoop` 调度
- tool orchestration policy
- channel boundary protocol

---

## Design Question

`pi-ai` 在 TypeScript 中整体采用 async / streaming 模型。  
当它被翻译到 Python 时，需要决定：

1. `loushang.ai` 是否整体绑定 `asyncio`
2. `signal` 在 Python 中如何表达
3. `AssistantMessageEventStream` 应该是纯协议对象，还是 `asyncio` 风格运行对象
4. cancellation 应该作为 runtime 机制，还是协议语义

---

## Why This Matters

这个问题之所以关键，是因为它会同时影响：

1. `loushang.ai` 的 public API
2. `loushang.ai`  的 types
3. provider streaming adapter 的实现方式
4. `loushang.agent` 未来如何消费 `loushang.ai`

如果这一层过早绑定到具体 runtime 机制，就会把本应属于 `agent` 层的调度与取消策略提前固化在 `ai` 层。

---

## Pi-AI Semantics

`pi-ai` 的 public contract 主要建立在这些抽象之上：

- `Promise`
- `AsyncIterable`
- `AbortSignal`
- `AssistantMessageEventStream`

它看起来“整体 async”，但它依赖的是 JavaScript / TypeScript 的平台级异步抽象，而不是某个框架专属 runtime。

换句话说，`pi-ai` 绑定的是：

- 语言层 async 模型
- 平台层 streaming / abort 抽象

而不是一个狭义的“某个实现 runtime”。

---

## Kimi-CLI Pattern

`kimi-cli` 的实现提供了一个很重要的参考，但它的职责层级与 `loushang.ai` 不同。

### 1. Provider Stream Interface

在 `kosong.chat_provider` 中，streaming interface 主要表现为：

- `ChatProvider.generate(...) -> StreamedMessage`
- `StreamedMessage.__aiter__() -> AsyncIterator[...]`

这说明它在 provider 边界上主要绑定的是：

- Python async iterator

而不是直接暴露 `asyncio.Event` 或 `asyncio.Task`。

### 2. Runtime and Cancellation

`kimi-cli` 的上层 runtime 明确大量使用：

- `asyncio.Event`
- `asyncio.create_task()`
- `task.cancel()`
- `asyncio.CancelledError`

这说明：

- `kimi-cli` 整体上是绑定 `asyncio` 的
- 但这种绑定主要发生在 app / soul / runtime / tool execution 层
- 而不是把 `asyncio` 直接当作 provider protocol 的核心语义

### 3. Key Takeaway

`kimi-cli` 证明了两件事：

1. Python async streaming 完全可以围绕 async iterator 工作
2. 产品 runtime 可以绑定 `asyncio`

但它不能自动推出：

- `loushang.ai` 的 public API 也必须深度绑定 `asyncio`

因为 `loushang.ai` 的职责比 `kimi-cli runtime` 更窄。

---

## LiteLLM Pattern

LiteLLM 提供了另一种可参考但不应直接照搬的路径。

### 1. Streaming Shape

LiteLLM 更偏向：

- 统一 provider 调用层
- OpenAI 风格输入输出格式
- streaming iterator / async iterator

它的公开重心更接近：

- `completion(..., stream=True)`
- 返回 chunk iterator

而不是：

- 高阶 assistant event stream
- `result()` 收敛最终 message
- 独立的 cancellation 协议对象

### 2. Cancellation Shape

公开文档层面没有像 `pi-ai` 那样把取消建模为统一 public 协议。  
更接近：

- 调用方通过 Python async/sync 调用模型管理生命周期
- 底层取消依赖 runtime / HTTP client / task 取消能力

### 3. Key Takeaway

LiteLLM 说明：

- 统一 provider 接入层可以只做到 chunk iterator 级别
- 这很适合通用调用库

但对于 `loushang.ai` 来说，这种公开层级偏低。  
`loushang.ai` 未来需要给 `loushang.agent` 提供稳定 streaming boundary，因此不宜只停留在 chunk iterator 语义。

---

## Option A: Sync Stream Handle + Runtime-Neutral Contract

做法：

- `stream()` / `stream_simple()` 为同步函数
- 返回 `AssistantMessageEventStream`
- provider start 通过额外 bridge 隐式完成

### 优点

- public shape 更接近 `pi-ai`
- `complete()` 可以继续表达为 `stream().result()` 语义

### 风险

- Python 里容易落成隐式 loop 假设
- provider start / task ownership 容易变得不清楚
- 如果实现不谨慎，会出现“同步返回，但内部依赖运行中 event loop”的问题

---

## Option B: Explicit Async-Start Public Contract

做法：

- `stream()` / `stream_simple()` 为 `async def`
- provider start 显式成为 public async 边界
- `signal` 保留字段名，但定义为 Python 最小取消协议
- 默认实现内部可以使用 `asyncio`
- `asyncio.Task` / `asyncio.Queue` / `asyncio.Event` 不进入 public contract

### 优点

- 对 Python 实现更自然
- provider start / task ownership / HTTP stream lifecycle 更清楚
- 不再要求同步 `stream()` 隐式依赖运行中的 event loop
- 更适合在 provider 边界直接建立 cancellation 观察点

### 风险

- 与 `pi-ai` 的同步 `stream()` public shape 不再完全一致
- `complete()` / `complete_simple()` 在文档和心智模型上需要多一段 `await stream(...)`
- 调用方需要接受“先 await stream handle，再消费 stream”的模型

---

## Recommendation

建议采用 **Option B**：

**`loushang.ai` 使用显式 async-start public contract，但不把 `asyncio` 类型写进 public contract。**

具体原则如下：

### 1. Streaming Model

`AssistantMessageEventStream` 绑定 Python async iteration 语义。

也就是说：

- `await stream()` 返回一个可异步迭代的 event stream 对象
- 这个对象在结束时可以收敛到最终 `AssistantMessage`

### 2. Cancellation Model

保留 `signal` 字段名，以对齐 `pi-ai`。

但：

- `signal` 不直接定义为 `asyncio.Event`
- 它应建模为 `AbortSignalLike`
- `AbortSignalLike` 只表达“调用是否应被取消”

### 3. Abort Semantics

取消属于协议语义，而不是只属于 runtime 机制。

一旦检测到取消，应映射为：

- `StopReason = "aborted"`
- `ErrorEvent(reason="aborted")`

而不是仅仅依赖：

- `CancelledError`
- `task.cancel()`

### 4. Implementation Model

v1 默认实现可以使用：

- `asyncio`
- `asyncio.create_task()`
- `asyncio.Queue`
- `asyncio.Event`

但这些对象不应成为 `loushang.ai` 根入口和核心类型定义的一部分。
显式 async-start 只意味着 provider start responsibility 外移，并不意味着 public contract 暴露 `asyncio.Task` 或 event loop policy。

---

## Boundary Decision

建议明确划分：

### `loushang.ai` 负责

- model/provider streaming abstraction
- assistant event stream abstraction
- abort 语义映射
- provider payload streaming

### `loushang.ai` 不负责

- task lifecycle orchestration
- 多任务取消传播策略
- event loop policy
- runtime scheduling semantics

这些属于 `loushang.agent` 或更上层 runtime。

---

## AssistantMessageEventStream Shape

当前建议采用：

- public 单对象
- internal reader/writer 分离

### Public Shape

`AssistantMessageEventStream` 对外只暴露消费能力。

建议 public methods：

- `__aiter__()`
- `result()`

说明：

- `await stream()` 返回该对象
- 调用方可以异步迭代事件
- 调用方也可以通过 `result()` 收敛为最终 `AssistantMessage`

### Internal Shape

内部允许存在 producer-side companion，但不作为稳定 public contract 暴露。

建议通过内部 factory 创建：

- `create_assistant_message_event_stream() -> (stream, writer)`

其中：

- `stream` 是只读消费对象
- `writer` 是内部生产对象

### Writer Responsibilities

`writer` 只负责：

- `push(event)`
- `finish(message)`
- `fail(message)`

说明：

- `writer` 不负责 tool call 组装
- `writer` 不负责 partial message 维护
- `writer` 不负责 usage / response_id 聚合
- 这些职责属于 raw assembler

### Why This Shape

这样设计的原因是：

1. 保持 `pi-ai` 风格的 public event stream contract
2. 避免把 `push()` / `end()` 这类生产端方法泄漏到 public API
3. 允许内部 assembler 与 provider adapter 清晰分工
4. 为默认 `asyncio` 实现保留足够空间，而不污染 public contract

---

## Internal Streaming Layers

当前建议 `loushang.ai` 内部采用三层流式结构：

1. provider SDK stream
2. raw part stream
3. assistant message event stream

### Provider SDK Stream

上游模型 SDK 的原始 chunk / delta / event。

### Raw Part Stream

内部私有中间层。

它的职责是把不同 provider 的 SDK stream 收敛到一组统一原始片段。  
这一层可以借鉴 `kimi-cli` 的 part / merge 思路，但不应进入 public API。

### Assistant Message Event Stream

对外 public contract。

这一层严格对齐 `pi-ai` 的 assistant event 语义，并作为 `loushang.agent` 消费 `loushang.ai` 的主要流式边界。

### Raw Assembler Responsibilities

raw assembler 负责：

- 将 raw parts 组装为标准 `AssistantMessageEvent`
- 维护 partial `AssistantMessage`
- 分配与维护 `content_index`
- 收敛最终 `AssistantMessage`
- 调用内部 writer 输出事件与最终结果

它不负责：

- 调用 provider SDK
- tool execution
- agent scheduling
- channel projection

### Provider Adapter Responsibilities

provider adapter 负责：

- 发起上游 SDK 请求
- 迭代 SDK stream
- 将 SDK stream 翻译为 raw parts
- 将 raw parts 交给 assembler
- 处理 provider-specific payload/options 映射

它不负责：

- 直接维护 public assistant event 组装规则
- 自己定义 partial message 生命周期
- 对外暴露 provider 私有 streaming 语义

### Comparison Summary

- `kimi-cli` 更适合作为内部实现参考：
  - async iterator
  - raw parts
  - merge 思路
  - `asyncio` runtime 取消

- LiteLLM 更适合作为 lower-level provider adapter 参考：
  - provider-normalized chunk iterator
  - OpenAI 风格统一输入输出

- `pi-ai` 更适合作为 `loushang.ai` 的 public contract 参考：
  - assistant event stream
  - `result()` 收敛
  - 取消作为协议语义的一部分

因此建议：

- public contract 对齐 `pi-ai`
- internal streaming 结构吸收 `kimi-cli`
- provider adapter lower-level shape 可参考 LiteLLM

---

## Practical Rule

一条简单规则可以帮助实现时不跑偏：

**凡是必须出现在 `loushang.ai.types` 或 `loushang.ai.__init__` 的对象，不应直接依赖 `asyncio` 具体类型。**

而：

**凡是只存在于 `stream.py`、provider adapter、内部 event stream 实现中的对象，可以使用 `asyncio`。**

---

## Open Questions

下一步需要继续明确：

1. `AssistantMessageEventStream` 的 Python 形态
   - async iterable + `result()`
   - 还是 wrapper object + internal queue

2. `AbortSignalLike` 的最小协议长什么样
   - 当前建议：`cancelled: bool`
   - 是否需要兼容 `is_cancelled()` 形式的适配层

3. provider 实现应在哪些边界检查取消
   - 调用前
   - streaming loop 中
   - 收敛结果前

4. `complete()` 在取消情况下是否总是收敛为 `AssistantMessage`
   - 还是允许直接抛出特定异常

---

## Current Decision

当前建议冻结为：

1. `loushang.ai` 绑定 Python async iteration
2. `loushang.ai` 不把 `asyncio` 深度写入 public contract
3. `loushang.ai` 默认实现允许基于 `asyncio`
4. cancellation 作为协议语义保留在 public API 中
5. `AssistantMessageEventStream` 对外只暴露读侧接口
6. internal streaming 采用 `provider SDK stream -> raw part stream -> assistant event stream` 三层结构
7. `AbortSignalLike` 当前建议采用最小只读协议：`cancelled: bool`

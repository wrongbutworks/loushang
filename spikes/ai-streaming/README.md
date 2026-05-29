# AI Streaming Spike

## Goal

这个 spike 用于技术验证 `loushang.ai` 当前关于 streaming 与 cancellation 的关键设计是否可行。

本 spike 只验证：

- `AssistantMessageEventStream` 的 Python 对象形态
- internal reader / writer 分离是否成立
- `AbortSignalLike` 的最小语义是否足够
- `aborted` 是否能正确映射到最终 `AssistantMessage`
- `complete()` 是否可以自然建立在 `stream().result()` 之上

本 spike 不验证：

- 真实 provider SDK 接入
- `ApiProvider` registry
- `AgentLoop`
- channel protocol
- tool execution orchestration

## Design Hypothesis

当前要验证的设计假设是：

1. public contract 使用 `AssistantMessageEventStream`
2. `AssistantMessageEventStream` 对外只暴露：
   - `__aiter__()`
   - `result()`
3. internal implementation 采用 reader / writer 分离
4. internal stream 通过 factory 创建：
   - `(stream, writer)`
5. cancellation 保留 `signal` 字段名
6. `signal` 使用最小协议：
   - `cancelled: bool`
7. 内部流式结构采用三层：
   - provider SDK stream
   - raw part stream
   - assistant message event stream

## Spike Structure

建议在本目录中使用以下最小文件结构：

```text
spikes/ai-streaming/
  README.md
  types.py
  event_stream.py
  abort_signal.py
  assembler.py
  demo.py
```

## File Responsibilities

### `types.py`

定义这次 spike 需要的最小协议对象：

- `TextContent`
- `AssistantMessage`
- `StopReason`
- `StartEvent`
- `TextStartEvent`
- `TextDeltaEvent`
- `TextEndEvent`
- `DoneEvent`
- `ErrorEvent`

### `event_stream.py`

定义：

- `AssistantMessageEventStream`
- internal writer/prodcer companion
- `create_assistant_message_event_stream()`

验证重点：

- `async for` 是否自然
- `await result()` 是否自然
- stream 结束后行为是否明确

### `abort_signal.py`

定义最小取消信号对象：

- `AbortSignalLike`
- 一个简单实现，例如 `ManualAbortSignal`

验证重点：

- `cancelled: bool` 是否足够
- 不依赖 `asyncio.Event` 是否仍然清楚

### `assembler.py`

定义一个最小 assembler，把内部 raw parts 组装成标准 `AssistantMessageEvent`。

建议只支持最小 happy path：

- text start
- text delta
- text end
- done
- aborted

验证重点：

- assembler 是否适合承担 partial message 维护
- writer 是否只需要 `push / finish / fail`

### `demo.py`

提供最小运行入口，包含 3 个场景：

1. 正常文本流完成
2. 中途取消
3. 先消费部分事件，再调用 `result()`

## Validation Scenarios

### Scenario 1: Normal Completion

目标：

- `async for event in stream` 能按顺序拿到事件
- `await stream.result()` 返回最终 `AssistantMessage`
- 最终 `stop_reason = "stop"`

### Scenario 2: Aborted Mid-Stream

目标：

- 外部将 `signal.cancelled` 设为 `True`
- assembler / stream 检测到取消
- 产生 `ErrorEvent(reason="aborted")`
- `await stream.result()` 返回最终 `AssistantMessage`
- 最终 `stop_reason = "aborted"`

### Scenario 3: Mixed Consumption

目标：

- 先消费部分事件
- 再调用 `await stream.result()`
- 结果仍然正确收敛

### Scenario 4: Reader/Writer Separation

目标：

- public 消费方不需要接触 writer
- assembler 可以只依赖 writer 的最小接口
- stream object 本身不需要公开 `push()` / `end()`

### Scenario 5: Event Throughput Smoke Test

目标：

- 验证 `AssistantMessageEventStream + writer + assembler` 在大量小事件下没有明显结构性问题
- 验证事件消费与最终 `result()` 收敛不会互相冲突

建议方式：

- 模拟约 `10_000` 个 `text_delta` 事件
- 单消费者 `async for` 消费
- 最后调用 `await stream.result()`

关注点：

- 是否稳定跑完
- 是否正确收敛最终 `AssistantMessage`
- 是否出现队列卡死、结束边界混乱或明显不合理的耗时

说明：

- 这是 smoke-level 性能验证
- 目标是排除明显错误设计
- 不作为严格 benchmark 或最终性能结论

## Acceptance Criteria

如果以下判断都成立，就说明当前设计方向基本可行：

1. `AssistantMessageEventStream` 的 public 形态自然可用
2. internal `(stream, writer)` 比单对象读写合一更清楚
3. `cancelled: bool` 足以表达 cancellation 语义
4. `aborted` 可以稳定映射到最终 `AssistantMessage`
5. `complete()` 可以自然建立在 `stream().result()` 之上
6. spike 实现不需要把 `asyncio.Event` 写入 public type surface
7. 在大量小事件下，没有暴露出明显结构性性能问题

## Decision After Spike

如果 spike 验证通过，下一步再继续：

1. `ApiProvider` registry 设计
2. `stream()` / `complete()` 顶层签名设计
3. provider adapter 与 raw assembler 的正式模块边界

如果 spike 验证不通过，再回退并调整：

- `AssistantMessageEventStream` 形态
- reader / writer 分离策略
- `AbortSignalLike` 设计

## Run

在本目录下直接运行：

```bash
python3 demo.py
```

# pi-agent 架构分析

## 说明

用户请求中提到 `pi-mono/packages/pi-agent`，但当前仓库实际存在的是 `pi-mono/packages/agent`，其 npm 包名为 `@mariozechner/pi-agent-core`。本文基于该实际包路径进行分析，并将其视为本次所指的 `pi-agent`。

## 包定位

- 包路径：`pi-mono/packages/agent`
- npm 名称：`@mariozechner/pi-agent-core`
- 描述：通用 Agent Core，提供传输抽象、状态管理、工具执行与事件流能力
- 直接依赖：`@mariozechner/pi-ai`

这个包是一个“状态化 Agent 运行时内核”，职责不是提供具体业务工具，也不是提供 UI，而是把大模型调用、上下文管理、工具执行、事件派发和代理传输组合成统一运行循环。

## 模块划分

### 1. 对外入口层

文件：

- `src/index.ts`

职责：

- 统一导出 `Agent`
- 导出低层循环 `agentLoop` / `agentLoopContinue`
- 导出代理流工具 `streamProxy`
- 导出全部类型定义

这层非常薄，主要负责公共 API 收口。

### 2. 状态化封装层

文件：

- `src/agent.ts`

职责：

- 提供 `Agent` 类，封装完整生命周期
- 管理运行时状态 `AgentState`
- 管理订阅者 `subscribe()`
- 管理 steering / follow-up 两类消息队列
- 把 `prompt()` / `continue()` 请求转换为底层 loop 执行
- 将 loop 事件折叠回内部状态

这是包的主入口，也是最重要的编排层。

### 3. 无状态循环层

文件：

- `src/agent-loop.ts`

职责：

- 实现低层 Agent loop
- 负责每轮 LLM 请求前的上下文转换
- 负责 Assistant 响应流式消费
- 负责工具调用预处理、执行、收尾
- 负责 turn / message / tool execution 事件序列输出

可以把它理解为纯运行引擎；`Agent` 只是给这个引擎补上“状态持久化、队列、订阅者和 API 外观”。

### 4. 类型与协议层

文件：

- `src/types.ts`

职责：

- 定义 `AgentMessage`、`AgentState`、`AgentContext`
- 定义 `AgentTool`、`AgentToolResult`
- 定义 `AgentEvent`
- 定义 loop 配置、hook、工具执行模式和可扩展消息协议

这一层决定了架构的稳定边界，是整个包的协议中心。

### 5. 代理传输适配层

文件：

- `src/proxy.ts`

职责：

- 提供 `streamProxy()` 适配器
- 将服务端代理返回的 SSE/JSON 事件重建为本地 `AssistantMessageEvent`
- 对带宽优化后的 proxy event 进行 partial message 重组

这层让 Agent 既能直连 provider，也能通过服务端代理访问模型。

## 核心对象关系

```text
调用方
  -> Agent.prompt()/continue()
  -> Agent.createLoopConfig()/createContextSnapshot()
  -> runAgentLoop()/runAgentLoopContinue()
  -> streamAssistantResponse()
  -> pi-ai streamSimple()/自定义 streamFn/streamProxy()
  -> AssistantMessage 流
  -> executeToolCalls()
  -> ToolResultMessage
  -> Agent.processEvents()
  -> AgentState + subscribers
```

这说明它采用的是“状态包装器 + 无状态执行引擎”的双层设计，而不是把所有行为都塞进一个大类里。

## 运行时主流程

### 1. prompt 阶段

`Agent.prompt()` 支持三类输入：

- 字符串
- 单条 `AgentMessage`
- 多条 `AgentMessage`

字符串会被规范化为 `user` 消息；图片会拼接到同一条 user content 中。

### 2. 生命周期管理

`Agent.runWithLifecycle()` 会：

- 建立 `AbortController`
- 标记 `isStreaming = true`
- 清空上一次错误
- 执行底层 loop
- 在异常时构造失败 assistant message
- 在 finally 中统一收尾

这让 `Agent` 具备明确的运行边界和错误兜底语义。

### 3. 进入低层 loop

`runAgentLoop()` / `runAgentLoopContinue()` 会：

- 初始化当前 context 副本
- 发出 `agent_start` / `turn_start`
- 对新 prompt 先发 `message_start` / `message_end`
- 进入 `runLoop()`

### 4. runLoop 双层循环

`runLoop()` 采用两层 while：

- 内层处理当前轮次中的 assistant 回复、工具调用和 steering 消息
- 外层在 agent 即将停止时检查 follow-up 消息，必要时继续工作

这意味着该 Agent 不只是“问一次答一次”，而是支持：

- 中途 steering
- 结束前 follow-up
- 多轮工具驱动继续执行

### 5. 上下文转换边界

真正调用模型前，`streamAssistantResponse()` 会依次执行：

1. `transformContext(messages)`
2. `convertToLlm(messages)`
3. 构造 LLM `Context`
4. 调用 `streamFn`

这是本包最关键的架构边界之一：

- `AgentMessage[]` 是应用层上下文
- `Message[]` 是模型层上下文

因此这个库天然支持在 Agent transcript 中混入 UI 消息、通知消息或自定义消息类型，再在 `convertToLlm` 阶段过滤或转换掉。

## 消息模型设计

### AgentMessage 是扩展点

`AgentMessage = Message | CustomAgentMessages[...]`

这里通过 declaration merging 支持外部扩展消息类型。也就是说，框架并不强迫所有消息都直接可喂给 LLM。

这带来两个明显好处：

- transcript 可以作为“应用级对话状态”
- LLM 输入可以作为“运行时投影视图”

这是一个很好的分层：应用层消息模型和模型层消息模型被显式分离。

### State 是可变但有边界的

`AgentState` 的 `tools` 与 `messages` 使用 accessor，并在赋值时复制顶层数组。这样做的目的有两个：

- 避免外部把同一数组引用直接塞进内部状态
- 允许调用方继续直接 mutate 当前状态数组

这是偏实用主义的设计，不是完全不可变架构，但它保持了最低限度的引用隔离。

## 事件驱动架构

### 事件分类

`AgentEvent` 大致分为四类：

- Agent 生命周期：`agent_start` / `agent_end`
- Turn 生命周期：`turn_start` / `turn_end`
- Message 生命周期：`message_start` / `message_update` / `message_end`
- Tool 生命周期：`tool_execution_start` / `tool_execution_update` / `tool_execution_end`

### 事件的作用

这个设计不是为了日志而已，而是为了让 UI、监控和外部控制器都能订阅同一套运行协议。

`Agent.processEvents()` 一边根据事件折叠内部状态，一边按注册顺序 await 所有监听器。这意味着：

- 订阅者可以可靠感知完整顺序
- `agent_end` 发出后，仍要等订阅者完成，运行才算真正 idle

这种“事件先于 idle 完成”的语义对 UI 和宿主系统很关键。

## 工具执行架构

### 执行模式

工具执行支持两种模式：

- `sequential`
- `parallel`，默认值

`parallel` 模式并不是简单并发，而是：

1. 先按 assistant 原始顺序逐个做 preflight
2. 把可运行的调用并发执行
3. 最终结果仍按原始顺序回收并发出

这个策略兼顾了三件事：

- schema 校验和拦截逻辑的确定性
- 实际执行阶段的吞吐量
- 对模型而言稳定的结果顺序

### 三段式工具调用

每次工具调用可拆为：

1. `prepareToolCall()`
2. `executePreparedToolCall()`
3. `finalizeExecutedToolCall()`

对应职责：

- prepare：找工具、预处理参数、schema 校验、执行 `beforeToolCall`
- execute：真正调用工具，并支持中间更新 `tool_execution_update`
- finalize：执行 `afterToolCall`，再产出最终 `ToolResultMessage`

这是一个很清晰的流水线设计，扩展点位置也合理。

### Hook 设计

`beforeToolCall`：

- 在参数校验后执行
- 可以阻断工具调用
- 适合权限控制、审计、危险操作拦截

`afterToolCall`：

- 在工具执行后、事件落地前执行
- 可以覆写 `content` / `details` / `isError`
- 适合统一后处理、脱敏、补充元数据

这两个 hook 把“策略层”从“执行层”中解耦出来了，是架构上非常重要的一笔。

## 队列与交互控制

`Agent` 内置两套队列：

- steeringQueue：当前 turn 完成后尽快插入
- followUpQueue：在 agent 原本将停止时再注入

它们都有两种 drain 策略：

- `one-at-a-time`
- `all`

这说明该包不仅服务于简单聊天，还明显在面向更复杂的人机协作流程，例如：

- 用户在 agent 工作中途追加指令
- agent 完成当前任务后再处理排队任务

## 传输抽象

默认情况下，Agent 使用 `@mariozechner/pi-ai` 的 `streamSimple`。

但通过 `streamFn` 注入和 `streamProxy()` 适配，它把传输层做成了可替换模块：

- 直连 provider
- 服务端代理
- 自定义流实现

`proxy.ts` 的关键价值不是 HTTP 转发本身，而是把“代理协议”重建为标准 `AssistantMessageEvent`，从而不污染上层 loop。

这意味着整体架构对传输来源是低耦合的。

## 测试结构反映出的架构意图

测试主要分三层：

- `test/agent.test.ts`
  - 验证 `Agent` 状态封装、订阅、abort、idle 语义
- `test/agent-loop.test.ts`
  - 验证低层 loop、消息转换、上下文转换、自定义消息兼容性
- `test/e2e.test.ts`
  - 通过 faux provider 验证真实交互链路和工具执行

从测试分层可以看出作者有意把：

- 纯运行引擎
- 有状态封装
- 集成行为

拆成三种不同验证维度。这个分层和源码结构是一致的。

## 依赖方向

```text
调用方 / UI / 业务宿主
  -> @mariozechner/pi-agent-core
      -> agent.ts
      -> agent-loop.ts
      -> proxy.ts
      -> types.ts
          -> @mariozechner/pi-ai
```

包本身不依赖任何上层 UI 或业务实现；上层只需要提供：

- model
- tool definitions
- 可选的自定义消息转换
- 可选的 hook
- 可选的代理流函数

因此它是标准的“可嵌入运行时核心”。

## 架构优点

- 运行时状态与无状态执行引擎分离，职责清晰
- 应用级消息与 LLM 消息分层，扩展性强
- 工具执行流水线清楚，hook 插入点自然
- 事件协议完整，适合 UI 和宿主系统消费
- 传输层可替换，不绑定单一 provider 访问方式
- 队列模型支持复杂交互，不局限于单轮问答

## 架构上的注意点

- `AgentState` 不是深不可变对象，调用方仍可能直接 mutate 当前消息数组内容，需要宿主侧自律
- `convertToLlm` / `transformContext` / `getApiKey` 等回调在注释中要求“不要抛错”，但框架层主要依赖调用方遵守约定
- `parallel` 工具执行虽然并发，但 preflight 仍串行，工具很多时前置校验可能成为瓶颈
- `processEvents()` 对 listener 是串行 await，优点是顺序稳定，代价是慢 listener 会直接拖慢整体 run 完成

## 结论

`pi-agent` 对应的这个包，本质上是一个以 `AgentMessage` 为中心的 Agent Runtime Core。它通过：

- `Agent` 提供状态与生命周期外观
- `agent-loop` 提供无状态执行引擎
- `types` 提供稳定协议边界
- `proxy` 提供可替换传输适配

构成了一套适合 SDK、CLI、UI 宿主和代理后端复用的核心架构。

如果后续要继续扩展这个包，最合理的方向通常不是往 `Agent` 类里继续堆功能，而是沿着现有边界扩展：

- 在 `types.ts` 增加协议
- 在 hook 上扩展策略能力
- 在 `transformContext` / `convertToLlm` 上实现更强的上下文投影
- 在 `streamFn` / `proxy.ts` 上接入更多传输方式

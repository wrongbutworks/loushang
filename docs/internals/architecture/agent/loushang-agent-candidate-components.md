# Loushang Agent Candidate Components

## Scope

本文档给出 `loushang-agent` 的候选组件列表。

本文档严格参照 `reference agent runtime` 的当前职责边界来识别候选组件，目标不是立即定版，而是为后续白盒设计提供组件候选清单。

本文档不讨论：

- 最终组件定版
- 最终模块结构
- 文件级映射
- 与 `loushang-coding`、`loushang-channel` 的最终细粒度接口

## Design Basis

本轮候选组件识别，基于以下边界前提：

- `loushang-agent` 是通用 agent runtime
- `loushang-agent` 直接依赖 `loushang-ai`
- `loushang-coding` 直接依赖 `loushang-agent`
- `loushang-channel` 与 `loushang-tui` 不属于 `loushang-agent` 的直接黑盒边界主体

同时，组件识别严格参照 `reference agent runtime` 当前已有的代码结构与职责分配：

- `agent.ts`
- `agent-loop.ts`
- `types.ts`
- `proxy.ts`

## Candidate Components

### 1. Agent API

职责：

- 对外暴露 `Agent`
- 提供高层 `prompt()` / `continue()` / `abort()` / `waitForIdle()` API
- 统一对外屏蔽低层 loop 细节

为什么它是组件：

- 这是整个 `loushang-agent` 的主入口
- 它承担 runtime public surface，不只是单一 helper

### 2. Agent Loop

职责：

- 承担 `agentLoop` / `agentLoopContinue`
- 驱动 turn 循环
- 驱动 assistant response、tool call 与 follow-up 推进

为什么它是组件：

- 它是 `Agent` 背后的真实执行引擎
- 与高层外观层职责明显不同

### 3. Run Lifecycle

职责：

- 管理 active run
- 管理 `AbortController`
- 管理 idle / finishRun / handleRunFailure
- 决定一轮运行的起止边界

为什么它是组件：

- 生命周期边界是稳定职责
- 与消息循环、工具执行、状态存储不是同一层次问题

### 4. Agent State

职责：

- 持有 `AgentState`
- 管理当前 `messages`
- 管理 `tools`
- 管理 `isStreaming`
- 管理 `pendingToolCalls`
- 管理 `errorMessage`

为什么它是组件：

- 这是 runtime 的事实状态中心
- 未来若有额外状态约束，最先承压的也是这一层

### 5. Context Builder

职责：

- 从当前 `AgentState` 提取 `AgentContext`
- 生成当前运行所需的 context 副本

为什么它是组件：

- 这是“状态存储”和“执行输入”之间的边界
- 虽然当前实现较薄，但职责边界稳定

### 6. Agent Options

职责：

- 将 `AgentOptions` 映射为 `AgentLoopConfig`
- 统一组织 `model`、`reasoning`、`sessionId`、`toolExecution`、hooks、queue pollers 等配置

为什么它是组件：

- 配置映射属于独立责任簇
- 不宜长期散落在高层 facade 内

### 7. Pending Message Queue

职责：

- 管理 steering queue
- 管理 follow-up queue
- 管理 queue mode（`all` / `one-at-a-time`）
- 支持 enqueue / drain / clear

为什么它是组件：

- 队列语义是 `loushang-agent` 的稳定运行控制能力
- 并非偶然 helper

### 8. Context Transformer

职责：

- 承担 `transformContext`
- 在模型调用前对 `AgentMessage[]` 做裁剪、注入、投影前变换

为什么它是组件：

- 它是应用级消息上下文进入模型层之前的关键处理边界
- 是长期扩展点，不是临时回调而已

### 9. Agent Message Transformer

职责：

- 承担 `convertToLlm`
- 将 `AgentMessage[]` 转换为 `Message[]`
- 过滤掉不应进入 LLM 的 custom message

为什么它是组件：

- 这是 `agent` 与 `ai` 的核心数据投影边界
- 未来 custom message 扩展会稳定压在这层

### 10. Assistant Message Event Stream Adapter

职责：

- 调用 `streamFn`
- 消费 assistant streaming events
- 重建 partial assistant message
- 产出 `message_start` / `message_update` / `message_end`

为什么它是组件：

- 它是模型流进入 agent runtime 的接入口
- 流式消费语义独立且复杂

### 11. Stream Function

职责：

- 承担 `StreamFn`
- 统一同步/异步 stream 返回值处理
- 屏蔽具体底层 stream 实现差异

为什么它是组件：

- 它是底层调用能力的抽象接缝
- 对未来直连、代理、自定义流实现都稳定相关

### 12. Proxy Stream

职责：

- 负责 `streamProxy`
- 将代理服务器返回的精简流式事件恢复成标准 `AssistantMessageEvent`
- 在客户端重建 partial message

为什么它是组件：

- 它明确是独立的传输适配边界
- 不应和通用 loop 或 facade 混在一起

### 13. Agent Message Types

职责：

- 定义 `AgentMessage`
- 定义 `CustomAgentMessages`
- 承担应用级消息模型抽象

为什么它是组件：

- 应用级 transcript 模型是 `loushang-agent` 的核心稳定协议
- 它决定 custom message 能否被系统性承载

### 14. Agent Event Types

职责：

- 定义 `AgentEvent`
- 定义 message / turn / tool execution lifecycle
- 为 UI、coding 层、后续 channel 层提供稳定观察协议

为什么它是组件：

- 事件协议是系统边界，不只是实现细节
- 后续多个子系统都会消费它

### 15. Event Dispatcher

职责：

- 管理 event listeners
- 按注册顺序 await listeners
- 将 loop event 折叠为 state update
- 向外广播 runtime event

为什么它是组件：

- 事件协议和事件派发实现不是一回事
- 派发顺序、await 语义、状态折叠都属于稳定责任

### 16. Tool Call Extractor

职责：

- 从 assistant message content 中识别并提取 `toolCall` blocks

为什么它是组件：

- 虽然当前实现较薄，但它是工具执行阶段和 assistant 响应阶段之间的明确边界

### 17. Tool Call Preflight

职责：

- 查找目标工具
- 执行 `prepareArguments`
- 做 schema validation
- 执行 `beforeToolCall`
- 决定工具是否进入 runnable 状态

为什么它是组件：

- 工具 preflight 是独立流水线阶段
- 权限控制、兼容层、阻断逻辑都汇聚在这里

### 18. Tool Execution

职责：

- 协调顺序或并行工具执行
- 管理 `sequential` / `parallel` 模式
- 组织 execution promises 与结果回收顺序

为什么它是组件：

- 执行模式是稳定变化面
- 顺序与并发调度逻辑不应混入其他职责

### 19. Tool Update Dispatcher

职责：

- 承接工具执行过程中的 `onUpdate`
- 产出 `tool_execution_update`

为什么它是组件：

- 工具执行中间态更新是稳定交互语义
- 对未来 channel / UI 也很重要

### 20. Tool Result Builder

职责：

- 执行 `afterToolCall`
- 包装 `ToolResultMessage`
- 发出 `tool_execution_end`
- 决定最终 `isError` / `content` / `details`

为什么它是组件：

- 它是工具执行流水线的最终边界
- 与 preflight、execution 本身职责不同

### 21. Tool Error Result Builder

职责：

- 统一构造工具错误结果
- 包括未找到工具、参数校验失败、hook 阻断、execute 抛错等情况

为什么它是组件：

- 错误结果语义会长期稳定存在
- 集中处理可避免错误语义散落

### 22. Queue Polling

职责：

- 决定何时拉取 steering messages
- 决定何时拉取 follow-up messages
- 决定它们在 loop 中插入的位置

为什么它是组件：

- 队列容器和队列消费策略不是同一职责
- 这是 run loop 控制语义的一部分

### 23. Execution Options

职责：

- 统一承载 `ToolExecutionMode`
- 承载 `ThinkingLevel`
- 承载 `transport`
- 承载 `maxRetryDelayMs`

为什么它是组件：

- 这些都是运行策略，而不是业务数据
- 未来可能扩展为更明显的策略簇

### 24. Runtime Error Builder

职责：

- 在 loop 异常时合成失败 assistant message
- 统一 error / aborted fallback 语义

为什么它是组件：

- 运行时失败不是工具失败
- 应有独立责任来稳定处理 agent 级失败语义

## Candidate Components Summary

完整候选组件列表如下：

- `Agent API`
- `Agent Loop`
- `Run Lifecycle`
- `Agent State`
- `Context Builder`
- `Agent Options`
- `Pending Message Queue`
- `Context Transformer`
- `Agent Message Transformer`
- `Assistant Message Event Stream Adapter`
- `Stream Function`
- `Proxy Stream`
- `Agent Message Types`
- `Agent Event Types`
- `Event Dispatcher`
- `Tool Call Extractor`
- `Tool Call Preflight`
- `Tool Execution`
- `Tool Update Dispatcher`
- `Tool Result Builder`
- `Tool Error Result Builder`
- `Queue Polling`
- `Execution Options`
- `Runtime Error Builder`

## Notes

本清单是候选组件清单，不是最终组件分解结果。

下一步更合理的工作应是：

- 将候选组件分为核心组件、边界组件、支撑组件
- 分析这些组件之间的拥有关系
- 进一步形成 `loushang-agent` 的白盒组件结构图

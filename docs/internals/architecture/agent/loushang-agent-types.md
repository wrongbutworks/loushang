# Loushang Agent Types

## Scope

本文档给出 `loushang-agent` 的类型 / 数据类列表。

本文档严格参照 `pi-agent` 当前公开边界整理，目标是形成一份独立于候选组件列表的类型清单。

本文档不讨论：

- 白盒组件分解
- 模块目录结构
- 与 `loushang-coding` 的扩展类型
- session persistence / compaction / summary 类

## Design Basis

本清单严格参照以下 `pi-agent` 源文件：

- `types.ts`
- `agent.ts`
- `agent-loop.ts`
- `proxy.ts`
- `index.ts`

原则：

- 优先列出 `pi-agent` 已公开或已稳定承载语义的类、类型、接口、函数类型
- 不把 `pi-ai` 的基础类型整体重复搬进 `loushang-agent`
- 不提前加入 `pi-coding-agent` 才拥有的 session / memory policy 类型

## Core Runtime Class

- `Agent`

说明：

- `loushang-agent` 的主入口类
- 对外提供 `prompt()`、`continue()`、`abort()`、`waitForIdle()` 等高层运行时 API

## Loop Functions

- `agentLoop`
- `agentLoopContinue`
- `runAgentLoop`
- `runAgentLoopContinue`

说明：

- 低层 agent loop 执行入口
- 负责 turn 推进、assistant 响应流消费、tool call 执行与 follow-up 继续运行

## State And Context Types

- `AgentState`
- `AgentContext`
- `AgentOptions`
- `AgentLoopConfig`

说明：

- `AgentState` 表示 public runtime state
- `AgentContext` 表示低层 loop 使用的上下文快照
- `AgentOptions` 表示 `Agent` 构造参数
- `AgentLoopConfig` 表示 loop 执行配置

## Message And Content Types

- `CustomAgentMessages`
- `AgentMessage`
- `AgentToolCall`
- `AgentToolResult`

说明：

- `CustomAgentMessages` 是声明合并扩展点
- `AgentMessage` 是基础 LLM message 与 custom message 的联合
- `AgentToolCall` 是 assistant message content 中 `toolCall` block 的提取类型
- `AgentToolResult` 是工具执行产出的标准结果类型，包含 `content`、`details` 与可选提前停止提示 `terminate`

## Tool Types

- `AgentTool`
- `AgentToolUpdateCallback`
- `ToolExecutionMode`

说明：

- `AgentTool` 在 `pi-ai` 的 `Tool` 基础上扩展出 `label`、`prepareArguments`、`execute`、`execution_mode`
- `AgentToolUpdateCallback` 用于工具执行过程中的 partial update
- `ToolExecutionMode` 规定多 tool call 的执行模式，支持 `parallel` 与 `sequential`
- 旧 runtime tool 未声明 `execution_mode` 时，在 agent/registry 边界默认补为 `parallel`

## Hook Types

- `BeforeToolCallContext`
- `BeforeToolCallResult`
- `AfterToolCallContext`
- `AfterToolCallResult`

说明：

- `BeforeToolCall*` 用于工具执行前拦截
- `AfterToolCall*` 用于工具执行后覆写结果，可覆写 `content`、`details`、`is_error` 与 `terminate`
- `AfterToolCall*` 抛出的异常会被 agent loop 转换为 `ToolResultMessage(is_error=True)`，保持与 `pi-agent` 的工具错误语义一致

## Event Types

- `AgentEvent`
- `StreamFn`
- `ThinkingLevel`

说明：

- `AgentEvent` 定义 agent runtime 生命周期事件
- `StreamFn` 是 agent loop 使用的流式调用函数类型
- `ThinkingLevel` 是 `loushang-agent` 自身定义的 reasoning level 联合类型

## Proxy Types

- `ProxyAssistantMessageEvent`
- `ProxyStreamOptions`
- `streamProxy`

说明：

- 这组类型与函数对应代理流适配边界
- 用于把服务端代理返回的事件恢复为标准 `AssistantMessageEvent` 流

## Minimal First-Batch Type List

如果只定义第一批最核心的 `loushang-agent` 类型，建议先落下面这组：

- `Agent`
- `AgentOptions`
- `AgentState`
- `AgentContext`
- `AgentLoopConfig`
- `CustomAgentMessages`
- `AgentMessage`
- `AgentEvent`
- `AgentTool`
- `AgentToolCall`
- `AgentToolResult`
- `AgentToolUpdateCallback`
- `BeforeToolCallContext`
- `BeforeToolCallResult`
- `AfterToolCallContext`
- `AfterToolCallResult`
- `StreamFn`
- `ToolExecutionMode`
- `ThinkingLevel`
- `ProxyAssistantMessageEvent`
- `ProxyStreamOptions`
- `streamProxy`

## Out Of Scope

以下类型不应放入 `loushang-agent` 的这份首批类型清单：

- `AgentSession`
- `AgentSessionState`
- `SessionMessageEntry`
- `SessionCheckpoint`
- `SessionManager`
- `CompactionSummary`
- `BranchSummary`

原因：

- 这些不是 `pi-agent` 的边界
- 它们属于 `pi-coding-agent` 一侧的 session persistence / compaction / summary 职责

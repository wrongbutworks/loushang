# Loushang Agent v0.2

## 1. Scope

本术语表定义 `loushang-agent` 层的核心概念。  
目标是尽量对齐 `pi` 已验证的抽象方式，并在跨边界通信处补充 `protocol` 与 `transport` 两个概念。

本版本暂不讨论方法层术语，如 `stage`、`role`、`task`、`work product`。

## 2. Design Principles

1. **Agent 核心术语尽量对齐 `pi`**  
   优先沿用 `Agent`、`AgentLoop`、`AgentMessage`、`AgentEvent`、`AgentTool` 等概念。

2. **`model` 优先于 `llm`**  
   `llm` 可作为习惯性别名保留，但正式术语统一使用 `model`。

3. **`wire` 不作为核心术语**  
   跨边界通信统一拆分为：
   - `protocol`
   - `transport`

4. **面向架构与使用者的概念优先**  
   先定义系统认知中心概念，再定义内部实现概念。

## 3. Architecture Principle

`loushang` 采用“内核 + 协议 + 适配器 + 扩展点”的分层架构。内核定义系统的运行语义，协议定义系统与外部世界的沟通边界，适配器连接不同环境与终端形态，扩展点则在不破坏内核一致性的前提下开放可编程能力。四者共同构成 `loushang` 的基础架构：内核保证一致性，协议保证可连接性，适配器保证可达性，扩展点保证可演化性。

`loushang` 以内核承载语义，以协议连接边界，以适配器触达环境，以扩展点驱动演化。

## 4. Agent Core

### Agent

智能体运行单元。  
负责持有状态、能力、上下文与运行控制，是 agent 层的核心执行主体。

### AgentLoop

智能体循环。  
负责驱动一次或多次 assistant 响应、工具调用与结果回流的执行机制。

### Turn

轮次。  
AgentLoop 中的单个运行周期，通常包含一次 assistant 响应，以及该响应触发的全部工具执行与 `toolResult` 回填。

### AgentContext

智能体上下文。  
传入低层 AgentLoop 的上下文快照，通常包括：
- `systemPrompt`
- `messages`
- `tools`

### AgentState

智能体状态。  
Agent 在运行过程中的完整内部快照，包含上下文内容与运行态信息，例如：
- `isStreaming`
- `streamingMessage`
- `pendingToolCalls`
- `errorMessage`

### AgentLoopConfig

智能体循环配置。  
定义一次 AgentLoop 的执行策略与边界行为，包括但不限于：
- `model`
- `convertToLlm`
- `transformContext`
- `getApiKey`
- `getSteeringMessages`
- `getFollowUpMessages`
- `toolExecution`
- `beforeToolCall`
- `afterToolCall`

## 5. Messages

### AgentMessage

智能体消息。  
Agent 层中的统一消息抽象，包含标准 LLM 消息与自定义消息。

### UserMessage

用户消息。  
由用户或系统注入的输入消息。

### AssistantMessage

助手消息。  
在 agent 语境中，表示由模型生成并被 agent 消费的助手消息。

其核心语义应对齐 `loushang-ai.AssistantMessage`。

### ToolResultMessage

工具结果消息。  
在 agent 语境中，表示工具执行完成后回填给 loop 的结果消息。

其核心语义应对齐 `loushang-ai.ToolResultMessage`。

### CustomAgentMessage

自定义智能体消息。  
应用层定义的非标准消息类型，用于 UI、通知、状态标记或领域特定扩展。

### MessageContent

消息内容块。  
构成消息的内容单元，常见类型包括：
- `text`
- `thinking`
- `toolCall`
- `image`

## 6. Streaming Semantics

### AssistantMessageEvent

助手消息事件。  
在 agent 语境中，表示被 agent 消费的 assistant 流式事件。

其核心语义应对齐 `loushang-ai.AssistantMessageEvent`。

常见事件包括：
- `text_start`
- `text_delta`
- `text_end`
- `thinking_start`
- `thinking_delta`
- `thinking_end`
- `toolcall_start`
- `toolcall_delta`
- `toolcall_end`

### TextDelta

文本增量。  
Assistant 流式输出中的文本增量片段。

### ThinkingDelta

思考增量。  
Assistant 流式输出中的 reasoning / thinking 增量片段。

### ToolCallDelta

工具调用增量。  
Assistant 流式输出中的工具调用参数增量片段。

### EventStream

事件流。  
可异步迭代的运行结果抽象，承载连续事件，并可在结束时返回最终结果。  
`AgentLoop` 的主要输出容器。

### StopReason

停止原因。  
表示 assistant message 结束的原因。

其核心语义应对齐 `loushang-ai.StopReason`，例如：
- `stop`
- `toolUse`
- `error`
- `aborted`

它定义了一条 assistant message 为何结束，以及 loop 是否需要继续。

### StreamFn

流式函数。  
AgentLoop 调用模型时使用的流式接口抽象。  
它必须返回标准 assistant event stream，并通过流内事件表达失败、终止或中断。

## 7. Events

### AgentEvent

智能体事件。  
Agent 生命周期中的标准事件抽象，用于描述 Agent、Turn、Message 与 Tool execution 的状态变化。

### Agent lifecycle

- `agent_start`
- `agent_end`

### Turn lifecycle

- `turn_start`
- `turn_end`

### Message lifecycle

- `message_start`
- `message_update`
- `message_end`

### Tool execution lifecycle

- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`

### AgentEventSink

事件接收端。  
用于接收、转发或消费 `AgentEvent` 的内部接口。  
更偏实现层，不作为高层主概念使用。

### ProxyAssistantMessageEvent

代理助手消息事件。  
用于在 provider/streaming 层与 agent 层之间转译或代理的 assistant message event。  
属于 streaming internals，不作为顶层领域概念使用。

## 8. Tools

### AgentTool

智能体工具。  
Agent 可调用的外部能力定义，包含：
- 工具元信息
- 参数 schema
- 执行函数
- 可选参数预处理
- 可选执行更新回调

### AgentToolCall

工具调用。  
AssistantMessage 中发出的单个 `toolCall` 内容块。

### AgentToolResult

工具结果。  
工具执行后的最终或部分结果，通常包含：
- `content`
- `details`

### ToolExecutionMode

工具执行模式。  
定义同一条 assistant message 中多个 tool call 的执行策略：
- `sequential`
- `parallel`

### BeforeToolCallContext

前置工具调用上下文。  
传递给 `beforeToolCall` 的上下文对象，包含 assistant message、toolCall、参数与当前 AgentContext。

### BeforeToolCallResult

前置工具调用结果。  
`beforeToolCall` 的返回值，可用于阻止工具执行。

### AfterToolCallContext

后置工具调用上下文。  
传递给 `afterToolCall` 的上下文对象，包含 tool 执行结果、错误标记与当前 AgentContext。

### AfterToolCallResult

后置工具调用结果。  
`afterToolCall` 的返回值，用于覆盖或修正工具结果。

## 8. Model Layer

### Provider

提供方。  
该术语由 `loushang-ai` 定义，agent 只消费其结果。

### Model

模型。  
Agent 实际调用的智能模型。  
`llm` 可作为习惯用语保留，但核心术语统一使用 `model`。

其核心语义应对齐 `loushang-ai.Model`。

### ThinkingLevel

思考等级。  
模型推理/思考强度的抽象级别。

其核心语义应对齐 `loushang-ai.ThinkingLevel`，例如：
- `off`
- `minimal`
- `low`
- `medium`
- `high`
- `xhigh`

## 9. Boundary Concepts

### Protocol

协议。  
由 `loushang-channel` 定义的边界概念。

`loushang-agent` 消费 `protocol`，但不拥有其核心定义。

### Transport

传输。  
由 `loushang-channel` 定义的边界概念。

`loushang-agent` 可运行在某种 transport 之上，但不拥有 transport 的核心定义。

## 10. Extensibility

### Skill

技能。  
可复用的能力或方法封装，用于约束、增强或组织 Agent 的行为。  
`tool` 是做事的手，`skill` 是做事的方法。

### Session

会话。  
围绕持续目标形成的长期运行单元，用于承载历史、恢复、分支与延续能力。

### CustomAgentMessages

自定义消息扩展点。  
用于向 AgentMessage 体系中注入应用层消息类型。

## 11. Concept Relationships

- `Agent` 通过 `AgentLoop` 运行。
- `AgentLoop` 消费 `AgentContext`，产生 `AgentEvent`，并沉淀到 `AgentState`。
- `Turn` 是 `AgentLoop` 的基本执行周期。
- `AgentMessage` 是交互内容，`AgentEvent` 是运行信号。
- `AssistantMessageEvent` 描述 assistant message 的流式生成过程。
- `AgentTool` 是做事的手，`Skill` 是做事的方法。
- `Provider` 提供 `Model` 能力。
- `Protocol` 与 `Transport` 由 `loushang-channel` 定义，`loushang-agent` 在其上暴露运行语义。

## 12. Open Points

下一步建议补齐三部分：

1. **Agent Type System**  
   明确 `AgentMessage family`、`AgentEvent family`、`Protocol message family`。

2. **Method Layer Bridge**  
   以后再把 `stage`、`role`、`task`、`work product` 接到 agent 层之上。

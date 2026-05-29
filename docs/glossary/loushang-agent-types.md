# Loushang Agent Types v0.1

## 1. Scope

本文档定义 `loushang-agent` 的核心类型定义。  
目标是对齐 `pi` 已验证的抽象方式，明确以下三组核心类型边界：

1. `AgentMessage` family
2. `AgentEvent` family
3. `Streaming` family

本文档暂不定义方法层类型，如 `stage`、`role`、`task`、`work product`，也暂不展开跨边界 `protocol` 的完整消息族。

---

## 2. Design Principles

1. **Message 是内容抽象**  
   Message 用于表达运行时中被存储、传递和回放的内容。

2. **Event 是运行信号**  
   Event 用于表达 agent 生命周期中的状态变化。

3. **Delta 是流式增量**  
   Delta 不是完整消息，而是 assistant message 生成过程中的增量片段。

4. **Turn 是 Loop 的执行边界**  
   一个 turn 表示一次 assistant 响应及其触发的完整工具执行闭环。

5. **EventStream 是 Loop 的输出容器**  
   Loop 不直接返回单一结果，而是返回可持续产生事件并在结束时收敛结果的流。

---

## 3. AgentMessage Family

### 3.1 AgentMessage

`AgentMessage` 是 agent 层的统一消息抽象。  
它既包含标准 LLM 消息，也包含应用层自定义消息。

推荐定义：

- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`
- `CustomAgentMessage`

### 3.2 UserMessage

由用户或系统注入的输入消息。  
它通常作为一次 `AgentLoop` 的起点之一。

典型属性：

- `role = "user"`
- `content`
- `timestamp`

### 3.3 AssistantMessage

由模型生成的消息。  
它既可以是最终完成态消息，也可以在 streaming 过程中表现为 partial message。

典型属性：

- `role = "assistant"`
- `content`
- `stopReason`
- `errorMessage?`
- `timestamp`

### 3.4 ToolResultMessage

工具执行完成后回流给 agent 的结果消息。  
它将工具执行结果重新纳入消息历史，用于驱动下一轮推理。

典型属性：

- `role = "toolResult"`
- `toolCallId`
- `toolName`
- `content`
- `isError`
- `details?`
- `timestamp`

### 3.5 CustomAgentMessage

agent 层或应用层定义的自定义消息。  
用于承载 UI 状态、通知、标记、领域信息等不直接属于 LLM 原生消息体系的内容。

它们可以存在于 transcript 中，但不一定会被送入模型上下文。

### 3.6 MessageContent

`MessageContent` 是消息内部的内容块抽象。  
常见内容类型包括：

- `text`
- `thinking`
- `toolCall`
- `image`

### 3.7 Type Relationship

```text
AgentMessage
├── UserMessage
├── AssistantMessage
├── ToolResultMessage
└── CustomAgentMessage

AssistantMessage.content
└── MessageContent[]
    ├── text
    ├── thinking
    ├── toolCall
    └── image
```

---

## 4. AgentEvent Family

### 4.1 AgentEvent

`AgentEvent` 是 agent 生命周期中的统一事件抽象。  
它不承载“历史内容本身”，而承载“运行过程中的状态变化”。

### 4.2 Event Families

#### Agent lifecycle

- `agent_start`
- `agent_end`

#### Turn lifecycle

- `turn_start`
- `turn_end`

#### Message lifecycle

- `message_start`
- `message_update`
- `message_end`

#### Tool execution lifecycle

- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`

### 4.3 Event Semantics

#### `agent_start`

一次 agent run 开始。

#### `agent_end`

一次 agent run 结束。  
通常携带本次 run 新增的消息集合，而不是完整 transcript。

#### `turn_start`

一个 turn 开始。

#### `turn_end`

一个 turn 结束。  
通常表示：

1. assistant 响应已完成
2. 该响应触发的工具执行已完成
3. `toolResult` 已回填到上下文

#### `message_start`

一条消息进入生命周期。  
对 assistant 来说，通常意味着 partial message 壳子已创建。

#### `message_update`

消息在 streaming 过程中被增量更新。  
通常只对 assistant message 出现。

#### `message_end`

消息进入完成态。  
此时该消息可被视为本轮最终版本。

#### `tool_execution_start`

工具执行开始。

#### `tool_execution_update`

工具在执行过程中产生部分更新。

#### `tool_execution_end`

工具执行结束，并进入结果收敛阶段。

### 4.4 Type Relationship

```text
AgentEvent
├── Agent lifecycle
│   ├── agent_start
│   └── agent_end
├── Turn lifecycle
│   ├── turn_start
│   └── turn_end
├── Message lifecycle
│   ├── message_start
│   ├── message_update
│   └── message_end
└── Tool execution lifecycle
    ├── tool_execution_start
    ├── tool_execution_update
    └── tool_execution_end
```

---

## 5. Streaming Family

### 5.1 AssistantMessageEvent

`AssistantMessageEvent` 是 assistant message 流式生成过程中的细粒度事件抽象。

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

### 5.2 Delta Types

#### TextDelta

文本增量。  
AssistantMessage 中 `text` 内容块的逐步生成片段。

#### ThinkingDelta

思考增量。  
AssistantMessage 中 `thinking` 内容块的逐步生成片段。

#### ToolCallDelta

工具调用增量。  
AssistantMessage 中 `toolCall` 参数的逐步生成片段。

### 5.3 EventStream

`EventStream` 是 agent 的流式输出抽象。  
它具有两个基本职责：

1. 连续产生事件
2. 在结束时收敛为最终结果

对 `AgentLoop` 来说，`EventStream` 是主要输出容器。

### 5.4 StreamFn

`StreamFn` 是 AgentLoop 调用模型时使用的流式函数抽象。  
它必须满足：

1. 返回标准 assistant message event stream
2. 不以抛异常作为常规失败表达方式
3. 失败、中断、终止应通过流内事件和最终消息表达

### 5.5 StopReason

`StopReason` 表示 assistant message 结束的原因。  
常见值包括：

- `stop`
- `toolUse`
- `error`
- `aborted`

它用于决定：

1. 当前 assistant message 为什么结束
2. `AgentLoop` 是否需要继续下一轮

### 5.6 Type Relationship

```text
AssistantMessageEvent
├── text_start
├── text_delta
├── text_end
├── thinking_start
├── thinking_delta
├── thinking_end
├── toolcall_start
├── toolcall_delta
└── toolcall_end

EventStream
├── emits AgentEvent
└── resolves final result
```

---

## 6. Cross-Cutting Type Roles

### AgentContext

一次低层 loop 执行可见的上下文快照。  
它不是完整运行态，只是 loop 的输入环境。

### AgentState

Agent 的完整状态快照。  
它不仅包含上下文，也包含 agent 运行状态。

### AgentTool

Agent 可调用的工具定义。  
它通常包含：

- 元信息
- 参数 schema
- 执行函数
- 更新回调

### AgentToolCall

AssistantMessage 中的单个工具调用块。

### AgentToolResult

工具执行后的结果抽象。  
既可以是最终结果，也可以是部分结果。

---

## 7. Type System Boundaries

### Agent Core

以下概念属于 agent 核心：

- `Agent`
- `AgentLoop`
- `Turn`
- `AgentMessage`
- `AgentEvent`
- `AgentContext`
- `AgentState`
- `AgentTool`
- `AgentToolCall`
- `AgentToolResult`
- `AgentLoopConfig`

### Streaming Core

以下概念属于 streaming 子系统：

- `AssistantMessageEvent`
- `TextDelta`
- `ThinkingDelta`
- `ToolCallDelta`
- `EventStream`
- `StreamFn`
- `StopReason`

### Internal Interfaces

以下概念偏内部实现，不作为顶层领域核心概念使用：

- `AgentEventSink`
- `ProxyAssistantMessageEvent`

---

## 8. Open Points

下一步建议继续定义：

1. **Protocol Message Family**  
   定义边界层的 `request`、`response`、`notification`、`client event`。

2. **Channel Boundary Model**  
   定义 `protocol`、`transport`、`channel host`、`client` 之间的关系。

3. **Method Layer Bridge**  
   后续将 `stage`、`role`、`task` 等方法层概念映射到 agent 层。

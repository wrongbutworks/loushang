# Loushang Channel Boundary Protocol v0.1

## Status

Legacy target-architecture reference.

This document preserves an older channel boundary model. It is useful for future
`loushang.channel` protocol work, but it is not evidence of a current
`src/loushang/channel/` implementation. Current RPC support is a transitional
`loushang.coding.mode.RpcMode` surface; see
[ARD-005](../architecture/coding/ARD-005-rpc-mode-transitional-channel-positioning.md)
for the accepted positioning.

## 1. Scope

本文档定义 `loushang-channel` 的边界协议模型。
目标是在 `pi` 已验证的 agent 抽象基础上，补齐跨边界运行所需的概念，包括：

1. `protocol`
2. `transport`
3. `request`
4. `response`
5. `notification`
6. `client`
7. `channel host`

本层对应的是过去常被称为 `wire` 的部分。
在 `loushang` 中，不再使用 `wire` 作为核心术语，而统一使用：

- `protocol`
- `transport`

---

## 2. Design Goals

边界协议层的目标不是替代 agent，而是把 agent 变成可跨边界运行的系统。

它需要支持：

1. **本地 UI**
2. **远程 UI**
3. **多客户端观察**
4. **审批与问答**
5. **远程工具执行**
6. **回放与审计**
7. **前后端分离**

---

## 3. Core Concepts

### Protocol

协议。
定义 channel 边界上消息、事件、请求与响应结构的规则集合。

`Protocol` 负责回答：

- 什么可以被发送
- 每类消息长什么样
- 谁发给谁
- 如何区分事件、请求、响应和通知

它是结构定义，不是传输实现。

### Transport

传输。
承载 protocol 的具体通信实现。

常见 transport 包括：

- `memory`
- `stdio`
- `websocket`
- `rpc`

`Transport` 负责回答：

- 协议消息如何在边界两端传递
- 是本地内存传递，还是进程间/网络传递

### Channel Host

通道宿主。
真正运行 `Agent`、`AgentLoop` 与工具执行逻辑的一侧。

它负责：

- 持有 agent state
- 发出 agent events
- 发起 requests
- 接收 responses

### Client

客户端。
消费 channel protocol 的一侧。

它可以是：

- `tui client`
- `web client`
- `rpc client`
- `background observer`

它负责：

- 接收 channel host 发出的 events / notifications
- 对 requests 作出响应
- 渲染 UI 或触发外部行为

---

## 4. Protocol Message Families

边界协议上的消息建议分为四类：

1. `event`
2. `request`
3. `response`
4. `notification`

### Event

事件。
由 channel host 发出，用于表达运行过程中的状态变化。

它主要对应 `AgentEvent` 的协议化表达。

典型 event：

- `agent_start`
- `turn_start`
- `message_update`
- `tool_execution_end`
- `agent_end`

### Request

请求。
由 channel host 发出，要求 client 或外部系统给出明确响应。

典型 request：

- `approval_request`
- `question_request`
- `selection_request`
- `input_request`

### Response

响应。
由 client 返回给 channel host，用于回应某个 request。

典型 response：

- `approval_response`
- `question_response`
- `selection_response`
- `input_response`

### Notification

通知。
由 channel host 或 client 发出，用于传递无需显式回应的信息。

典型 notification：

- `status_update`
- `info_notification`
- `warning_notification`
- `error_notification`

---

## 5. Channel Boundary Semantics

### Event Semantics

`Event` 用于表达 channel 边界上的事实。
它不要求 client 回答。

特点：

- 单向
- 可记录
- 可回放
- 可被多个观察者消费

### Request / Response Semantics

`Request` / `Response` 用于表达 channel host 与 client 之间的交互闭环。

特点：

- 配对出现
- request 发出后，channel host 可能等待 response
- 适合审批、提问、选择、交互输入

### Notification Semantics

`Notification` 用于表达不需要形成闭环的提示信息。

特点：

- 不阻塞主循环
- 不要求回应
- 适合 UI 提示、状态同步、系统广播

---

## 6. Suggested Protocol Shape

建议协议消息具备统一 envelope：

- `kind`
- `type`
- `id`
- `timestamp`
- `payload`
- `correlationId?`

### kind

表示消息家族，例如：

- `event`
- `request`
- `response`
- `notification`

### type

表示该消息的具体类型，例如：

- `agent_start`
- `approval_request`
- `approval_response`

### id

消息唯一标识。

### timestamp

消息创建时间。

### payload

该消息承载的具体数据。

### correlationId

用于将 response 关联回对应的 request。
对 request/response 类消息尤其重要。

---

## 7. Relationship to Agent Types

### AgentEvent -> Event

`AgentEvent` 是 agent 内部事件抽象。
当跨边界传输时，应投影为 protocol `event`。

### AssistantMessageEvent -> Event

`AssistantMessageEvent` 可作为更细粒度的 agent 流事件投影到 protocol event 中。

### AgentMessage -> Protocol Payload

`AgentMessage` 本身通常不直接等于 protocol message。
更常见的是：

- 它作为 `event.payload`
- 或作为 `request.payload`
- 或作为 `response.payload`

### EventStream -> Transported Event Sequence

`EventStream` 是 agent 内部的流式抽象。
跨边界后，它会表现为 transport 上持续流动的一系列 protocol messages。

---

## 8. Boundary Model

```text
Channel Host
├── Agent
├── AgentLoop
├── State
├── Tools
└── Protocol Adapter
        │
        │ protocol messages
        ▼
     Transport
        │
        ▼
      Client
      ├── TUI
      ├── Web UI
      ├── RPC Client
      └── Observer
```

### Protocol Adapter

协议适配器。
负责把 agent 内部对象投影为边界协议消息，并将外部 response 映射回 agent 可用的数据结构。

它处于：

- agent core
- boundary protocol

之间。

---

## 9. Replay and Audit

边界协议层应天然支持：

1. **Replay**
   - 重放事件序列
   - 重建交互历史
   - 驱动调试与可视化

2. **Audit**
   - 记录关键请求/响应
   - 追踪审批与人工输入
   - 支持后验分析

因此建议 protocol message 设计天然可序列化、可持久化、可回放。

---

## 10. Open Points

## 10. Request / Response Type Families

边界协议上的交互闭环，建议首先固化四类基础 request / response：

1. `approval`
2. `question`
3. `selection`
4. `input`

它们共同覆盖：

- 授权确认
- 问答澄清
- 选项选择
- 自由输入

### 10.1 Approval Request / Response

#### approval_request

用于 channel host 请求 client 对某个动作作出批准或拒绝。

适用场景：

- 危险命令执行
- 跨边界权限提升
- 破坏性文件操作
- 外部副作用确认

建议 payload 字段：

- `title`
- `message`
- `severity`
- `operation`
- `details?`
- `timeoutMs?`

#### approval_response

用于 client 回应某个 `approval_request`。

建议 payload 字段：

- `approved`
- `reason?`

### 10.2 Question Request / Response

#### question_request

用于 channel host 向 client 发出问题，请求用户回答。

适用场景：

- 需求澄清
- 缺失上下文确认
- 运行中追问

建议 payload 字段：

- `title`
- `question`
- `description?`
- `placeholder?`
- `timeoutMs?`

#### question_response

用于 client 回应某个 `question_request`。

建议 payload 字段：

- `answer`

### 10.3 Selection Request / Response

#### selection_request

用于 channel host 请求 client 从一组选项中进行选择。

适用场景：

- 模型切换
- 模板选择
- 路径选择
- 工作流分支选择

建议 payload 字段：

- `title`
- `message`
- `options`
- `multiSelect?`
- `defaultValue?`
- `timeoutMs?`

其中 `options` 建议为结构化数组，每项包含：

- `id`
- `label`
- `description?`

#### selection_response

用于 client 回应某个 `selection_request`。

建议 payload 字段：

- `selected`

说明：

- 单选时 `selected` 可为单值
- 多选时 `selected` 可为数组

### 10.4 Input Request / Response

#### input_request

用于 channel host 请求 client 提供自由输入内容。

适用场景：

- 文本输入
- 多行说明
- 参数补全
- 临时命令或草稿输入

建议 payload 字段：

- `title`
- `message`
- `multiline?`
- `placeholder?`
- `defaultValue?`
- `timeoutMs?`

#### input_response

用于 client 回应某个 `input_request`。

建议 payload 字段：

- `value`

### 10.5 Common Request / Response Rules

所有 request / response 建议遵循以下规则：

1. 每个 request 必须有唯一 `id`
2. 每个 response 必须通过 `correlationId` 对应某个 request
3. request 应天然可超时
4. response 应允许显式取消或拒绝
5. 所有 request / response 都应可序列化与回放

### 10.6 Optional Future Families

在四类基础 request / response 之外，后续可扩展：

- `editor_request` / `editor_response`
- `upload_request` / `upload_response`
- `auth_request` / `auth_response`
- `agent_control_request` / `agent_control_response`

这些不建议在第一版 protocol 中优先固化。

---

## 11. Open Points

下一步建议继续定义：

1. **Client Capability Model**
   - 哪些 client 支持审批
   - 哪些 client 支持选择
   - 哪些 client 仅支持只读观察

2. **Protocol Versioning**
   - 如何做 schema 演进
   - 如何兼容旧 client / 新 agent host

3. **Notification Type Families**
   - `status_update`
   - `info_notification`
   - `warning_notification`
   - `error_notification`

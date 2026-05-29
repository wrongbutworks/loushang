# Loushang Channel v0.1

## 1. Scope

本术语表定义 `loushang-channel` 层的核心概念。

`loushang-channel` 是 `loushang` 的边界协议与传输层。
它负责承接 agent 与外部客户端、宿主或远端运行体之间的跨边界通信语义。

它负责：

- `protocol`
- `transport`
- `request`
- `response`
- `notification`
- capability negotiation
- replay
- channel audit trail

它不负责：

- agent 内核状态机
- provider 接入细节
- 本地 UI 组件实现
- 方法层调度
- 业务级审计分析

---

## 2. Design Principles

1. `channel` 只定义边界语义，不承载 agent 内核语义
2. `protocol` 与 `transport` 分离
3. `request / response / notification` 是核心边界消息家族
4. replay 与 audit 只覆盖边界交互，不覆盖内部推理过程
5. 正式术语优先服务边界稳定性，而不是某种具体传输实现

---

## 3. Channel Core

### Channel

边界通信子系统。

负责把 `loushang-agent` 的运行能力暴露为稳定的边界交互形式，并承接来自边界外部的输入、控制与订阅。

### Channel Endpoint

边界端点。

表示一个可被连接、调用、订阅或管理的 channel 暴露点。

### Channel Session

边界会话。

表示在某个 channel 连接或交互上下文中形成的持续通信单元。

它关注的是边界交互连续性，而不是 agent 内部长期状态本体。

### Protocol

协议。

定义 channel 边界上的消息类型、字段约束、交互规则与状态约定。

### Transport

传输。

承载 `protocol` 的具体通信实现，例如：

- `memory`
- `stdio`
- `websocket`
- `rpc`

---

## 4. Boundary Message Family

### Request

请求。

由边界调用方向被调用方发送的命令型消息，用于发起动作、查询或控制操作。

典型特征包括：

- 有明确意图
- 通常期待对应结果
- 可携带参数与上下文元信息

### Response

响应。

对 `request` 的对应返回消息，用于表达成功结果、失败结果或拒绝结果。

典型特征包括：

- 与某个 `request` 关联
- 表达结果或错误
- 可携带结构化返回值

### Notification

通知。

单向发送的边界消息，用于表达状态变化、事件推送或非请求型更新。

典型特征包括：

- 不要求直接配对的响应
- 更适合事件广播或异步告知
- 常用于进度、生命周期、状态与提示信息

### Event

事件。

边界上可被观察与转发的状态变化信号。

在 `channel` 语境中，`event` 更强调“可被协议承载的边界事件”，而不是 agent 内核内部事件本体。

---

## 5. Boundary Capabilities

### Capability

能力声明。

表示某个 channel endpoint 或对端在边界上支持的功能集合。

### Capability Negotiation

能力协商。

用于在连接建立或会话初始化阶段确认双方支持的协议特性、消息能力与可选功能。

### Replay

重放。

基于已记录的边界交互记录，对 request、response、notification 或 event 进行再投递、再呈现或再恢复的能力。

`Replay` 关注的是边界层可见交互，而不是 agent 内部完整执行状态复原。

### Channel Audit

边界审计轨迹。

用于记录边界上实际发生过的交互事实，例如：

- 发出了什么 `request`
- 收到了什么 `response`
- 推送了什么 `notification`
- 某次能力协商启用了什么 capability
- 某次 replay 基于什么边界记录

`Channel Audit` 负责的是边界交互可审计性，不等于完整的审计系统。

---

## 6. Concept Relationships

- `Channel` 通过 `Protocol` 定义边界规则。
- `Transport` 承载 `Protocol` 的具体通信实现。
- `Request` 与 `Response` 共同形成成对交互。
- `Notification` 负责单向边界告知。
- `Event` 是可被协议承载与分发的边界状态信号。
- `Capability Negotiation` 用于协商 channel 可用能力。
- `Replay` 基于边界记录恢复或再呈现交互。
- `Channel Audit` 记录边界上发生过的交互事实。

---

## 7. Boundary Rule

`loushang-channel` 到此为止。

以下术语不应进入 `loushang-channel` 的核心术语表：

- `Agent`
- `AgentLoop`
- `AgentState`
- `AgentTool`
- `Model`
- `Provider`
- `Tool orchestration policy`
- 本地 `TUI` 组件原语

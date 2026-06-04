# Loushang Subsystems

## Scope

本文档定义 `loushang` 的主要子系统及其职责边界。  
它关注系统分工，不展开实现细节、类型系统或边界协议。

## Subsystem List

当前建议的核心子系统包括：

- `loushang-ai`
- `loushang-agent`
- `loushang-channel`
- `loushang-tui`
- `loushang-methods`
- `loushang-coding`

## Subsystem Responsibilities

### loushang-ai

模型接入、统一调用与流式语义层。

负责：

- `model` 抽象
- 统一 AI 调用入口
- `provider` 适配
- 流式输出协议
- tool schema / tool call / tool result message 语义
- 与上游模型 API 的能力映射

不负责：

- `Agent` 生命周期
- tool orchestration policy
- tool execution scheduling
- tool execution hook policy
- 边界协议建模

### loushang-agent

agent 运行内核。

负责：

- `Agent`
- `AgentLoop`
- `AgentMessage`
- `AgentEvent`
- `AgentTool`
- `AgentContext`
- `AgentState`

不负责：

- provider 接入细节
- UI 渲染
- 跨边界 transport

### loushang-channel

agent 边界与协议层。

负责：

- `event`
- `request`
- `response`
- `notification`
- `protocol`
- `transport`
- capability negotiation
- replay
- channel audit trail

不负责：

- agent 内核状态机
- 本地 UI 组件实现
- 方法层调度

### loushang-tui

通用终端 UI 基础层。

负责：

- prompt / composer / toolbar / terminal output 等交互原语
- keybinding / history / TTY fallback 等终端交互能力
- 真实 terminal scrollback 与 transient composer 的协调
- 为产品适配层提供可复用的终端 UI primitives

不负责：

- agent 内核语义
- provider 接入
- 方法层定义
- coding session/runtime 语义
- coding-specific model / tool / diagnostics policy

相关文档：

- [Loushang-TUI Architecture](./tui/README.md)

### loushang-methods

方法层。

负责：

- `skill`
- `stage`
- `role`
- `task`
- `guidance`
- `work product`
- 方法元与调度关系

不负责：

- 底层模型接入
- 边界协议承载
- TUI 交互实现

### loushang-coding

面向 coding 场景的产品装配层。

负责：

- 默认工具
- 默认策略
- coding workflow
- CLI 入口
- 与 `tui`、`channel`、`methods` 的产品化集成
- `loushang.coding.ui` 终端产品适配层
- session/runtime 与 terminal UI 的交互编排

不负责：

- 通用模型协议定义
- agent 核心类型系统
- 通用边界协议定义
- 通用 terminal UI primitives

## Layer Relationship

从下到上，建议的系统关系为：

1. `loushang-ai`
2. `loushang-agent`
3. `loushang-channel`
4. `loushang-tui`
5. `loushang-methods`
6. `loushang-coding`

其中：

- `ai` 提供模型接入能力
- `agent` 提供运行语义
- `channel` 提供边界通信
- `tui` 提供通用终端交互原语
- `methods` 提供方法组织
- `coding` 提供场景装配，并通过 `loushang.coding.ui` 调用 `loushang.tui`

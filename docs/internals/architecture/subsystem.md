# Loushang Subsystems

## Scope

本文档定义 `loushang` 的主要子系统及其职责边界。
它关注系统分工，不展开实现细节、类型系统或边界协议。

## Subsystem List

当前已落地的核心包级子系统包括：

- `loushang.ai`
- `loushang.agent`
- `loushang.coding`
- `loushang.method`
- `loushang.tui`
- `loushang.work`

当前已落地的支撑/实验性包包括：

- `loushang.runtime`
- `loushang.observability`
- `loushang.ontology`

目标架构仍保留 `loushang.channel`，但当前没有 package-level
implementation。现有 RPC mode 是 coding-local transitional adapter，不等于
长期 channel surface。

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

### loushang-channel (target)

边界协议与 transport 层。当前是目标架构概念，不是已落地 Python 包。

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

### loushang-method

方法层。

负责：

- `skill`
- `MethodDescriptor`
- `MethodPlan`
- `MethodStep`
- `MethodProjection`
- method resource loading
- fixed method compilation
- `guidance`
- `work product`
- 方法元与投影关系

不负责：

- 底层模型接入
- 边界协议承载
- TUI 交互实现
- 通用 work lifecycle

### loushang-work

工作运行语义、事件日志与 projection 层。

负责：

- `WorkOperation`
- `WorkRun`
- `WorkEvent`
- work event log
- plan/step lifecycle projection
- method run replay / inspect 的基础语义

不负责：

- coding-specific tool policy
- method resource 编译
- TUI 呈现
- 外部 transport

### loushang-coding

面向 coding 场景的产品装配层。

负责：

- 默认工具
- 默认策略
- coding workflow
- CLI 入口
- 与 `tui`、`method`、`work` 的产品化集成
- transitional RPC/JSONL mode adapter
- `loushang.coding.ui` 终端产品适配层
- session/runtime 与 terminal UI 的交互编排

不负责：

- 通用模型协议定义
- agent 核心类型系统
- 通用边界协议定义
- 通用 terminal UI primitives

## Layer Relationship

当前 V1 coding 产品的主链路为：

```text
loushang.coding
  -> loushang.agent
  -> loushang.ai
```

相邻集成链路为：

```text
loushang.method -> loushang.coding -> loushang.work
loushang.coding.ui -> loushang.tui
```

长期目标边界为：

```text
external host/client -> loushang.channel -> loushang.work -> domain app
```

其中：

- `ai` 提供模型接入能力
- `agent` 提供运行语义
- `channel` 提供目标边界通信，当前未作为源码包落地
- `tui` 提供通用终端交互原语
- `method` 提供方法组织与 plan/projection
- `work` 提供运行、事件、日志与 projection
- `coding` 提供场景装配，并通过 `loushang.coding.ui` 调用 `loushang.tui`

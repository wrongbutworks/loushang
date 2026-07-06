# Loushang Subsystems

## Scope

本文档定义 `loushang` 的主要子系统及其职责边界。
它关注系统分工，不展开实现细节、类型系统或边界协议。

## Subsystem List

当前已落地的核心包级子系统包括：

- `loushang.ai`
- `loushang.agent`
- `loushang.harness`
- `loushang.coding`
- `loushang.method`
- `loushang.tui`
- `loushang.work`

当前已落地的支撑/实验性包包括：

- `loushang.observability`
- `loushang.ontology`

`loushang.runtime` 不再作为子系统保留。若某个 worktree 中仍存在
`src/loushang/runtime`，它只是待删除的旧 command/effect 临时路径；迁移目标是
`loushang.harness.commands`，不保留 runtime shim。跨产品 host / adapter /
command substrate 的目标归属是 `loushang.harness`，见
[ARD-002: Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。

目标产品线概念包括：

- `loushang.design`
- `loushang.research`
- `loushang.ppt`
- `loushang.cowork`

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
- prepared agent run contract
- UI 渲染
- 跨边界 transport
- coding / design / research / ppt / cowork 产品语义
- work / method 投影语义

### loushang-harness

跨产品的 product-adapter substrate。当前已落地的核心是 prepared agent run
contract，后续 product-neutral host / adapter / command / lifecycle /
diagnostics 合同也归属这里。

负责：

- `AgentRunSpec`
- `AgentRunResult`
- `run_agent()`
- headless agent run 编排
- product-neutral adapter / prepared-turn / adapter-result contracts
- product-neutral host lifecycle contracts
- command/effect value objects
- generic diagnostics / status records

不负责：

- `Agent` 生命周期
- low-level agent loop ownership
- coding / design / research / ppt / cowork 产品语义
- work / method 投影语义
- provider auth / model default persistence
- TUI render loop、layout、input 或 screen state

`loushang.harness` 位于 low-level agent loop 之上，依赖 `loushang.agent` 并
复用现有 loop，不另写第二套 loop。`loushang.agent` 不依赖
`loushang.harness`。`AgentRunSpec`、`AgentRunResult` 和 `run_agent()` 是唯一
prepared-run contract，不引入第二套 `HarnessRunSpec`。原
`src/loushang/agent/harness` / `loushang.agent.harness` compatibility path 已删除；
新代码应从 `loushang.harness` import。详见
[Agent Harness and Product Adapter Boundaries](./agent/ARD-001-agent-harness-and-product-adapters.md)
和
[Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。

### loushang-channel (target)

边界协议与 transport 层。当前是目标架构概念，不是已落地 Python 包。

负责：

- operation / event protocol
- request / response correlation
- notification / subscription
- transport adapters, such as in-process, stdio/JSONL, HTTP, WebSocket
- capability negotiation
- delivery policy, such as immediate / coalesce / final-only
- replay / resume
- channel audit trail
- multi-client access to the same work run

不负责：

- agent 内核状态机
- 本地 UI 组件实现
- 方法层调度
- coding / design / research / ppt / cowork 产品内部 session
- 产品 adapter 注册之外的业务执行

`channel` 面向多客户端和多 UI：TUI、WebUI、AppUI、SDK host、RPC client
都应通过 channel 发送 operation、订阅 event、恢复和回放状态。channel core
承载 `WorkOperation` / `WorkEvent` 的边界传输语义；具体产品 adapter 由
host 装配，不由 channel core 直接 import。

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
- 普通产品 turn 的强制执行路径

`method` 是可选的结构化工作组织层。产品线可以在 plan / guided / staged
workflows 中使用 `method`，但轻量 turn 可以直接使用 `loushang.harness` 和
`work`。

### loushang-work

跨产品工作运行语义、事件日志与 projection 层。

负责：

- `WorkOperation`
- `WorkRun`
- `WorkEvent`
- future `ArtifactRef`
- artifact references / work product projections
- work event log
- plan/step lifecycle projection
- method run replay / inspect 的基础语义

不负责：

- coding-specific tool policy
- method resource 编译
- TUI 呈现
- 外部 transport
- coding / design / research / ppt / cowork 产品语义

`work` 是 coding、design、research、ppt、cowork 等产品线共享的工作事实与投影抽象。
它不依赖这些产品线，也不依赖 `method`。

Artifact 分层规则：

- `method` 定义 expected artifact，即结构化工作“应该产出什么”
- `work` 记录 actual artifact reference，即“实际产出了什么、在哪里、状态如何”
- `coding` / `design` / `research` / `ppt` / `cowork` 定义具体 artifact 类型、内容、
  加载、渲染、校验和物化逻辑

因此 `work` 层优先引入 `ArtifactRef`，而不是抽象 `Artifact` ABC。若未来需要
统一加载或渲染行为，应通过 provider/protocol 接口扩展，不把产品行为塞进
`work`。

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

`coding` 可以直接依赖 `loushang.harness` 和 `work` 处理普通 coding turn；只有
结构化 / guided 工作需要通过 `method`。

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

跨产品执行目标链路为：

```text
loushang.ai
  <- loushang.agent

loushang.agent
  <- loushang.harness
  <- loushang.coding / loushang.design / loushang.research / loushang.ppt / loushang.cowork
```

跨产品工作抽象链路为：

```text
loushang.work
  <- loushang.coding / loushang.design / loushang.research / loushang.ppt / loushang.cowork

loushang.work
  <- loushang.method
  <- product adapters, only for structured work
```

长期目标边界为：

```text
external host/client -> loushang.channel -> loushang.work -> domain app
```

其中：

- `ai` 提供模型接入能力
- `agent` 提供运行语义
- `harness` 提供跨产品 prepared-run contract 以及 product-neutral host /
  adapter / command substrate
- `channel` 提供目标边界通信，当前未作为源码包落地
- `tui` 提供通用终端交互原语
- `method` 提供可选的方法组织与 plan/projection
- `work` 提供运行、事件、日志与 projection
- `coding` 提供 coding 产品装配，并通过 `loushang.coding.ui` 调用
  `loushang.tui`
- `design`、`research`、`ppt`、`cowork` 是目标产品线概念，和 `coding` 并列，而不是
  `work` 或 `agent` 的子层

## Future Dependency Map

目标二级组件依赖关系。本节中 `A -> B` 表示 `A` 可以依赖 / 调用 `B`。

```text
all packages -> observability

method / work / product packages -> ontology
  # only when semantic typing is needed

agent -> ai
product packages -> ai
  # only for product-level helper AI calls

harness -> agent
product packages -> harness
product packages -> agent
  # only through stable agent primitives when bypassing harness is justified

method -> work
product packages -> work
channel -> work

product packages -> method
  # optional and only for structured work

product TUI adapters -> tui

UI clients / SDK hosts / RPC clients -> channel
```

Product packages are peers:

```text
coding
design
research
ppt
cowork
```

Product packages should not depend on each other directly. Cross-product
coordination should go through explicit adapters, `work` events, `channel`
protocol, or a future host-level orchestration layer.

Multi-UI target shape:

```text
TUI / WebUI / AppUI / SDK / RPC client
  -> channel client
  -> channel server / host assembly
  -> WorkOperation / WorkEvent
  -> product adapter
  -> harness
```

The channel core transports and replays work operations/events. It does not
render UI and does not own product execution internals.

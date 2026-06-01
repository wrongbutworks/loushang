# Loushang Work / Method / Channel / Harness 目标架构草案

## Status

Draft.

本文档是 `loushang-runtime-architecture.md` 的中文补充设计。它把前期讨论
收敛成一套可渐进落地的目标架构，重点覆盖：

- `loushang.channel`
- `loushang.work`
- `loushang.method`
- `loushang.agent.harness`
- `DomainApp`
- 第一版 `coding` domain app
- method 资源化与现有 skill 生态兼容
- 多 agent 协作
- 保持 coding 快速使用路径

本文档仍是架构草案，不是详细实现计划。

## 核心判断

`loushang` 不应继续被建模为一个 coding-first CLI/TUI，也不应把未来能力
塞进现有 `AgentSession` 或 `loushang.agent`。

目标架构应把 `loushang` 建模为一个 **method-guided work operating layer**：

```text
Hosts / Products / SDK
  CLI / TUI / GUI / HTTP / WebSocket / stdio
  WeChat / Feishu / mini app
  Hermes / OpenClaw / Manus / upper-level orchestrators

        |
        v

loushang.channel
  channel adapters
  inbound normalization
  outbound delivery
  channel capability
  delivery policy projection
  reconnect / reply / edit / final-only

        |
        v

loushang.work
  WorkOperation
  WorkRun
  WorkEvent
  WorkSession
  TaskFlow
  AgentLane
  ArtifactRef
  ApprovalRequest
  MethodRun
  Scheduler
  EventLog

        |
        v

loushang.method
  MethodDescriptor
  MethodLoader
  MethodRegistry
  MethodSelector
  MethodCompiler
  MethodProjector
  skill-backed method compatibility

        |
        v

Domain Apps
  loushang.coding
  loushang.research
  loushang.cowork
  loushang.ppt
  loushang.evolution

        |
        v

loushang.agent.harness
  one prepared agent turn
  turn phase / turn snapshot
  steer / follow-up / next-turn queues
  save point / settled events
  hooks / session write ordering
  AgentEvent -> HarnessEvent

        |
        v

loushang.agent + loushang.ai
  low-level agent loop
  model/provider streaming
  tool call / tool result semantics
```

## 命名边界

### 为什么不是 `loushang.runtime`

`runtime` 容易和以下概念混淆：

- Python/Node runtime
- model runtime
- agent loop runtime
- TUI runtime
- extension runtime

因此不建议把目标控制面继续命名为 `loushang.runtime`。

### 为什么不是 `loushang.platform`

`platform` 太泛，容易变成所有共享代码的收纳层。目标架构需要一个更具体的名
字来表达“工作过程、运行状态、事件、产物和方法执行”。

### 推荐名称：`loushang.work`

`work` 表达的是：

- 一件事被提交
- 被拆解为 run / task / step
- 被 method 指导
- 由 domain app 执行
- 产生 artifact
- 经 approval / evaluation / replay 闭环

它比 `runtime` 更贴近语义，也比 `platform` 更收敛。

## 分层职责

### `loushang.channel`

`channel` 是外部入口与交付出口，不是业务运行时。

负责：

- 接收外部输入
- 归一化 inbound event
- 解析外部身份与会话来源
- 把输入转换成 `WorkOperation`
- 声明通道能力
- 按能力渲染 `WorkEvent`
- 执行 outbound delivery
- 支持 reconnect、reply、edit、attachment、final-only、streaming

不负责：

- method 选择
- 多 agent 调度
- tool policy
- coding workflow
- session/run 生命周期

核心对象：

```text
ChannelAdapter
ChannelInbound
ChannelOutbound
ChannelCapability
DeliveryPolicy
DeliveryAddress
ExternalIdentity
ConversationAddress
```

`ExternalIdentity`、`ConversationAddress`、`DeliveryAddress` 可以作为共享 value
objects 由 `channel` 生产、由 `work` 记录、由 delivery 使用。它们不应把
channel-specific SDK 类型泄漏到 `work` 内部。

### `loushang.work`

`work` 是控制面。它知道“工作如何被提交、路由、调度、记录、取消、恢复和交
付”。

负责：

- 接收 `WorkOperation`
- 创建和管理 `WorkRun`
- 管理 `WorkSession`
- 建立 run / session / task / artifact / channel 的关联
- 维护 `TaskFlow`
- 管理 `AgentLane`
- 发出 `WorkEvent`
- 写入 `EventLog`
- 管理 `ArtifactRef`
- 处理 `ApprovalRequest`
- 调用 `method` 做选择与编译
- 调用 `DomainApp` 执行业务步骤
- 为 scheduler / replay / SDK 提供统一入口

不负责：

- channel 具体收发
- coding 工具细节
- 低层模型 provider
- 单次 agent turn 内部状态机

核心对象：

```text
WorkOperation
WorkRun
WorkEvent
WorkSession
TaskFlow
TaskRun
AgentLane
ArtifactRef
ApprovalRequest
MethodRun
EventLog
DomainAppRegistry
Scheduler
```

### `loushang.method`

`method` 是方法资产与方法编译层。它提供“怎么做事”的结构，但不直接执行工
具，也不直接推进 agent loop。

负责：

- 发现 method 资源
- 解析 method metadata
- 兼容现有 skill
- 注册 method
- 根据上下文选择 method
- 把 method 编译成 `MethodPlan`
- 把当前 step 投影成 prompt / skill / tool / artifact / gate guidance

不负责：

- `WorkRun` 状态持久化
- 多 agent 调度
- 文件编辑、测试执行
- channel delivery

核心对象：

```text
MethodDescriptor
MethodLoader
MethodRegistry
MethodSelector
MethodCompiler
MethodPlan
MethodProjector
MethodTrace
```

其中 `MethodRun` 的运行状态建议归 `loushang.work`，因为它需要和
`WorkRun`、`TaskRun`、`ArtifactRef`、`ApprovalRequest` 统一记录。

### `DomainApp`

`DomainApp` 是领域能力提供者。第一版只实现 `loushang.coding`。

负责：

- 声明 domain id
- 声明支持的 operation kind
- 声明可用工具、策略、artifact 类型
- 提供 domain-specific prompt 和 method packs
- 把 `MethodStep` 映射成 domain task
- 调用 `agent.harness` 或其他执行器

不负责：

- channel protocol
- 通用 work run 生命周期
- 通用 method loader
- 通用 agent harness

第一版 `coding` domain app 负责：

```text
coding tools
coding policy
coding prompt resources
coding artifacts: patch / test_report / review_finding / summary
coding method packs: bugfix / review / tdd
```

### `loushang.agent.harness`

`agent.harness` 是 **一次 prepared agent turn 的执行器**。

负责：

- turn phase
- turn snapshot
- steer / follow-up / next-turn queue
- save point
- settled event
- context / provider / tool hooks
- session write ordering
- `AgentEvent` 到 `HarnessEvent` 的提升

不负责：

- channel
- work run
- task flow
- method selection
- multi-agent team
- domain workflow

这个边界与 Pi 的 AgentHarness、OpenClaw 的 agent harness 思路一致：harness
不是 provider，不是 channel，不是 tool registry，也不是上层工作流引擎。

## Operation / Event 模型

### WorkOperation

`WorkOperation` 是外部输入进入 `work` 的统一意图对象。

第一版建议包含：

```text
SubmitTurn
SubmitSteer
SubmitFollowUp
InterruptRun
CancelRun
Approve
Reject
InvokeCommand
StartWorkflow
StartTeamRun
AttachArtifact
OpenSurface
ResumeSession
```

Coding 第一版可以只实现：

```text
SubmitCodingTurn
StartCodingTask
StartCodingWorkflow
StartCodingTeamRun
InterruptRun
Approve
Reject
```

### WorkEvent

`WorkEvent` 是 `work` 层输出事实。它可以由 `AgentEvent` 投影而来，也可以由
`work`、`method`、`domain app` 自己产生。

建议第一版事件：

```text
OperationAccepted
WorkRunStarted
WorkRunCompleted
WorkRunFailed
TaskStarted
TaskCompleted
TaskFailed
MethodSelected
MethodPlanCreated
MethodStepStarted
MethodStepCompleted
ContentDelta
ToolCallStarted
ToolCallCompleted
ApprovalRequested
ApprovalResolved
ArtifactCreated
ArtifactUpdated
SurfaceRequested
OperationFailed
```

现有 `loushang.agent.AgentEvent` 不应废弃。关系应是：

```text
AgentEvent
  low-level: turn_start / message_update / tool_execution_start / ...

HarnessEvent
  AgentEvent + harness-owned events

WorkEvent
  HarnessEvent + run/session/task/channel/domain/method metadata
```

## Method 资源化原则

具体方法不能写死在代码里。

代码里只保留稳定 runtime：

```text
MethodLoader
MethodRegistry
MethodSelector
MethodCompiler
MethodProjector
```

具体方法来自资源：

```text
methods/**/METHOD.md
methods/**/SKILL.md
skills/**/SKILL.md
```

### 极简退化路径

一个 method 最小可以退化成一个普通 skill：

```markdown
---
name: bugfix
description: Debug and fix a failing behavior.
---

Read the failure carefully.
Reproduce before editing.
Make the smallest safe change.
Run verification before final response.
```

这个文件没有 steps、roles、gates、artifacts，仍然可以运行。

编译结果：

```text
MethodPlan
  mode: single_turn
  steps:
    - id: main
      executor: current_agent
      projection: inject method content as guidance
```

这保证第一版即使只有简单 skill，也能跑通。

### 兼容现有 skill 生态

现有 `skills/**/SKILL.md` 必须保持兼容：

- 不要求改格式
- 不要求迁移目录
- 仍出现在 `<available_skills>`
- 仍可通过显式 skill 调用加载

新增兼容规则：

```text
SkillDescriptor
  -> MethodDescriptor(kind="skill_backed", id="skill:<name>")
```

也就是说，任何现有 skill 都可以作为一个单步 method 使用：

```text
/method skill:debugging
```

或由 `MethodSelector` 在高置信度场景下轻量选择。

### 增强 method

复杂 method 可以逐步增加 metadata：

```yaml
---
id: software/bugfix
name: Bugfix
description: Reproduce, fix, and verify a bug.
domain: coding
execution_mode: fixed
applicability:
  when:
    - failing test
    - runtime error
roles:
  - investigator
  - implementer
  - verifier
steps:
  - id: reproduce
    role: investigator
    goal: reproduce the failure
  - id: fix
    role: implementer
    goal: make the smallest safe change
  - id: verify
    role: verifier
    goal: run targeted tests
uses_skills:
  - debugging
artifacts:
  - failure_summary
  - patch
  - test_report
gates:
  - before_destructive_command
  - before_public_api_change
---
```

这些字段仍是资源声明，不是代码里的 hardcoded branch。

## 多 Agent 协作

多 agent 协作不应放进 `agent.harness`。它属于 `work` 层。

### 协作层对象

```text
TaskFlow
  多步骤工作流。

TaskRun
  一个具体任务实例。

AgentLane
  一个 agent 执行通道，绑定 role / session / workspace / tool scope。

TaskLedger
  任务、依赖、claim、heartbeat、status 的共享账本。

CollaborationBus
  agent 间消息、conductor 指令、人类介入记录。

ArtifactRef
  patch、test report、review finding、summary 等产物引用。

ApprovalRequest
  高风险动作、人类确认、策略门。
```

### 第一版协作模式

第一版不需要直接实现完整 team platform。建议支持三档：

```text
Single Agent
  默认快速 coding 路径。

Method-Guided Single Agent
  method 只注入 guidance，不改变执行形态。

Controlled Workflow
  method 编译出固定 steps，work 顺序推进。
```

随后再扩展：

```text
Subagent
  主 agent 委派短任务，子 agent 返回结果。

Team Run
  多个 AgentLane 长期协作，共享 TaskLedger。
```

### Coding 第一版角色

Coding domain app 可以定义这些 role/lane，但它们也应来自 method resource，
不是写死在 runtime：

```text
planner
  只读，产出 plan。

investigator
  只读或有限执行，复现问题。

implementer
  可编辑，产出 patch。

tester
  可运行测试，产出 test_report。

reviewer
  只读，产出 review_finding。

integrator
  汇总产物，生成 final summary，必要时执行合并。
```

默认权限应保守：

- planner / reviewer 默认 read-only
- tester 可以执行测试但不编辑
- implementer 可以编辑，但应尽量在 isolated worktree
- integrator 负责最终 apply / merge

## Coding 快速路径

第一版必须保留现有快速体验：

```text
loushang "fix this bug"
```

不应默认启动复杂 method plan 或多 agent team。

默认路径：

```text
CLI/TUI input
  -> channel adapter
  -> SubmitCodingTurn
  -> WorkRun(single_turn)
  -> existing AgentSession.prompt()
  -> AgentEvent projection
  -> WorkEvent stream
  -> channel delivery
```

只有以下情况才升级：

- 用户显式选择 method
- 用户显式请求 workflow / multi-agent / review / full verification
- 风险高
- 任务复杂度超过单 turn 阈值
- method selector 高置信度匹配 deep workflow

建议模式：

```text
fast
  no method or skill-backed method

guided
  single-turn method projection

workflow
  fixed MethodPlan / TaskFlow

team
  multi-agent AgentLane
```

## 第一版范围

### P0: WorkRun 包装现有 AgentSession

目标：不改变用户体验，先建立 work 外壳。

范围：

- 新增 `WorkOperation`
- 新增 `WorkRun`
- 新增 `WorkEvent`
- 新增 `EventLog` 最小接口
- 包装现有 `AgentSession.prompt()`
- 将现有 `AgentEvent` 投影为 `WorkEvent`
- `WorkEvent` 增加 `run_id`、`session_id`、`domain`、`operation_id`

不做：

- 多 agent
- method workflow
- 复杂 scheduler

### P1: Method 资源兼容

目标：method 最小退化成 skill，兼容现有 skill 生态。

范围：

- 新增 `MethodDescriptor`
- 扩展 resource loader 或增加 method loader
- `SkillDescriptor -> skill-backed MethodDescriptor`
- 支持 `methods/**/METHOD.md`
- 支持 `methods/**/SKILL.md`
- 支持 single-turn `MethodPlan`
- method projection 注入 prompt
- `WorkRun` 记录 `method_id`

### P2: Coding DomainApp

目标：把现有 coding 能力作为第一版 domain app 暴露。

范围：

- `CodingDomainApp`
- coding operation kind
- coding artifact types
- coding policy bridge
- coding method packs as resources
- 现有 command/session/tool 逐步通过 domain app 适配

### P3: Fixed MethodPlan / TaskFlow

目标：支持可审计的多步骤方法执行。

范围：

- `MethodCompiler`
- `TaskFlow`
- `TaskRun`
- step started/completed events
- artifact created/updated events
- approval gate

### P4: Controlled Subagent

目标：最小多 agent 协作。

范围：

- `AgentLane`
- read-only reviewer/planner lane
- implementer lane
- tester lane
- task assignment
- result aggregation

不做完整 autonomous team，先保证可控。

## 现有代码迁移关系

### `AgentSession`

当前 `AgentSession` 很厚，包含 tool、prompt、queue、compaction、extensions、
commands、session store 等职责。

迁移方向：

```text
现阶段:
  AgentSession 仍作为 coding runtime facade。

P0:
  WorkRun 包装 AgentSession.prompt()。

P1/P2:
  method projection 和 coding domain app 从外部装配 AgentSession。

后续:
  AgentSession 逐步退化成 CodingSessionFacade。
```

### `AgentSessionRuntime`

当前只管理一个 current session 和一个 rebind callback。

迁移方向：

```text
AgentSessionRuntime
  -> WorkSessionRegistry
  -> SessionController
  -> multi-session / multi-lane support
```

### `QueueController`

当前 queue 是单 agent turn 的 steering/follow-up queue。

迁移方向：

```text
QueueController
  保留给 agent.harness / single-agent turn。

WorkQueue / TaskQueue
  新增给 work/task/multi-agent 调度。
```

### `coding.workflow.runner`

当前 workflow runner 更适合作为测试、playback 和固定场景验证工具。

迁移方向：

```text
短期:
  继续用于 workflow scenario 测试。

中期:
  MethodPlan/TaskFlow 可以复用其经验，但生产调度放到 work。
```

### `RpcMode`

当前 RPC mode 直接解析 JSON line 并调用 session 方法。

迁移方向：

```text
RPC request
  -> WorkOperation
  -> WorkRun / WorkEvent
```

## 自外而内与自内而外

### 自外而内

外部用户和 host 只看到：

```text
submit operation
subscribe events
wait/cancel run
list artifacts
approve/reject request
```

外部不需要知道内部是 single agent、method workflow、还是 multi-agent team。

### 自内而外

内部从现有能力渐进抽象：

```text
AgentEvent
  -> HarnessEvent
  -> WorkEvent

AgentSession.prompt()
  -> WorkRun(single_turn)

SkillDescriptor
  -> skill-backed MethodDescriptor

coding workflow tests
  -> MethodPlan / TaskFlow validation
```

## 成功标准

第一版成功标准不是“完整超越所有 agent 产品”，而是：

- 现有 coding 快速路径不变慢
- 每次 coding turn 都有 `WorkRun`
- 每个重要输出都有 `WorkEvent`
- method 可以像 skill 一样被发现、启用、禁用、覆盖
- 一个普通 skill 可以作为最小 method 使用
- 一个增强 method 可以编译成单步 `MethodPlan`
- coding domain app 可以作为第一版 domain app 运行
- 后续多 agent / workflow 不需要重写 channel 或 agent loop

## 非目标

第一版不追求：

- 完整 autonomous team
- 完整 GUI
- 所有 channel adapter
- 完整 self-evolution
- 复杂 method DSL
- 替换现有 AgentSession

第一版的重点是把边界立住：

```text
channel handles delivery
work handles run/task/event/artifact
method handles guidance/plan assets
domain app handles domain execution
harness handles one prepared turn
agent/ai handle low-level model loop
```

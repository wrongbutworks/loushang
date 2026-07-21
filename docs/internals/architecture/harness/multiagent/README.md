# Loushang Multi-Agent Architecture

> Status: **draft proposal**（目标设计，未经接受）。本目录的所有文档
> 表达 should-be 的目标边界，不描述当前实现状态；与代码冲突时以代码
> 与已接受 ARD 为准（见
> [Loushang Documentation Model](../../loushang-documentation-model.md)）。

`loushang.harness.multiagent` 提供子 agent 的派生、隔离、通信与生命
周期管控——是**纯技术态**能力：它不理解 stage / acceptance / artifact
等业务语义；业务编排（method / work）经产品装配层间接消费本能力。

## Reading Order

1. [System Context](system-context.md)
   黑盒边界：直接上游（产品装配层）、直接下游（harness prepared run）、
   逻辑 actor（parent agent、user/host）；明确不在边界上的子系统。
2. [Candidate Components](candidate-components.md)
   8 个候选组件的职责、独立性理由与参照来源。
3. Accepted-direction ARDs:
   - [ARD-001: Harness Ownership](ARD-001-harness-ownership.md) —
     为什么是 `loushang.harness.multiagent` 而非顶层包或 agent 内核。
   - [ARD-002: Async-Only Execution And Recovery](ARD-002-async-execution-and-recovery.md) —
     一期全异步、消息驱动恢复、open/closed 区分。
4. Component boundaries（按依赖序阅读）:
   - [Tool Surface](tool-surface-boundary.md) — 模型可见的三件套
     （spawn_agent / send_message / wait_agent）与提示纪律。
   - [Control](control-boundary.md) — spawn 流水线与消息路由的编排。
   - [Registry](registry-boundary.md) — AgentPath 寻址、两阶段预留、
     树拓扑。
   - [Run Handle](run-handle-boundary.md) — 子 agent 运行载体：多轮
     驱动、取消双模式、事件转接。
   - [Agent Input Facade](agent-input-facade-boundary.md) — 通知合成
     与 wait 原语（复用 HostInputQueue）。
   - [Context Fork](context-fork-boundary.md) — 隔离矩阵、fork 档位、
     历史过滤、审批冒泡装配、可参数化 `fork_history()`。
   - [Limits And Projection](limits-and-projection-boundary.md) — 并发
     闸门、depth 上限、驻留回收（二期）、生命周期状态机与事实。

## Core Invariants

所有组件与注入缝必须遵守的不变式（产品/OEM 可定制策略，不可改写
这些语义）：

1. **不写第二套 agent loop**：子 agent 本体是 `run_agent(AgentRunSpec)`
   的 prepared run 重入。
2. **默认隔离，显式共享**：子上下文默认全隔离；任务注册穿透 root；
   审批冒泡到 root 交互出口。
3. **全异步 + 通知**：无同步 spawn；结果经完成通知到达；wait 等自己
   input 的 activity，不轮询子状态。
4. **先状态后收尾**：终态事实先于清理/汇总；收尾失败不反转状态。
5. **open / closed 区分**：close 后不可寻址；open 的 idle/终态 agent
   可被消息唤醒。
6. **fork 的字节约束**：fork 档的父前缀字节级一致；历史过滤确定性；
   fork 档不可改 model。
7. **机制写死、策略注入**：上限值、过滤规则、通知模板、纪律文本等
   是产品/OEM 注入缝；组件语义不变式不是。

## Relationship To Other Subsystems

- `loushang.harness`：本目录归属其中；复用其 `run_agent`、
  `HostInputQueue`、`ApprovalRequest`、transcript（fork 历史源）、
  host lifecycle 编排。
- `loushang.agent`：提供 agent loop 与稳定原语；multiagent 不扩大其
  内核语义。
- `loushang.method` / `loushang.work`：业务态编排层；method 角色可
  编译为 agent 类型（装配层职责），work 可消费 agent 树事实做业务
  投影——multiagent 不依赖它们。
- `loushang.channel`：未来承载远端/多客户端订阅；multiagent 的事实
  经装配层投影后才可能进入 channel。
- 产品装配层（coding / design / …）：注入类型注册表、策略参数、
  事件消费者、审批出口；决定工具面暴露范围。

## Evolution Path

1. **一期**：三件套工具、全异步、消息驱动唤醒、内存 registry、无回收。
2. **二期**：LRU 驻留回收（状态外置 + 透明重载）、同步 spawn（增量）、
   transcript 持久化拓扑。
3. **远期**：远端子 agent（channel 承载 transport）、method 编排的
   stage 级派生与验收（业务态结合点，属 method/work 侧设计）。

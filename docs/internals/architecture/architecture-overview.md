# Loushang Architecture Overview

## Scope

本文档只描述 `loushang` 的技术架构。
业务定位、愿景、使命与品牌叙事请参见 [Loushang Strategy](../strategy/strategy.md)。

## 架构原则

`loushang` 采用“内核 + 协议 + 适配器 + 扩展点”的分层架构。内核定义系统的运行语义，协议定义系统与外部世界的沟通边界，适配器连接不同环境与终端形态，扩展点则在不破坏内核一致性的前提下开放可编程能力。四者共同构成 `loushang` 的基础架构：内核保证一致性，协议保证可连接性，适配器保证可达性，扩展点保证可演化性。

`loushang` 以内核承载语义，以协议连接边界，以适配器触达环境，以扩展点驱动演化。

## Architecture Evaluation Lens

评估 Loushang 时，应区分“当前开箱即用的 Agent 功能数量”和“系统长期需要
保持稳定的语义 substrate”。Loushang 有意不把某一代模型需要的 planner、
reflection、todo reminder、通用 verifier prompt 或工具选择启发式固化进
Agent 内循环。模型能力可以吞噬这些认知脚手架，但不应吞噬权限、副作用控制、
证据、持久化、协调和 Work truth。

以下是理解当前架构价值的主要视角：

| 设计 | 架构价值 | 不应误读为 |
|---|---|---|
| `ai` 与小型 `agent` 执行内核 | Provider 变化和模型能力升级不要求重写 Product/Work 语义 | Agent Loop 应内置 planner、verifier 或产品 workflow |
| Product -> Harness -> Agent -> AI 的单向依赖 | 跨产品机制复用，同时阻止 Coding 语义污染底层 | Harness 是第二套 Agent Loop |
| Conversation、Transcript、Runtime Event、Work Event 分层 | 区分交互记录、执行事实与业务权威事实 | 一份 checkpoint 或消息日志可以替代全部状态 |
| Method 与 Work 分离 | Method 规定什么必须成立；模型决定怎样达到；Work 记录本次实际履约 | MethodPlan、模型 todo 和一次 Agent invocation 是同一对象 |
| Policy、Approval、Enforcement 分离 | 同一 action model 支撑决策、同意、强制执行和审计，委派权限只能收窄 | 提示模型“不要越权”就是安全边界 |
| TUI、HarnessTUI 与 Product presentation 分离 | 终端机制、对话交互和产品语义可独立演进、测试和复用 | TUI 必须理解 Agent/AI/Coding 对象 |
| terminal playback | 将输入、streaming、resize、surface、光标和终端操作序列变成可执行回归契约 | 只对最终屏幕文本做 snapshot，或等同于 Session transcript replay |

这些优点不意味着当前能力面已经完整。通用图执行、远端 multi-agent、持久
审批和 managed runtime 仍有明确缺口。架构评价应同时报告“能力是否已实现”
和“该能力应由哪个 owner 实现”，不能因为某个可选认知脚手架尚未内置，就把
它错误记为 Agent 内循环缺陷。

### Playback 是 TUI 的可执行规范

Loushang TUI playback 不等同于重放历史消息。它把脚本化输入和运行事件送入
真实的输入解码、路由、render planning 与 terminal-operation 边界，并逐步记录
逻辑行、changed range、viewport、光标、repaint 原因、scrollback policy、
终端操作和可选 frame。更高层的 HarnessTUI playback 还记录 neutral action
result、conversation state，并可用 scripted TTY chunks 运行真实 screen loop。

因此 playback 能验证普通 final-screen golden 难以发现的问题：中间帧闪烁、
重复 transcript、resize/reflow 漂移、错误清屏、scrollback 破坏、光标错位、
streaming 每 token 产生一个 block、surface focus 顺序、steer/follow-up/abort
路由以及跨 feature 交互回归。它也能输出 JSONL trace、screen、terminal 和 state
artifact，并对操作数、输出字节、changed lines、同步 frame 和长 transcript
性能设置预算。

这是一项对模型和 Product 都相对稳定的能力：模型输出策略可以变化，不同
Product 可以复用相同机制，而终端交互和渲染不变量仍能通过同一套
Product-neutral playback substrate 验证。详细设计见
[TUI Architecture](./tui/README.md)、
[Terminal Playback Harness](./tui/native-terminal-core/key-designs/KD-010-terminal-playback-harness.md)
和 [HarnessTUI](./harnesstui/README.md#conversation-playback-testing)。

## Monorepo Subsystem Map

`loushang` 采用 monorepo 组织。当前阶段按统一根 Python project 组织各子系统源码，而不是先拆成多个独立 Python packages。

当前已经落到 Python 包级源码的主要子系统包括：

- `loushang.ai`
- `loushang.agent`
- `loushang.channel`
- `loushang.coding`
- `loushang.harness`
- `loushang.harnesstui`
- `loushang.method`
- `loushang.tui`
- `loushang.work`
- `loushang.observability`
- `loushang.ontology`
- `loushang.protocol`

`loushang.channel` 提供承载 `WorkOperation` / `WorkEvent` 以及已投影
`RuntimeEventView` 的边界协议，及 `rpc_jsonl` 的 JSONL framing、request
correlation、accepted ACK 和 event delivery。Channel 仅消费 Harness 的纯
runtime-view 值契约，Harness 不反向依赖 Channel。现有
`loushang.coding.mode.RpcMode` 仍是 Coding-local transitional surface；它的
命令表和 UI payload 不属于 Channel。

当前仓库结构应按已落地包理解：

```text
loushang/
  docs/
  src/
    loushang/
      ai/
      agent/
      channel/
      coding/
      harness/
      harnesstui/
      method/
      tui/
      work/
      observability/
      ontology/
      protocol/
  tests/
```

`loushang.runtime` 不再作为保留子系统。若某个 worktree 在 command/effect
迁移完成前仍存在该路径，它只是待删除的旧临时路径；相关类型迁到
`loushang.harness.commands` 后应删除。

## Subsystem Documentation

子系统划分与职责边界请参见 [Loushang Subsystems](./subsystem.md)。
子系统关系图请参见 [Loushang Subsystem Diagram](./subsystem-diagram.md)。
跨层架构判断准则请参见 [Loushang Architecture Principles](./loushang-architecture-principles.md)。
文档分层与阅读规则请参见 [Loushang Documentation Model](./loushang-documentation-model.md)。
`loushang-tui` 子系统文档请参见 [Loushang-TUI Architecture](./tui/README.md)。
`loushang-harnesstui` 的中性 conversation composition 与 playback testing
边界请参见 [Loushang Harness TUI](./harnesstui/README.md)。
`loushang-harness` 的产品适配器 substrate 方向请参见
[ARD-002: Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。
`loushang-work` 的业务工作与方法履约边界请参见
[Loushang Work Architecture](./work/README.md)。

## Architecture Stack

当前 V1 coding 产品的核心运行链路为：

```text
CLI / TUI
  -> loushang.coding Product composition
  -> loushang.harness Session / prepared run
       -> loushang.agent loop
            -> loushang.ai provider adapters
       -> tools / policy / approval / sandbox / events
```

相邻能力层：

- `loushang.method` 提供 method resource、compile、projection 和 fixed
  `MethodPlan` 语义；method 是面向一类任务的结构化工作契约
- `loushang.work` 接受具有可判定终局的业务意图，拥有 `WorkRun`、可选 method
  plan/step 的真实履约、权威终态、`WorkEvent`、event log、query 和 replay
- `loushang.tui` 提供通用 terminal-native UI primitives；
  `loushang.harnesstui` 组合 product-neutral Harness conversation 与 TUI；
  Coding feature-local adapter 解释产品状态，`loushang.coding.ui` 只保留最终
  UI 装配、具体 surface 与 terminal binding
- `loushang.channel` 提供 Work boundary protocol 和窄 JSONL framing adapter；
  capability negotiation 与 interaction request/response 仍是后续工作

其中：

- `agent` 定义 agent loop 与运行语义
- `ai` 定义模型/provider/streaming/tool-call 兼容层
- `method` 提供方法资产与 plan/projection，定义角色、阶段、流程、约束、工作产物与验收预期
- `work` 提供业务 work 的 acceptance、run/plan/step lifecycle、terminal
  outcome、event log、query 和 replay；Method 可选
- `tui` 提供通用终端 UI primitives
- `harnesstui` 提供可跨产品复用的 Harness/TUI conversation interaction 与
  presentation composition；依赖 `harness` 和 `tui`，不依赖 `coding`
- `coding` 提供产品化装配；产品语义留在 feature-local adapter，
  `loushang.coding.ui` 只完成最终 UI composition 与 terminal binding
- `channel` 定义边界通信协议类型，当前已落地最小 envelope / endpoint surface
- `protocol` 提供不依赖产品、Harness、Agent 或 AI 的严格 JSON wire-value
  algebra，供上述层共同使用

## Agent and Channel Documentation

当前 agent / channel 相关文档包括：

- [Loushang-AI Architecture](./ai/README.md)
- [Loushang Channel Architecture](./channel/README.md)
- [Loushang AI Glossary](../glossary/loushang-ai.md)
- [Loushang AI Types](../glossary/loushang-ai-types.md)
- [Loushang Agent](../glossary/loushang-agent.md)
- [Loushang Agent Types](../glossary/loushang-agent-types.md)
- [Loushang Channel Glossary](../glossary/loushang-channel.md)
- [Loushang Product And OEM Glossary](../glossary/loushang-product.md)
- [Loushang Product And OEM Chinese Terms](../glossary/loushang-product-zh.md)
- [Legacy Channel Boundary Protocol](../legacy/loushang-channel-boundary-protocol.md)

## Next Steps

下一步建议继续完善：

1. `loushang.work` 的 run-bound plan binding、动态输入与 outcome 验证
2. channel capability negotiation and interaction request/response contracts
3. TUI method status layer 与 `WorkEvent` / `WorkPlanRun` projection
4. public CLI reference 对 Method、Work 与 Resource Package surfaces 的补齐

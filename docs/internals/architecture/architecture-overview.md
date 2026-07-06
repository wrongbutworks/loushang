# Loushang Architecture Overview

## Scope

本文档只描述 `loushang` 的技术架构。
业务定位、愿景、使命与品牌叙事请参见 [Loushang Strategy](../strategy/strategy.md)。

## 架构原则

`loushang` 采用“内核 + 协议 + 适配器 + 扩展点”的分层架构。内核定义系统的运行语义，协议定义系统与外部世界的沟通边界，适配器连接不同环境与终端形态，扩展点则在不破坏内核一致性的前提下开放可编程能力。四者共同构成 `loushang` 的基础架构：内核保证一致性，协议保证可连接性，适配器保证可达性，扩展点保证可演化性。

`loushang` 以内核承载语义，以协议连接边界，以适配器触达环境，以扩展点驱动演化。

## Monorepo Subsystem Map

`loushang` 采用 monorepo 组织。当前阶段按统一根 Python project 组织各子系统源码，而不是先拆成多个独立 package。

当前已经落到 Python 包级源码的主要子系统包括：

- `loushang.ai`
- `loushang.agent`
- `loushang.channel`
- `loushang.coding`
- `loushang.harness`
- `loushang.method`
- `loushang.tui`
- `loushang.work`
- `loushang.observability`
- `loushang.ontology`

`loushang.channel` 已有最小协议类型包，用于承载 `WorkOperation` /
`WorkEvent` 边界消息。现有 RPC/JSONL 能力仍先作为
`loushang.coding.mode.RpcMode` 的 transitional surface 存在；后续 channel
层成熟后再上提为 `loushang.channel.rpc_jsonl` 等 adapter。

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
      method/
      tui/
      work/
      observability/
      ontology/
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
`loushang-harness` 的产品适配器 substrate 方向请参见
[ARD-002: Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。

## Architecture Stack

当前 V1 coding 产品的核心运行链路为：

```text
CLI / TUI
  -> loushang.coding bootstrap / runtime / session
  -> loushang.agent loop
  -> loushang.ai provider adapters
  -> tools / events / store / diagnostics / modes
```

相邻能力层：

- `loushang.method` 提供 method resource、compile、projection 和 fixed
  `MethodPlan` 语义；method 是面向一类任务的结构化工作契约
- `loushang.work` 提供 `WorkOperation`、`WorkRun`、`WorkEvent`、work event
  log 与 plan/step projection
- `loushang.tui` 提供通用 terminal-native UI primitives，`loushang.coding.ui`
  将 coding session 状态适配到 TUI
- `loushang.channel` 提供最小边界协议类型；具体 transport adapter 仍是后续工作

其中：

- `agent` 定义 agent loop 与运行语义
- `ai` 定义模型/provider/streaming/tool-call 兼容层
- `method` 提供方法资产与 plan/projection，定义角色、阶段、流程、约束、工作产物与验收预期
- `work` 提供 run/event/log/projection
- `tui` 提供通用终端 UI primitives
- `coding` 提供产品化装配，并通过 `loushang.coding.ui` 连接 coding core 与 `loushang.tui`
- `channel` 定义边界通信协议类型，当前已落地最小 envelope / endpoint surface

## Agent and Channel Documentation

当前 agent / channel 相关文档包括：

- [Loushang-AI Architecture](./ai/README.md)
- [Loushang Channel Architecture](./channel/README.md)
- [Loushang AI Glossary](../glossary/loushang-ai.md)
- [Loushang AI Types](../glossary/loushang-ai-types.md)
- [Loushang Agent](../glossary/loushang-agent.md)
- [Loushang Agent Types](../glossary/loushang-agent-types.md)
- [Loushang Channel Glossary](../glossary/loushang-channel.md)
- [Legacy Channel Boundary Protocol](../legacy/loushang-channel-boundary-protocol.md)

## Next Steps

下一步建议继续完善：

1. `loushang.work` 与 method plan/step failure projection 的硬化
2. `loushang.channel.rpc_jsonl` adapter 草案和 operation/event delivery 行为
3. TUI method status layer 与 `WorkEvent` / `WorkPlanRun` projection
4. public CLI reference 对 method/work/package surface 的补齐

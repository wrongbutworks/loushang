# Loushang Architecture Overview

## Scope

本文档只描述 `loushang` 的技术架构。  
业务定位、愿景、使命与品牌叙事请参见 [Loushang Strategy](../strategy/strategy.md)。

## 架构原则

`loushang` 采用“内核 + 协议 + 适配器 + 扩展点”的分层架构。内核定义系统的运行语义，协议定义系统与外部世界的沟通边界，适配器连接不同环境与终端形态，扩展点则在不破坏内核一致性的前提下开放可编程能力。四者共同构成 `loushang` 的基础架构：内核保证一致性，协议保证可连接性，适配器保证可达性，扩展点保证可演化性。

`loushang` 以内核承载语义，以协议连接边界，以适配器触达环境，以扩展点驱动演化。

## Monorepo Subsystem Map

`loushang` 采用 monorepo 组织。当前阶段按统一根 Python project 组织各子系统源码，而不是先拆成多个独立 package。

建议子系统 map：

- `loushang-ai`
- `loushang-agent`
- `loushang-channel`
- `loushang-tui`
- `loushang-methods`
- `loushang-coding`

建议仓库结构：

```text
loushang/
  docs/
  src/
    loushang/
      ai/
      agent/
      channel/
      tui/
      methods/
      coding/
  tests/
```

## Subsystem Documentation

子系统划分与职责边界请参见 [Loushang Subsystems](./subsystem.md)。
子系统关系图请参见 [Loushang Subsystem Diagram](./subsystem-diagram.md)。
跨层架构判断准则请参见 [Loushang Architecture Principles](./loushang-architecture-principles.md)。
文档分层与阅读规则请参见 [Loushang Documentation Model](./loushang-documentation-model.md)。
`loushang-tui` 子系统文档请参见 [Loushang-TUI Architecture](./tui/README.md)。

## Architecture Stack

从下到上，`loushang` 的核心运行栈为：

1. `loushang-ai`
2. `loushang-agent`
3. `loushang-channel`
4. `loushang-tui`
5. `loushang-methods`
6. `loushang-coding`

其中：

- `agent` 定义运行语义
- `channel` 定义边界通信
- `tui` 提供通用终端 UI primitives
- `methods` 提供方法论运行骨架
- `coding` 提供产品化装配，并通过 `loushang.coding.ui` 连接 coding core 与 `loushang.tui`

## Agent and Channel Documentation

当前 agent / channel 相关文档包括：

- [Loushang-AI Architecture](./ai/README.md)
- [Loushang AI Glossary](../glossary/loushang-ai.md)
- [Loushang AI Types](../glossary/loushang-ai-types.md)
- [Loushang Agent](../glossary/loushang-agent.md)
- [Loushang Agent Types](../glossary/loushang-agent-types.md)
- [Loushang Channel Boundary Protocol](../loushang-channel-boundary-protocol.md)

## Next Steps

下一步建议继续完善：

1. `Client Capability Model`
2. `Notification Type Families`
3. `Method Layer Bridge`
4. `Loushang Methods Architecture`

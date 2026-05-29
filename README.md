# Loushang

`loushang` 是面向智能时代的操作系统，让个人、团队与组织能创新地发现机会，系统地驾驭复杂，快捷地释放价值。

## 愿景

驾驭复杂工作，成就卓越价值。

## 架构

`loushang` 采用“内核 + 协议 + 适配器 + 扩展点”的分层架构：

- **内核**：定义系统运行语义
- **协议**：定义系统与外部世界的沟通边界
- **适配器**：连接不同环境与终端形态
- **扩展点**：在不破坏一致性的前提下开放可编程能力

## Monorepo Packages

- `loushang-ai`
- `loushang-agent`
- `loushang-channel`
- `loushang-tui`
- `loushang-methods`
- `loushang-coding`

## 文档

- [Loushang Strategy](./docs/strategy/strategy.md)
- [Architecture Overview](./docs/architecture/architecture-overview.md)
- [Loushang Subsystems](./docs/architecture/subsystem.md)
- [Loushang Subsystem Diagram](./docs/architecture/subsystem-diagram.md)
- [Loushang AI Streaming and Cancellation](./docs/architecture/ai/loushang-ai-streaming-and-cancellation.md)
- [Loushang AI Streaming Validation](./docs/architecture/ai/validation/loushang-ai-streaming-validation.md)
- [Loushang AI Historical Handoff Summary](./docs/architecture/ai/history/loushang-ai-historical-handoff.md)
- [Loushang Method Notes](./docs/architecture/loushang-method-notes.md)
- [Loushang Agent Runtime](./docs/architecture/agent/README.md)
- [Loushang Agent](./docs/glossary/loushang-agent.md)
- [Loushang AI Types](./docs/glossary/loushang-ai-types.md)
- [Loushang Agent Types](./docs/glossary/loushang-agent-types.md)
- [Loushang Channel Boundary Protocol](./docs/loushang-channel-boundary-protocol.md)

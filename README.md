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

## 致谢

Loushang 的产品形态、交互设计与工程实现参考了以下开源项目的公开设计经验：

- [OpenAI Codex](https://github.com/openai/codex) — Agent TUI、会话中断与多轮输入设计
- [pi](https://github.com/earendil-works/pi) — Agent SDK 与会话状态管理
- [python-prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — 终端输入处理与全屏 TUI 模式
- [browser-use](https://github.com/browser-use/browser-use) — 浏览器自动化 Agent 架构
- [kimi-cli](https://github.com/MoonshotAI/kimi-cli) — CLI 流式输出与交互模式
- [superpowers](https://github.com/obra/superpowers) — Skill 库与工作流编排
- [gstack](https://github.com/garrytan/gstack) — Agent 协调与多智能体模式
- [openclaw](https://github.com/openclaw/openclaw) — Agent 运行时参考
- [hermes-agent](https://github.com/NousResearch/hermes-agent) — Agent 框架设计参考

上述项目为设计参考与灵感来源；除 `THIRD_PARTY_NOTICES.md` 中列出的依赖外，不表示本项目包含或再分发其代码。

## 许可证

本项目的代码与文档默认遵循 Apache License 2.0，除非文件中另有说明。

再分发本项目源码、二进制包、文档或其修改版本时，应保留 `LICENSE` 与 `NOTICE` 文件，并在产品文档、About/Credits 页面或其他第三方声明位置保留本项目归属信息。

第三方依赖信息见 `THIRD_PARTY_NOTICES.md`。

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

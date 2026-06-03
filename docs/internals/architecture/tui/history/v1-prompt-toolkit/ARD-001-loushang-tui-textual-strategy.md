# ARD-001: Loushang-TUI Textual Strategy

Status: Superseded by [ARD-002: Loushang-TUI Terminal Strategy](./ARD-002-loushang-tui-terminal-strategy.md).

This document records the earlier Textual-based direction. It remains useful as historical context, but it is no longer the P0 architecture for `loushang-tui`.

## Status

Superseded

## Context

`loushang` 当前已经接受以下核心子系统：

- `loushang-ai`
- `loushang-agent`
- `loushang-channel`
- `loushang-tui`
- `loushang-methods`
- `loushang-coding`

其中，`loushang-coding` 已明确保留 `interactive mode`，但实现后置。  
当前需要尽早钉住的是：

- `loushang-tui` 是否保持独立子系统
- `Textual` 是替代 `loushang-tui`，还是作为其内部实现
- 第一版是否直接做通用 TUI 平台，还是先服务 `coding`
- 如何参考成熟终端助手的 `InteractiveMode + TUI substrate` 职责分离，同时避免过早复制重型 UX 复杂度

结合当前讨论，`loushang` 对 `tui` 的目标不是：

- 把 `Textual` 直接提升为架构主语
- 让 `Widget` 或 `Screen` 直接拥有 `session/runtime` 语义
- 在 P0 就完成完整通用 UI 平台

而是：

- 保留 `loushang-tui` 作为独立子系统边界
- 以 `coding interactive` 为第一条落地 vertical slice
- 在实现层积极复用 `Textual`
- 为未来扩展到更通用的本地 rich client 保留空间

## Decision

### 1. `loushang-tui` 保持独立子系统定位

`loushang-tui` 不并入 `loushang-coding`，也不被 `Textual` 这个第三方框架替代。

它在 `loushang` 架构中的角色仍然是：

- 本地 terminal rich client 子系统
- 负责 screen / widget / dialog / input / status 等交互呈现
- 承接本地 UI 状态与交互原语

### 2. `Textual` 作为 `loushang-tui` 的内部实现底座

当前接受的方向是：

- `Textual` 是 `loushang-tui` 的首选实现底座
- `Textual` 不作为 `loushang` 子系统名词进入整体分层
- `Textual` 的 `App / Screen / Widget / MessagePump` 能力主要服务于 `loushang-tui` 的实现

换言之：

- 架构边界名称是 `loushang-tui`
- 具体技术实现可以是 Textual-based

### 3. 长期按“独立 TUI 子系统”设计，P0 按“coding vertical slice”落地

当前接受“长期按 3，短期按 2”的策略：

- 长期目标：`loushang-tui` 是可持续演化的独立 TUI 子系统
- P0 落地：第一版只实现 `coding` 所需的交互 slice

这意味着当前不追求：

- 一开始抽出完整的通用 widget platform
- 一开始实现完整 theme/router/action bus/framework

而是优先实现：

- transcript pane
- command/input editor
- assistant streaming projection
- tool progress / tool result 区域
- session or branch selection
- diagnostics / confirm / selector 一类最小 dialog
- status / footer 等基本交互构件

### 4. 参考成熟终端助手的职责边界，不追求逐字结构复刻

当前对齐的是成熟终端助手的职责判断：

- `InteractiveMode` 是 UI orchestration layer
- 本地 TUI 模块是 terminal UI substrate

在 `loushang` 中，对应关系为：

- `loushang-coding.mode.interactive` 负责 orchestration
- `loushang-tui` 负责 UI substrate

但不要求：

- 逐字 API 兼容
- 逐文件映射
- 一次性复制成熟终端助手的交互复杂度

### 5. `coding` 与 `tui` 的边界按“流程编排 / UI 呈现”切分

当前接受的边界为：

- `coding` 负责 `AgentSessionRuntime` / `AgentSession` 的流程编排
- `coding` 订阅 `AgentSessionEvent`
- `coding` 决定 prompt / steer / follow-up / abort / session switching 等 runtime 动作
- `tui` 负责将可渲染状态映射为 widgets / dialogs / layout / keybindings
- `tui` 负责把用户交互结果回传给 `coding`

因此不应让：

- `Widget` 直接操作底层 `Agent`
- `Textual` UI 树直接拥有 session 主语义
- tool execution 与 tool presentation 在组件边界上混成一个对象

### 6. `loushang-tui` 的对外边界先保持薄层

P0 阶段，`loushang-tui` 对外不追求抽出大而全稳定 API。

当前更合理的边界是：

- 对 `coding` 暴露 coding-oriented UI contracts
- 在 `loushang-tui` 内部允许大量直接使用 Textual 心智和类型
- 只在 mode / subsystem 边界做必要隔离

这是一种：

- 外部边界独立
- 内部实现务实

的策略。

## Rationale

本次决定采用“保留子系统边界，但不提前平台化”的策略，理由是：

1. 当前整体架构已经接受 `loushang-tui` 作为独立子系统，直接取消会破坏现有分层判断。
2. `Textual` 很适合实现 terminal rich client，但它是实现技术，不是 `loushang` 的产品边界本身。
3. 参考成熟终端助手，真正值得借鉴的是 `InteractiveMode + TUI substrate` 的职责分离，而不是重型 UI 的完整复制。
4. 如果 P0 直接做完整通用 TUI 平台，成本高且容易偏离 `coding interactive` 的首要目标。
5. 如果 P0 反过来让 `InteractiveMode` 直接耦合 Textual，则后续会削弱 `tui` 子系统的独立价值，也更容易形成 UI god object。

## Consequences

### Positive

- `loushang-tui` 的架构位置被明确保留
- `Textual` 的实现收益可以直接利用
- `coding interactive` 能以较小范围尽快落地
- 后续可在不推翻 P0 的前提下，把 coding-specific UI 能力逐步上提为通用 TUI 能力
- 更容易保持 `InteractiveMode` 与 UI primitives 的责任分离

### Negative

- P0 阶段 `loushang-tui` 内部会保留一定 coding-specific 痕迹
- 前期不会得到一套完整稳定的通用 TUI API
- 后续如果扩展到非 coding 场景，仍需要进一步抽象通用 contracts

## Impacted Documents

- `docs/architecture/subsystem.md`
- `docs/architecture/architecture-overview.md`
- `docs/architecture/coding/ARD-001-coding-product-boundaries.md`
- `docs/architecture/coding/loushang-coding-system-context.md`
- `docs/architecture/coding/loushang-coding-key-mode-sequences.md`

## Follow-up

- 补齐 `loushang-tui` 的 system context 文档
- 建立 `src/loushang/tui/` 最小源码目录
- 后续补 `loushang-tui` 的候选组件与 P0 组件切分
- 后续在 `interactive mode` 进入实现前，再细化 `coding <-> tui` 的 UI state / action contracts

# ARD-001: Loushang Coding Product Boundaries

## Status

Accepted

## Context

`loushang-coding` 当前处于设计阶段，目标是：

- 参考 `reference coding agent`
- 使用 Python 实现
- 先设计完整组件边界，再分阶段实现
- 当前不优先实现 `interactive mode`

同时，`loushang` 总体架构中已经存在这些相邻子系统概念：

- `loushang-ai`
- `loushang-agent`
- `loushang-channel`
- `loushang-tui`
- `loushang-methods`
- `loushang-coding`

在讨论中出现了几个需要尽早钉住的边界问题：

- `loushang-coding` 的候选组件列表是什么
- `context` 是否当前就单列
- `channel` 是否应并入 `coding`
- `coding` 前期是否必须依赖 `channel`
- `print/json/rpc/interactive` 如何归类
- `tui` 与 `coding` 的边界如何处理
- `coding` 是否只通过 `agent` 间接依赖 `ai`

## Decision

### 1. `loushang-coding` 的候选组件列表

当前接受以下候选组件列表：

- `bootstrap`
- `sdk`
- `cli`
- `mode`
- `runtime`
- `session`
- `store`
- `message`
- `event`
- `tools`
- `exec`
- `prompt`
- `skill`
- `loader`
- `extensions`
- `control`
- `policy`
- `compaction`
- `method`
- `diagnostics`
- `utils`

### 2. 当前不单列 `context`

当前阶段不把 `context` 作为 `loushang-coding` 的独立顶层组件。

相关职责先由以下边界协同承接：

- `session`
- `prompt`
- `loader`
- `compaction`

后续如果 session 内部的上下文选择、投影、working set 组装明显膨胀，再考虑单独拆出 `context`。

### 3. `mode` 是 `loushang-coding` 的核心组件

当前接受以下 mode 列表：

- `print`
- `json`
- `rpc`
- `interactive`（未来实现）

其中：

- `print` / `json` / `rpc` 属于当前阶段需要纳入设计范围的运行形态
- `interactive` 保留为明确 mode，但实现后置
- 在架构对象层，`json` 当前应视为 `PrintMode` 的结构化输出 projection，而不是独立 `JsonMode`

### 4. `sdk` 保留为对外入口层

`sdk` 不只是内部辅助文件，而是 `loushang-coding` 的对外嵌入入口层。

其职责是：

- 暴露可嵌入的 coding runtime 创建入口
- 复用 `bootstrap` 的默认装配能力

### 5. `loushang-channel` 不并入 `loushang-coding`

`loushang-channel` 不作为 `loushang-coding` 的内部组件。

原因：

- `channel` 的职责是边界协议与 transport 语义
- `coding` 的职责是 coding 产品装配
- `channel` 是跨产品的稳定协议层，不应被 coding-specific 语义吞并

因此：

- `loushang-channel` 仍保持独立子系统定位
- `loushang-coding` 未来可依赖 `channel`
- 但 `channel` 不进入 `coding` 的候选组件列表

### 6. `loushang-coding` 直接依赖 `loushang-ai`

`loushang-coding` 不只是通过 `loushang-agent` 间接依赖 `loushang-ai`，还保留对 `ai` 的直接依赖。

主要原因是，参考 `reference coding agent`，coding 产品层会直接消费一部分 AI 能力，例如：

- model registry / model selection
- direct summarization / compaction requests
- 某些 helper-style AI 调用

因此，当前接受的关系是：

- `loushang-coding -> loushang-agent`
- `loushang-coding -> loushang-ai`
- `loushang-agent -> loushang-ai`

### 7. `loushang-coding` 前期不依赖 `channel`

前期实现 `loushang-coding` 时，不要求先实现 `loushang-channel`。

这意味着：

- 没有 `channel` 也不影响 `coding` 起步
- `print mode`、`json mode`、`rpc mode` 可以先直接基于 `session/runtime/event` 工作
- 后续如果边界协议、审计、回放、跨客户端一致性需求成熟，再引入 `channel`

### 8. `print mode` 是输出适配层，不是 `channel`

`print mode` 的职责是把运行事件投影到 stdout/stderr 或结构化输出。

它属于：

- `coding` 的 mode adapter

它不属于：

- `channel` 协议层

### 9. `loushang-tui` 与 `coding` 保持分层

`loushang-tui` 代表独立的终端交互子系统，不并入 `loushang-coding`。

边界建议为：

- `coding` 负责 interactive mode 的流程编排
- `tui` 负责终端 UI primitives、widgets、layout 与交互呈现

未来若基于 Textual 实现 `loushang-tui`，这是可接受方向。

但约束是：

- 对齐 `reference TUI` 的职责边界
- 不要求逐字 API 兼容
- 更强调语义兼容与 Python 化实现

## Rationale

本次决定采用“先稳住产品骨架，再后置跨边界协议层”的策略，理由是：

1. 当前 `loushang-coding` 的优先目标是镜像 `reference coding agent` 的产品装配主干。
2. `channel` 是长期有价值的边界层，但不是 `coding` 起步的前置条件。
3. 过早把 `channel` 并入 `coding`，会污染分层并让 `coding` 过厚。
4. 参考 `reference coding agent`，`coding` 产品层不仅装配 `agent`，也会直接依赖部分 `ai` 能力，因此系统环境图必须显式保留 `coding -> ai`。
5. 过早单列 `context`，会增加边界数量，但当前其职责仍可被 `session/prompt/loader/compaction` 稳定承接。
6. 明确保留 `sdk`、`mode`、`interactive`，有利于后续从 CLI 扩展到嵌入式、RPC 与 TUI。

## Consequences

### Positive

- `loushang-coding` 可以先独立推进，不被 `channel` 阻塞
- 组件列表更贴近 `reference coding agent`
- `mode`、`sdk`、`runtime`、`session` 的主干更清楚
- `coding -> ai` 的直接依赖被显式保留，后续 model registry / summarization 等设计更容易落位
- `channel` 与 `tui` 的长期独立价值被保留

### Negative

- 早期不同 mode 可能会暂时重复做一部分边界投影逻辑
- 后续引入 `channel` 时，可能需要把 `rpc/web/interactive` 的部分适配逻辑上提
- `context` 暂不单列，意味着 `session` 设计时需要更克制地控制体积

## Impacted Documents

- `docs/architecture/coding/loushang-coding-candidate-components.md`
- `docs/architecture/coding/loushang-coding-system-context.md`
- `docs/architecture/subsystem.md`
- `docs/architecture/agent/loushang-agent-system-context.md`
- `docs/loushang-channel-boundary-protocol.md`

## Follow-up

- 后续补一份 `loushang-coding` 分阶段实现建议
- 后续在 `interactive` 设计阶段，再决定 `loushang-tui` 的 Textual 方案细节
- 后续在 `rpc/web` 需求稳定后，再决定 `loushang-channel` 的落地时机

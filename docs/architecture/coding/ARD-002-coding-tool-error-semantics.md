# ARD-002: Loushang Coding Tool Error Semantics

## Status

Superseded for runtime tool diagnostics by strict `pi` alignment on 2026-05-01.

Runtime tool failure now uses the `pi` main path only: tool throws, agent loop emits `ToolResultMessage.is_error=True`, and the result is sent back to the model. `AgentSession` no longer projects generic tool execution failure into diagnostics, and built-in tools no longer write ordinary runtime tool failures to diagnostics.

## Context

`loushang-coding` 当前已经有一条与 `pi-agent` 基本同构的工具执行主链：

- tool 成功时返回 `AgentToolResult`
- tool 失败时由 `agent_loop` 统一转换为 `ToolResultMessage.is_error=True`
- `coding` 层再消费 session / retry / compaction / diagnostics

当前问题不在于主链方向错误，而在于错误语义还没有稳定收敛：

- `AgentToolResult` 只承载 `content` 与 `details`，没有统一错误信封
- `agent_loop` 在错误分支里目前主要保留字符串消息，结构化错误信息会丢失
- 部分 built-in tool 直接记录 diagnostics，主错误记录没有统一接缝
- `after_tool_call` 当前可以改写 `is_error`，存在把错误洗成成功的风险
- provider / model / tool / policy / exec / extension 的错误，目前没有一套跨层统一的结构化表示

目标是：

- 对齐 `pi` 的 agent 层语义，不把状态位塞回每个 tool 的返回对象
- 让新工具在 Python 中保持自然写法
- 不吞错误，不假装成功
- 让 provider / model / UI / diagnostics 看见同一套错误事实

## Decision

### 1. 工具失败继续使用异常表达，不把错误状态塞进 `AgentToolResult`

`loushang.agent` 继续保持 `pi` 路线：

- 成功：tool 返回 `AgentToolResult`
- 失败：tool 抛异常
- `agent_loop` 是唯一把失败投影为 `ToolResultMessage.is_error=True` 的边界层

不把 `status`、`is_error`、`ok/error` 之类状态字段提升进 `AgentToolResult`。

### 2. 引入统一的结构化错误信封 `ErrorInfo`

新增 agent 级错误对象 `ErrorInfo`，用于在异常、tool result、diagnostics 之间传递同一份错误语义。

建议字段：

- `code`
- `source`
- `message`
- `display_message`
- `retryable`
- `details`

其中 `source` 至少覆盖：

- `tool`
- `policy`
- `exec`
- `provider`
- `model`
- `extension`
- `session`
- `agent`

新增 `LoushangError` 作为基础异常，并允许派生少量 typed exception，例如：

- `ToolValidationError`
- `ToolPermissionError`
- `ToolExecutionError`
- `ToolBlockedError`

### 3. `agent_loop` 统一把异常归一成带 `ErrorInfo` 的错误结果

`agent_loop` 在 tool 执行 catch 分支中：

- 先把异常归一为 `ErrorInfo`
- 再构造错误 `AgentToolResult`
- `content` 使用给模型可见的文本消息
- `details` 放入结构化错误，例如 `{"error": ...}`
- 最终由 `ToolResultMessage.is_error=True` 对外表达失败事实

这样：

- model 能继续看到文本错误
- UI / runtime / diagnostics 可以读取结构化错误信息
- 不再只有字符串错误

### 4. hook 可以加重错误，不能把错误洗成成功

`after_tool_call` 允许：

- 补充错误信息
- 把原本成功的结果升级成错误

`after_tool_call` 不允许：

- 把已经是错误的结果改回成功

因此，hook 的错误改写语义必须满足单调性：

- `false -> true` 允许
- `true -> false` 不允许

如后续需要更清晰的接口，可逐步把 `AfterToolCallResult.is_error` 迁移为 `error: ErrorInfo | None`。

### 5. diagnostics 从事件和结果投影，不由工具直接承担主错误记录

Superseded note: generic runtime tool failure is no longer projected into diagnostics. Provider/model/extension/resource/startup diagnostics remain in scope; ordinary tool execution failure is represented by `ToolResultMessage.is_error=True`.

`DiagnosticsService` 继续作为归一化与查询组件，但主错误记录不由 tool 自己直接写入。

主接缝放在 `coding.session.AgentSession`：

- `tool_execution_end` 且 `is_error=True` 时，从 tool result 的结构化错误投影 `DiagnosticRecord`
- `agent_end` 且 assistant turn 为 provider / model 错误时，投影对应 `DiagnosticRecord`
- extension / loader / startup 诊断继续沿用现有资源诊断归一路径

工具自身可以记录补充 warning，但不承担主失败事实的唯一来源。

### 6. `DiagnosticSource` 扩展为覆盖 provider / model / agent

为了避免把 provider / model 失败都硬塞到 `session` 或 `tool`，`DiagnosticSource` 扩展为至少包含：

- `provider`
- `model`
- `agent`

## Rationale

### 1. 这是最符合 Python 书写习惯的工具契约

Python 工具作者最自然的写法仍然是：

- 成功返回结果
- 失败抛异常

如果把错误状态提升进每个 tool 的返回对象，会让每个 tool 都承担额外状态协议，增加作者心智负担。

### 2. 保持 `agent` 与 `coding` 的分层清晰

`agent` 的职责是：

- 统一执行 tool
- 统一生成 `is_error`
- 向上游暴露稳定事件

`coding` 的职责是：

- 把这些事件投影到 session / retry / compaction / diagnostics / UI

如果让 tool 或 diagnostics 先决定主错误事实，会破坏这条分层。

### 3. 结构化错误比字符串错误更适合跨层消费

provider / model / UI / diagnostics 对错误的关心点不同：

- model 需要一段可理解的文本
- UI 需要错误类型、来源和展示文案
- diagnostics 需要 code / source / details
- retry / policy 需要 `retryable` 等机器可判断语义

统一的 `ErrorInfo` 可以让这些消费面共享同一事实源。

### 4. hook 单调性可以防止“假成功”

如果 `after_tool_call` 可以自由把错误改回成功，那么：

- UI 可能看见成功
- session 中却留下失败语义
- diagnostics 可能已经记过错误

这会导致不同层看到不同真相。

单调性约束可以避免这种分裂。

## Consequences

### Positive

- 新工具更容易写：成功返回，失败抛 typed exception
- 错误不会只剩字符串
- `tool_result`、UI、diagnostics、retry 能共享同一套结构化错误
- 继续对齐 `pi` 的 agent 边界，不把 `sdk-python` 风格的状态位上移到 core

### Negative

- 需要在 `agent` 层新增错误归一逻辑和 typed exception
- 需要调整现有 built-in tool，避免直接返回伪成功错误结果
- 需要给 diagnostics 增加基于 event 的投影逻辑

## Impacted Documents

- `docs/architecture/coding/component-interfaces/tools.md`
- `docs/architecture/coding/component-interfaces/diagnostics.md`
- `docs/architecture/coding/core-data-objects/tool-exec-policy.md`
- `docs/architecture/coding/core-data-objects/diagnostics.md`

## Follow-up

- 在 `loushang.agent` 引入 `ErrorInfo` 与基础 typed exception
- 调整 `agent_loop` 的 tool error normalization，保留结构化错误
- 收紧 `after_tool_call` 的错误改写语义，禁止把错误降级为成功
- 在 `AgentSession` 中增加 tool/provider/model 错误到 diagnostics 的统一投影
- 逐步把 built-in tools 迁移到 typed exception 路线

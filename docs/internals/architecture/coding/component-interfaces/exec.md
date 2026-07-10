# `exec`

## Role

- coding 产品对中立 workspace execution substrate 的适配与公共兼容入口

## Owns

- `loushang.coding.exec` 与顶层 `loushang.coding` 的 compatibility exports
- session cwd 与相对 cwd 的产品解析
- extension runtime binding 的参数适配
- coding policy、bash tool 和用户可见结果的集成

中立 owner 位于 `loushang.harness.workspace.exec`：

- `ExecService`
- `ExecBackend`
- `ExecRequest`
- `ExecResult`
- `ExecOutputChunk`
- `ExecUpdateCallback`
- shell / subprocess、streaming、rolling capture、preview 与 artifact 机制

## Depends On

- OS subprocess / shell runtime
- `loushang.harness.workspace.exec`
- caller-provided execution policy or guardrail result（可选）

## Commands

- `execute(request: ExecRequest) -> Awaitable[ExecResult]`
- harness `ExecService(backend=...)` 可注入自定义执行后端
- `execute(..., signal=..., on_update=...)` 支持 abort signal 和 stdout/stderr incremental update callback

## Queries

- 当前无稳定 query surface

## Events

- 当前无稳定事件面

## Key Data

- `ExecBackend`
- `ExecRequest`
- `ExecResult`
- `ExecOutputChunk`
- `ExecUpdateCallback`

这些对象由 harness 定义；coding compatibility 路径 re-export 相同对象，
不保留第二套实现。

## Out Of Scope

- 工具注册
- tool schema 定义
- session 生命周期
- prompt 组装

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 中 bash executor 与 built-in tool execution capability
- 不复刻 `reference CLI` 把执行能力主要压在 tool layer 内部的结构
- `ExecService` 是 `loushang.harness.workspace.exec` 为 Python subprocess
  边界显式保留的一层
- `ExecBackend` 承接 `reference CLI` bash operations custom backend 语义，用于 remote executor、sandbox executor 或测试替身
- 无 backend 时保持默认本地 subprocess 行为
- `extensions` 通过 `ctx.exec_command(...)` / `api.exec_command(...)` 复用同一 `ExecService`，避免 extension
  侧另起一套 subprocess / shell 语义

# `exec`

## Role

- 命令执行子系统

## Owns

- `ExecService`
- `ExecBackend`
- `ExecRequest`
- `ExecResult`
- shell / subprocess 执行边界

## Depends On

- OS subprocess / shell runtime
- caller-provided execution policy or guardrail result（可选）

## Commands

- `execute(request: ExecRequest) -> Awaitable[ExecResult]`
- `ExecService(backend=...)` 可注入自定义执行后端
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

## Out Of Scope

- 工具注册
- tool schema 定义
- session 生命周期
- prompt 组装

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 中 bash executor 与 built-in tool execution capability
- 不复刻 `reference CLI` 把执行能力主要压在 tool layer 内部的结构
- `ExecService` 是 `loushang` 为 Python subprocess 边界显式保留的一层
- `ExecBackend` 承接 `reference CLI` bash operations custom backend 语义，用于 remote executor、sandbox executor 或测试替身
- 无 backend 时保持默认本地 subprocess 行为
- `extensions` 通过 `ctx.exec_command(...)` / `api.exec_command(...)` 复用同一 `ExecService`，避免 extension
  侧另起一套 subprocess / shell 语义

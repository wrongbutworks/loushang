# `domain-work`

## Scope

- coding domain bridge 与 work projection 中跨组件交换的对象
- `loushang.method` / `loushang.work` 对 coding 可见的边界投影

## Objects

### `CodingDomainRequest`

归属组件：

- `domain`

角色：

- 一次 coding turn 准备请求

承担语义：

- 用户 prompt
- explicit/default method policy
- 当前 cwd/session 相关输入

### `CodingDomainPreparedTurn`

归属组件：

- `domain`

角色：

- domain bridge 输出给 CLI/session 的可执行 turn

承担语义：

- prepared prompt
- method metadata
- plan/step metadata
- work-log correlation metadata

### `MethodPolicy`

归属组件：

- `domain`

角色：

- coding 侧 method 应用策略

承担语义：

- explicit method
- default method
- no-method override

### `WorkEvent`

归属组件：

- `loushang.work`

角色：

- method-driven coding run 的 work lifecycle 事件

承担语义：

- plan start/completion/failure
- step start/completion/failure
- run/step correlation
- replay and inspection surface

## Reference Implementation Alignment

- `CodingDomainApp` 是 `loushang` 自有 domain bridge，不直接对齐 reference coding agent 的一等对象。
- `WorkEvent` 属于 `loushang.work`，coding 只负责在 method-driven non-interactive run 中发出和投影。

## Notes

- `MethodDescriptor` / `MethodPlan` / `MethodStep` 归属 `loushang.method`。
- `WorkPlanRun` / `WorkStepRun` 归属 `loushang.work`。
- `--method` 当前只支持非交互 prompt/print/json 路径；TUI/RPC 的 method integration 由 ARD-006 约束。

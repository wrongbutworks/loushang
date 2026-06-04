# `diagnostics`

## Role

- coding 启动检查、资源加载诊断与非工具执行类错误归一化组件

## Owns

- `DiagnosticsService`
- `DiagnosticsQuery`
- 启动前环境检查
- provider / model / extension 等非工具执行类运行期错误归一化
- package/plugin source policy rejection normalization
- 最近一次诊断结果快照
- 诊断聚合摘要与 source/phase/code 计数

## Depends On

- `session`
- `store`
- `control`

## Commands

- `run_startup_checks(...)`
- `normalize_error(...)`
- `capture_failure(...)`
- `normalize_startup_check_result(...)`

## Queries

- `get_last_diagnostics()`
- `get_diagnostics(query=...)`
- `get_last_error_report()`
- `get_diagnostics_summary(query=...)`
- `serialize_diagnostic(...)`
- `serialize_error_report(...)`
- `serialize_diagnostic_summary(...)`

## Semantics

- `record(...)` 会为诊断生成稳定 fingerprint。
- 同一 session 内相同 fingerprint 的诊断会合并为一条，并累加 occurrence count。
- `ErrorReport.related` 返回去重后的相关诊断，避免 retry/provider error 重复刷屏。
- runtime tool failure 的主通道仍是 `ToolResultMessage(is_error=True)`；同时会记录带 `toolCallId` / `toolName` correlation 的 `tool_execution_failed` diagnostics，供 headless clients 查询。
- CLI `--list-diagnostics` 通过 `get_last_diagnostics(limit=...)` 暴露最近诊断，可输出 TSV 或 JSON。
- RPC `get_diagnostics` 暴露最近诊断，并支持按 `sessionId`、`entryId`、`phase`、`source`、`level` / `diagnosticType`、`code`、`limit` 查询。
- RPC `get_diagnostics_summary` / `get_session_diagnostics_summary` 暴露同一 query surface 的聚合摘要：total/error/warning/info counts、byCode、bySource、byPhase、latestError。
- RPC `get_last_error_report` 暴露 primary/related 错误报告。
- package/plugin source policy rejection records use `code=package_source_policy_denied`, `source=policy`, and details containing `plugin_source`, `policy`, and `disposition`.
- 对外序列化字段使用 camelCase：`sessionId`、`entryId`、`sourcePath`、`occurrenceCount`。

## Events

- 当前无稳定事件面

## Key Data

- `DiagnosticRecord`
- `DiagnosticsQuery`
- `DiagnosticSummary`
- `ErrorReport`
- `StartupCheckResult`

## Out Of Scope

- session 事件编排
- runtime tool execution failure 的主错误面
- CLI 呈现样式
- UI 级恢复建议与分组策略
- 重试或恢复策略本体

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 的 diagnostics / startup checks / error normalization 需求
- 保持诊断能力独立于 `session` 与 `mode`
- `bootstrap` / `cli` / `mode` 可以调用 diagnostics，但不应让 diagnostics 反向依赖这些入口表面

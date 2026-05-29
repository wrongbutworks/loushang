# `event`

## Role

- session 运行时动态事件组件

## Owns

- `AgentSessionEvent`
- agent passthrough 与 session-level lifecycle 事件类型
- session event serialization
- JSON event projection / filtering helpers

## Depends On

- `message`
- `loushang-agent`

## Commands

- `serialize_session_event(...)`
- `project_session_event(...)`
- `select_events(...)`
- `normalize_event_select(...)`
- `should_emit_projected_event(...)`

## Queries

- 当前无稳定 query surface

## Events

- `AgentEvent` passthrough family
- `queue_update`
- `compaction_start`: carries `reason` and optional `usage` snapshot
- `compaction_end`: carries `reason`, `result`, `aborted`, `will_retry`, optional `error_message`,
  plus optional `usage_before` / `usage_after` snapshots
- `auto_retry_start`
- `auto_retry_end`

## Key Data

- `AgentSessionEvent`
- `CompactionReason`

## Out Of Scope

- 事件生产者本体
- transcript 持久化
- mode-specific I/O

## Pi Alignment

- 语义上对齐 `pi` 的 agent passthrough + session-level lifecycle event stream
- 明确保留 `event` 作为独立组件，而不是把事件类型散落在 session/mode 内

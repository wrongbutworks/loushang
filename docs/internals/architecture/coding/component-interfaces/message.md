# `message`

## Role

- session entry family 与 coding-specific runtime message projection 组件

## Owns

- `SessionEntry` family
- custom message family
- `convert_to_llm(...)`
- message JSON codec

## Depends On

- `loushang-agent`
- `loushang-ai`

## Commands

- `convert_to_llm(...)`
- `create_custom_message(...)`
- `create_branch_summary_message(...)`
- `create_compaction_summary_message(...)`

## Queries

- 当前无稳定 query surface

## Events

- 无

## Key Data

- `SessionHeader`
- `SessionEntry`
- `CustomMessage`
- `BranchSummaryMessage`
- `CompactionSummaryMessage`

## Out Of Scope

- transcript 持久化
- `SessionContext` 重建
- session lifecycle
- event transport

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 的 `session-manager` entry family 与 custom message family
- 保留 `message` 作为独立边界，承接“持久化 entry”与“runtime projection”之间的转换
- `SessionContext` 的重建职责仍应保持在 `store/session` 一侧

# `store`

## Role

- append-only 的 session persistence 与 context rebuild 组件

## Owns

- session header 与 JSONL entry 持久化
- leaf / branch / tree 视图
- label 索引
- 从 entry 图重建 `SessionContext`

## Depends On

- `message`
- `pathlib`
- JSONL codec

## Commands

- `new(...)`
- `load(...)`
- `branch(...)`
- `branch_with_summary(...)`
- `reset_leaf()`
- `append_message(...)`
- `append_model_change(...)`
- `append_thinking_level_change(...)`
- `append_compaction(...)`
- `append_custom_entry(...)`
- `append_custom_message_entry(...)`
- `append_label(...)`
- `append_session_info(...)`
- `fork(...)`
- `create_branched_session(...)`

## Queries

- `get_header()`
- `get_entries()`
- `get_entry(...)`
- `get_leaf_id()`
- `get_leaf_entry()`
- `get_branch(...)`
- `get_children(...)`
- `get_tree()`
- `get_label(...)`
- `get_session_record()`
- `get_session_summary()`
- `load_metadata()`
- `build_session_context()`
- `list(...)`
- `list_summaries(...)`
- `list_all_summaries(...)`
- `load_summary(...)`
- `find_sessions(...)`
- `find_all_sessions(...)`
- `index_file(...)`
- `refresh_index(...)`
- `load_index(...)`
- `list_indexed_summaries(...)`
- `find_indexed_sessions(...)`
- `refresh_all_indexes(...)`
- `list_all_indexed_summaries(...)`
- `find_all_indexed_sessions(...)`

## Events

- 无

## Key Data

- `SessionHeader`
- `SessionEntry`
- `SessionContext`
- `SessionRecord`
- `SessionSummary`
- `SessionQuery`
- `SessionMetadata`
- `SessionTreeNode`

## Session Index Fields

- `SessionSummary.has_diagnostics`
- `SessionSummary.diagnostic_count`
- `SessionSummary.first_message`
- `SessionSummary.all_messages_text`
- `SessionSummary.last_diagnostic_code`
- `SessionSummary.last_diagnostic_level`
- `SessionQuery.has_diagnostics`

These fields are lightweight index metadata derived from session entries. Store recognizes diagnostic metadata entries as `CustomEntry(custom_type="diagnostic" | "diagnostics")`; it does not own full diagnostics persistence or error-report generation.

`updated_at` follows pi-style session list semantics: prefer the latest user/assistant message activity timestamp, fall back to message entry timestamp, then session header timestamp. Metadata-only entries such as labels, session info, and diagnostic custom entries do not make an old conversation sort as recently active.

`refresh_index(session_dir)` writes a lightweight `.session-index.json` cache for `SessionSummary` projections. `list_indexed_summaries(...)` and `find_indexed_sessions(...)` use that cache when available and rebuild it if missing, invalid, or pointing at session files that have disappeared outside `SessionManager`. The default `list_summaries(...)` / `find_sessions(...)` paths intentionally continue to scan JSONL directly, so cache behavior is opt-in rather than hidden.

`rename_session(...)` and `delete_session(...)` refresh an existing index as an auxiliary cache update. If that cache refresh fails, the primary store operation still succeeds; callers can rebuild the index on the next indexed query or through runtime auto-refresh.

## Out Of Scope

- run-loop 决策
- model/auth 解析
- compaction trigger 判断
- prompt 组装

## Pi Alignment

- 语义上对齐 `pi` 的 `SessionManager`
- 保持 append-only transcript tree
- 支持 branch summary / compaction summary 的持久化与投影
- 保持 `custom` 与 `custom_message` 的分层语义，以及由 entry 图重建 `SessionContext` 的职责
- `list_all_summaries(root)` / `find_all_sessions(root, query)` 提供 pi-style all-session lookup 基础面，负责聚合 sessions root 下的直接 JSONL 与一层 project/session 子目录
- `first_message` / `all_messages_text` 对齐 pi 的 `SessionInfo.firstMessage` / `allMessagesText`，用于 session list 展示和全文搜索
- session summary 提供轻量 diagnostics index 字段，便于跨 session lookup/filter；完整 diagnostics 记录、去重和 error report 仍属于 `diagnostics`
- 显式 `.session-index.json` cache 补齐 pi-style session index 查询面；默认扫描路径不隐式依赖 cache，避免 stale index 影响核心 runtime

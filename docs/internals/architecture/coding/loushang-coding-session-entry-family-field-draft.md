# Loushang Coding Session Entry Family Field Draft

## Scope

本文档给出 `loushang-coding` 的 `SessionEntry family` 字段草案。

目标是：

- 尽量对齐 `reference coding agent/session-manager.ts`
- 在 Python 实现前先稳定核心持久化字段
- 明确哪些字段应直接进入 JSONL schema
- 明确哪些字段只作为 Python 内部视图存在

本文档不展开：

- 具体 Python 类实现
- `AgentSessionEvent` 字段
- mode-specific 字段
- 未来 `channel` 投影

## Design Basis

本轮字段草案主要对齐：

- [reference implementation session-manager.ts](/home/dev/workspace/reference-repository/packages/coding-agent/src/core/session-manager.ts:27)
- [reference implementation messages.ts](/home/dev/workspace/reference-repository/packages/coding-agent/src/core/messages.ts:1)

## Field Design Rule

建议先接受这三条规则：

1. 对象名优先对齐 `reference CLI`
2. JSONL 持久化字段语义优先对齐 `reference CLI`
3. Python 内部字段命名可用 `snake_case`，但应保留 JSON alias

也就是说，推荐采用：

- Python 内部：
  - `parent_id`
  - `model_id`
  - `first_kept_entry_id`

- JSONL 落盘：
  - `parentId`
  - `modelId`
  - `firstKeptEntryId`

## 1. Session Header

### `SessionHeader`

用途：

- session 文件第一条记录
- 提供 session root metadata

建议字段：

- `type: Literal["session"]`
- `version: int`
- `id: str`
- `timestamp: str`
- `cwd: str`
- `parentSession: str | None`

说明：

- `version` 应保留，即使第一版只有一个版本
- `timestamp` 建议保持 ISO-8601 字符串，与 `reference CLI` 一致
- `parentSession` 用于 fork/resume lineage，不建议删除

## 2. Base Entry

### `SessionEntryBase`

用途：

- 所有 `SessionEntry` 的公共基类

建议字段：

- `type: str`
- `id: str`
- `parentId: str | None`
- `timestamp: str`

说明：

- `id` / `parentId` 构成树结构
- `timestamp` 应按持久化写入时生成，不依赖消息本身时间戳

## 3. Message-Carrying Entries

### `SessionMessageEntry`

用途：

- 存一个标准 `AgentMessage`
- 是最常见的对话 entry

建议字段：

- `type: Literal["message"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `message: AgentMessage`

说明：

- `message` 保持来自 `loushang-agent`
- `BashExecutionMessage` 也可作为这里的 `message` 值
- `BranchSummaryMessage` 和 `CompactionSummaryMessage` 不建议直接写成 `SessionMessageEntry`

### `CustomMessageEntry`

用途：

- 扩展注入、且参与 LLM context 的 entry

建议字段：

- `type: Literal["custom_message"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `customType: str`
- `content: str | list[ContentBlock]`
- `details: object | None`
- `display: bool`

说明：

- 对齐 `reference CLI`
- `details` 不进入 LLM context
- `display` 控制 future TUI / interactive rendering

## 4. State-Change Entries

### `ThinkingLevelChangeEntry`

用途：

- 记录 thinking level 切换

建议字段：

- `type: Literal["thinking_level_change"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `thinkingLevel: str`

### `ModelChangeEntry`

用途：

- 记录 model/provider 切换

建议字段：

- `type: Literal["model_change"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `provider: str`
- `modelId: str`

说明：

- 即使 assistant message 里也可能带 model/provider，仍建议保留显式 `model_change` entry
- 这样 `build_session_context()` 恢复更稳定

## 5. Summary And Branch Entries

### `CompactionEntry`

用途：

- 记录一次 compaction 的摘要与边界

建议字段：

- `type: Literal["compaction"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `summary: str`
- `firstKeptEntryId: str`
- `tokensBefore: int`
- `details: object | None`
- `fromHook: bool | None`

说明：

- `summary` 是 durable summary，不是 runtime message
- runtime 侧由它投影出 `CompactionSummaryMessage`
- `firstKeptEntryId` 不建议改成 index

### `BranchSummaryEntry`

用途：

- 记录从 branch 返回后的摘要

建议字段：

- `type: Literal["branch_summary"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `fromId: str`
- `summary: str`
- `details: object | None`
- `fromHook: bool | None`

说明：

- runtime 侧由它投影出 `BranchSummaryMessage`

## 6. Extension And Metadata Entries

### `CustomEntry`

用途：

- 扩展持久化自己的内部状态
- 不进入 LLM context

建议字段：

- `type: Literal["custom"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `customType: str`
- `data: object | None`

说明：

- 这是 extension state persistence，不是 message

### `LabelEntry`

用途：

- 给某个 entry 打 label/bookmark

建议字段：

- `type: Literal["label"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `targetId: str`
- `label: str | None`

说明：

- `label = None` 表示清除 label

### `SessionInfoEntry`

用途：

- 存 session display metadata

建议字段：

- `type: Literal["session_info"]`
- `id: str`
- `parentId: str | None`
- `timestamp: str`
- `name: str | None`

说明：

- 当前先只保留 `name`
- 不建议第一版在这里堆更多非必要 metadata

## 7. Union Types

### `SessionEntry`

建议为以下联合：

- `SessionMessageEntry`
- `ThinkingLevelChangeEntry`
- `ModelChangeEntry`
- `CompactionEntry`
- `BranchSummaryEntry`
- `CustomEntry`
- `CustomMessageEntry`
- `LabelEntry`
- `SessionInfoEntry`

### `FileEntry`

建议为：

- `SessionHeader | SessionEntry`

## 8. Supporting Read Models

这些对象不一定直接落盘，但建议作为稳定读取视图保留。

### `SessionContext`

建议字段：

- `messages: list[AgentMessage]`
- `thinkingLevel: str`
- `model: { provider: str, modelId: str } | None`

说明：

- 直接对齐 `reference CLI`
- 这是 `build_session_context()` 的结果，不直接落盘

### `SessionTreeNode`

建议字段：

- `entry: SessionEntry`
- `children: list[SessionTreeNode]`
- `label: str | None`
- `labelTimestamp: str | None`

说明：

- 这是只读视图对象，不是持久化对象

## 9. Explicit Non-Goals

第一版不建议在 `SessionEntry family` 里加入：

- UI rendering hints
- mode-specific output formatting data
- channel envelope fields
- diagnostics-only payloads
- duplicated prompt cache fields

这些都不属于 `reference CLI` 的稳定 session entry 骨架。

## 10. Recommended Implementation Notes

如果进入 Python 实现，建议：

- 用判别联合表达 `SessionEntry`
- 持久化 codec 独立于业务逻辑
- `SessionManager` 只负责：
  - append
  - load
  - migrate
  - build context
- 不让 `AgentSession` 直接拼 JSONL schema

## 11. Immediate Next Step

基于这份字段草案，接下来最自然的是继续补：

1. `AgentSessionEvent` 字段草案
2. session JSONL schema 例子
3. `build_session_context()` 规则草案

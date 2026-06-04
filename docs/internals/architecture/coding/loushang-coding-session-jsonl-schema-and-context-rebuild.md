# Loushang Coding Session JSONL Schema And Context Rebuild

## Scope

本文档给出 `loushang-coding` 的 session JSONL 文件 schema 示例，以及 `build_session_context()` 的规则草案。

目标是：

- 把 `SessionEntry family` 真正落到文件组织上
- 尽量对齐 `reference coding agent` 的 `SessionManager`
- 明确 `store` 如何从 entry 重建当前运行上下文

本文档不展开：

- 具体 Python codec 实现
- 具体 mode 行为
- event 字段草案
- branch UI 展示

## Design Basis

本轮规则主要对齐：

- [reference implementation session-manager.ts](/home/dev/workspace/reference-repository/packages/coding-agent/src/core/session-manager.ts:27)
- [reference implementation messages.ts](/home/dev/workspace/reference-repository/packages/coding-agent/src/core/messages.ts:1)

## 1. File Model

建议直接对齐 `reference CLI` 的单文件 JSONL 模型：

- 一个 session 对应一个 `.jsonl` 文件
- 第一行必须是 `SessionHeader`
- 后续每一行都是一个 `SessionEntry`
- 文件整体是 append-oriented

抽象上：

```text
SessionFile = SessionHeader + SessionEntry*
```

## 2. File Naming

建议第一版保持和 `reference CLI` 接近：

- `YYYY-MM-DDTHH-MM-SS-sssZ_<session-id>.jsonl`

最小要求：

- 文件名里包含 timestamp
- 文件名里包含 session id
- 文件路径位于 session store root 下

说明：

- 最终文件名不必逐字复制 `reference CLI`
- 但应避免只用 session id，便于人工排查和时间排序

## 3. Header Schema

第一行：

```json
{
  "type": "session",
  "version": 1,
  "id": "b0b1f9d8",
  "timestamp": "2026-05-20T09:00:00.000Z",
  "cwd": "/home/dev/workspace/project",
  "parentSession": null
}
```

约束：

- `type` 必须是 `"session"`
- `version` 必须存在
- `id` 为 session id
- `timestamp` 为 session 创建时间
- `cwd` 为该 session 启动目录
- `parentSession` 为空或指向父 session

## 4. Entry Schema Examples

以下示例都表示单行 JSON object。

### 4.1 `SessionMessageEntry`

```json
{
  "type": "message",
  "id": "e1",
  "parentId": null,
  "timestamp": "2026-05-20T09:00:05.000Z",
  "message": {
    "role": "user",
    "content": [
      { "type": "text", "text": "Summarize this repo." }
    ],
    "timestamp": 1776243605000
  }
}
```

### 4.2 `ThinkingLevelChangeEntry`

```json
{
  "type": "thinking_level_change",
  "id": "e2",
  "parentId": "e1",
  "timestamp": "2026-05-20T09:00:06.000Z",
  "thinkingLevel": "medium"
}
```

### 4.3 `ModelChangeEntry`

```json
{
  "type": "model_change",
  "id": "e3",
  "parentId": "e2",
  "timestamp": "2026-05-20T09:00:07.000Z",
  "provider": "openai",
  "modelId": "gpt-5.4"
}
```

### 4.4 `CompactionEntry`

```json
{
  "type": "compaction",
  "id": "e4",
  "parentId": "e3",
  "timestamp": "2026-05-20T09:05:00.000Z",
  "summary": "The user asked for repository analysis and we inspected the CLI, session, and tool layers.",
  "firstKeptEntryId": "e2",
  "tokensBefore": 18342,
  "details": null,
  "fromHook": false
}
```

### 4.5 `BranchSummaryEntry`

```json
{
  "type": "branch_summary",
  "id": "e5",
  "parentId": "e4",
  "timestamp": "2026-05-20T09:10:00.000Z",
  "fromId": "branch-17",
  "summary": "A side investigation concluded that JSON output should remain a projection of PrintMode.",
  "details": null,
  "fromHook": false
}
```

### 4.6 `CustomEntry`

```json
{
  "type": "custom",
  "id": "e6",
  "parentId": "e5",
  "timestamp": "2026-05-20T09:11:00.000Z",
  "customType": "artifact_index",
  "data": {
    "version": 1,
    "artifacts": []
  }
}
```

### 4.7 `CustomMessageEntry`

```json
{
  "type": "custom_message",
  "id": "e7",
  "parentId": "e6",
  "timestamp": "2026-05-20T09:12:00.000Z",
  "customType": "review_note",
  "content": [
    { "type": "text", "text": "The migration plan is ready." }
  ],
  "details": {
    "severity": "info"
  },
  "display": true
}
```

### 4.8 `LabelEntry`

```json
{
  "type": "label",
  "id": "e8",
  "parentId": "e7",
  "timestamp": "2026-05-20T09:13:00.000Z",
  "targetId": "e4",
  "label": "before-compaction"
}
```

### 4.9 `SessionInfoEntry`

```json
{
  "type": "session_info",
  "id": "e9",
  "parentId": "e8",
  "timestamp": "2026-05-20T09:14:00.000Z",
  "name": "coding-architecture-review"
}
```

## 5. Persistence Rules

建议直接保留这些规则：

### 5.1 Append-Oriented

- 新 entry 默认 append 到当前 leaf 之后
- 新 entry 的 `parentId` 默认为当前 `leafId`
- 写入成功后，新的 `leafId = entry.id`

### 5.2 Header First

- 新 session 创建时，先写 `SessionHeader`
- header 缺失的文件视为损坏或空文件

### 5.3 Rewrite Only For Migration Or Repair

建议和 `reference CLI` 一样：

- 正常写入以 append 为主
- rewrite 仅用于：
  - migration
  - 空文件修复
  - 索引重建后重新落盘

### 5.4 Versioned Schema

- `version` 是 session file schema version
- migration 应以文件级处理，而不是让业务层兼容所有历史格式

## 6. `build_session_context()` Rule Draft

建议直接对齐 `reference CLI` 的核心思路。

输入：

- `entries: list[SessionEntry]`
- `leaf_id: str | None`
- 可选 `by_id: dict[str, SessionEntry]`

输出：

- `SessionContext`
  - `messages`
  - `thinkingLevel`
  - `model`

### 6.1 Step 1: Build Index

若未传入 `by_id`：

- 遍历所有 `SessionEntry`
- 建立 `id -> entry` 索引

### 6.2 Step 2: Resolve Leaf

规则：

- 若 `leaf_id is None` 且调用者明确表示“回到开头前”，返回空 context
- 若 `leaf_id` 指向某个 entry，则从它开始
- 若 `leaf_id` 未给定，则默认取最后一个 entry 作为 leaf
- 若无 entry，则返回空 context

### 6.3 Step 3: Walk From Leaf To Root

沿 `parentId` 逐步向上追溯，构造：

- `path: list[SessionEntry]`

要求：

- `path` 最终顺序应为 root -> leaf

### 6.4 Step 4: Recover Stateful Facts

沿 `path` 扫一遍，恢复：

- `thinkingLevel`
- `model`
- `latest compaction`

建议规则：

- `ThinkingLevelChangeEntry` 更新 `thinkingLevel`
- `ModelChangeEntry` 更新 `model`
- 若 `SessionMessageEntry.message.role == "assistant"` 且其中带 model/provider 信息，也可作为 model fallback
- `CompactionEntry` 记录当前生效 compaction 边界

### 6.5 Step 5: Project Entries Into Messages

无 compaction 时：

- 顺序遍历 `path`
- 对可进入上下文的 entry 做投影：
  - `SessionMessageEntry -> message`
  - `CustomMessageEntry -> CustomMessage`
  - `BranchSummaryEntry -> BranchSummaryMessage`

有 compaction 时：

1. 先投影 `CompactionEntry -> CompactionSummaryMessage`
2. 再从 `firstKeptEntryId` 开始投影 compaction 前保留的 entry
3. 再投影 compaction 之后的所有可见 entry

### 6.6 Step 6: Return `SessionContext`

返回：

- `messages`
- `thinkingLevel`
- `model`

## 7. Projection Visibility Rules

建议先固定这些规则：

### 7.1 Included In Session Context

- `SessionMessageEntry`
- `CustomMessageEntry`
- `BranchSummaryEntry`
- `CompactionEntry`（通过 summary message 形式）

### 7.2 Not Included In Session Context

- `ThinkingLevelChangeEntry`
- `ModelChangeEntry`
- `CustomEntry`
- `LabelEntry`
- `SessionInfoEntry`

说明：

- 这些 entry 会影响状态或元数据
- 但不直接成为 LLM 可见消息

## 8. Error Handling Rules

建议第一版就明确：

### 8.1 Invalid Header

- 无 header 或 header 非第一条：
  - 视为损坏文件
  - 交由 `SessionManager` repair / migration 逻辑处理

### 8.2 Missing Parent

- `parentId` 找不到时：
  - 该 entry 不应导致进程崩溃
  - 可记录 diagnostics
  - 但不应 silently fabricate context

### 8.3 Unknown Entry Type

- 应保留 migration / tolerant read 能力
- 但默认不应把未知 entry 纳入 context projection

## 9. Python Implementation Notes

建议实现时保持：

- JSON schema keys 贴近 `reference CLI`
- Python 模型字段可用 alias
- `build_session_context()` 作为纯函数或近纯函数实现
- `SessionManager` 只是状态持有与文件协调层

不建议：

- 在 `AgentSession` 内直接手写 context rebuild 逻辑
- 在 mode 层直接解析 JSONL

## 10. Cross-session Read Model

`SessionManager` 还应提供跨 session 的只读索引面，供 runtime、mode、RPC 与 CLI 复用。

当前稳定输出：

- `SessionRecord`
  - 轻量文件记录，保留 session id、cwd、session file、parent session、leaf id、metadata
- `SessionSummary`
  - 基于 `build_session_context()` 派生
  - 包含 session id、name、cwd、created/updated、entry/message count、last message preview、model、parent session
- `SessionQuery`
  - 用于跨 session 查询
  - 支持 cwd、name、parent session、text、limit

规则：

- mode / RPC / CLI 不应直接扫描 JSONL
- summary 中的 model 与 message count 以 active branch context 为准
- 损坏 session 文件在 list/query 中跳过，不中断整体查询
- `limit` 为非负整数，负数应返回稳定错误

## 11. Immediate Next Step

基于这份文档，接下来最自然的是：

1. `AgentSessionEvent` 字段草案
2. `message.entries` 的 Python 模型实现
3. `store.file_codec` 的 JSONL codec 实现

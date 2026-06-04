# `message-family`

## Scope

- coding-specific runtime message 对象与 entry-to-message 投影规则

## Objects

### `BashExecutionMessage`

归属组件：

- `message`
- `exec`

角色：

- bash / command execution 的 runtime message 对象

承担语义：

- command
- output
- exit code
- cancelled / truncated
- optional full output path
- optional exclude-from-context flag

### `CustomMessage`

归属组件：

- `message`
- `extensions`

角色：

- 扩展注入的 runtime custom message 对象

承担语义：

- custom type
- content
- display
- optional details

### `BranchSummaryMessage`

归属组件：

- `message`
- `compaction`

角色：

- branch summary 的 runtime message 对象

承担语义：

- summary
- from id

### `CompactionSummaryMessage`

归属组件：

- `message`
- `compaction`

角色：

- compaction summary 的 runtime message 对象

承担语义：

- summary
- tokens before

## Reference Implementation Alignment

- 这组对象整体直接对齐 `reference coding agent/messages.ts` 中的 coding-specific `AgentMessage` 扩展

## Notes

- 运行时消息对象不是 entry 主模型，而是投影层
- 当前建议保留以下投影关系：
  - `SessionMessageEntry.message -> AgentMessage`
  - `CustomMessageEntry -> CustomMessage`
  - `BranchSummaryEntry -> BranchSummaryMessage`
  - `CompactionEntry -> CompactionSummaryMessage`

# `entry-family`

## Scope

- session file 的 entry 家族对象

## Objects

### `SessionEntryBase`

归属组件：

- `store`
- `message`

角色：

- session entry 的公共基类对象

承担语义：

- `type`
- `id`
- `parent_id`
- `timestamp`

### `SessionMessageEntry`

归属组件：

- `store`
- `message`

角色：

- 持久化消息条目对象

承担语义：

- 一个 `AgentMessage`
- 可进入 session context 的标准消息记录

### `ThinkingLevelChangeEntry`

归属组件：

- `store`

角色：

- thinking level 变化记录对象

承担语义：

- 当前 thinking level 切换

### `ModelChangeEntry`

归属组件：

- `store`

角色：

- model change 记录对象

承担语义：

- provider
- model id

### `CompactionEntry`

归属组件：

- `store`
- `compaction`

角色：

- compaction 结果持久化条目

承担语义：

- summary
- first kept entry
- tokens before
- optional hook details

### `BranchSummaryEntry`

归属组件：

- `store`
- `compaction`

角色：

- branch summary 持久化条目

承担语义：

- branch return summary
- from entry id
- optional hook details

### `CustomEntry`

归属组件：

- `store`
- `extensions`

角色：

- 不进入 LLM context 的扩展持久化条目

承担语义：

- extension-specific state persistence

### `CustomMessageEntry`

归属组件：

- `store`
- `message`
- `extensions`

角色：

- 进入 LLM context 的扩展消息条目

承担语义：

- custom type
- display flag
- content
- optional details

### `LabelEntry`

归属组件：

- `store`

角色：

- label / bookmark 条目

承担语义：

- entry label
- target entry id

### `SessionInfoEntry`

归属组件：

- `store`

角色：

- session metadata 条目

承担语义：

- display name

### `SessionEntry`

归属组件：

- `store`
- `message`

角色：

- session 持久化条目联合对象

承担语义：

- `pi-coding-agent` 风格的 session file entry universe
- transcript、model/thinking 变化、compaction 与 custom metadata 统一 entry 宇宙

## Pi Alignment

- 这组对象整体直接对齐 `pi-coding-agent` 的 session entry family

## Notes

- 这组对象是 `store` 的权威记录层，同时为 `message` 层提供投影源

# `session-records`

## Scope

- session 持久化根记录、分支记录与恢复锚点对象

## Objects

### `SessionRecord`

归属组件：

- `store`

角色：

- 单个 session 的持久化根记录

承担语义：

- session identity
- session metadata
- store-level locate / restore 信息

### `SessionMetadata`

归属组件：

- `store`

角色：

- session 的持久化元数据对象

承担语义：

- 标题
- 创建时间
- 更新时间
- 当前 mode / model / profile 的摘要信息

### `SessionSummary`

归属组件：

- `store`

角色：

- 跨 session 查询与展示用 read model

承担语义：

- session identity / cwd / file / parent session
- active branch 的 message count 与最后消息预览
- active branch 派生出的当前 model
- session name 与 created/updated 时间

### `SessionQuery`

归属组件：

- `store`

角色：

- 跨 session 查询条件对象

承担语义：

- 按 cwd、name、parent session、text、limit 过滤 session summary

### `SessionBranchRecord`

归属组件：

- `store`

角色：

- branch / fork 关系记录对象

承担语义：

- parent-child 分支关系
- 分支摘要或分支关联信息

### `SessionCheckpointRecord`

归属组件：

- `store`

角色：

- 检查点或恢复点记录对象

承担语义：

- 某个可恢复时间点的引用
- 与 compaction / summarization / restore 相关的持久化锚点

## Reference Implementation Alignment

- `SessionRecord` 与 `SessionMetadata` 对齐的是 `reference CLI` 中 session header、info entry 与索引视图的组合语义
- `SessionSummary` 是面向 mode / RPC / CLI 的稳定 read model，避免上层直接解析 JSONL
- `SessionBranchRecord` 与 `SessionCheckpointRecord` 当前不直接对齐 `reference CLI` 的稳定一等对象名

## Notes

- 如果第一阶段不做完整 branch/checkpoint，可先保留对象位，不急于细化字段

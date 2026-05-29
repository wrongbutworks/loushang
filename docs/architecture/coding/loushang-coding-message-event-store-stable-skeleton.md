# Loushang Coding Message Event Store Stable Skeleton

## Scope

本文档给出 `loushang-coding` 在 Python 实现前应先稳定下来的 `message / event / store` 骨架。

本文档目标是回答：

- `loushang-coding` 的 `message` 应如何尽量对齐 `pi-coding-agent`
- `event` 应如何建立在 `loushang-agent.AgentEvent` 之上
- `store` 应采用什么样的持久化骨架与文件组织
- 哪些对象与命名应直接对齐 `pi`
- 哪些地方只做 Python 化，不改变核心语义

本文档不展开：

- 具体 Python 类实现
- 具体数据库或后端替换方案
- mode 细节
- interactive / channel 细节

## Design Basis

本轮结论主要建立在这些 `pi` 源码事实上：

- `messages.ts`
  - 定义 coding-specific custom message family
- `session-manager.ts`
  - 定义 `SessionHeader`、`SessionEntry`、`SessionContext`
  - 负责 JSONL 持久化与 `buildSessionContext()`
- `agent-session.ts`
  - 定义 `AgentSessionEvent`
- `pi-agent-core`
  - 定义基础 `AgentEvent`

参考源码：

- [pi messages.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/messages.ts:1)
- [pi session-manager.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/session-manager.ts:1)
- [pi agent-session.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/agent-session.ts:111)
- [pi agent types.ts](/home/dev/workspace/pi-mono/packages/agent/src/types.ts:326)

## Core Conclusion

如果尽量对齐 `pi-coding-agent`，则：

1. `message.ts` 不是 message 中心  
   它只是 custom message family 与 `AgentMessage -> LLM Message` 转换层。

2. `SessionEntry` 才是 `coding` 持久化中心  
   `SessionManager` 通过 `SessionEntry[]` 重建当前上下文。

3. `AgentSessionEvent` 才是 `coding` 运行观察中心  
   它建立在 `loushang-agent.AgentEvent` 之上。

因此，`loushang-coding` 不应把 `message` 设计成一个新的“大一统消息中心”，而应明确三层：

- `loushang-agent.AgentMessage`
  - 通用运行消息层
- `loushang-coding.SessionEntry`
  - 持久化记录层
- `loushang-coding.AgentSessionEvent`
  - 运行观察层

## 1. Message Skeleton

### 1.1 Stable Alignment With pi

`loushang-coding.message` 应包含两组核心对象。

#### A. Session Entry Family

这组对象是持久化中心，直接对齐 `pi-coding-agent/session-manager.ts`：

- `SessionHeader`
- `SessionEntryBase`
- `SessionMessageEntry`
- `ThinkingLevelChangeEntry`
- `ModelChangeEntry`
- `CompactionEntry`
- `BranchSummaryEntry`
- `CustomEntry`
- `CustomMessageEntry`
- `LabelEntry`
- `SessionInfoEntry`
- `SessionEntry`

#### B. Custom Agent Message Family

这组对象是 runtime message projection 层，直接对齐 `pi-coding-agent/messages.ts`：

- `BashExecutionMessage`
- `CustomMessage`
- `BranchSummaryMessage`
- `CompactionSummaryMessage`

### 1.2 Recommended Layering

建议在 `loushang-coding` 明确接受以下分层：

- `AgentMessage`
  - 仍归 `loushang-agent`
- `SessionEntry`
  - 属于 `loushang-coding.message` 与 `loushang-coding.store`
- custom agent message family
  - 属于 `loushang-coding.message`
- `SessionContext`
  - 由 `SessionManager.build_session_context()` 从 `SessionEntry[]` 投影生成
  - 语义上更应视为 `store/session` 侧的读取视图，而不是 `message` 的权威对象

### 1.3 Entry-To-Message Projection Rules

建议直接对齐 `pi` 保留这些投影关系：

- `SessionMessageEntry.message -> AgentMessage`
- `CustomMessageEntry -> CustomMessage`
- `BranchSummaryEntry -> BranchSummaryMessage`
- `CompactionEntry -> CompactionSummaryMessage`

关键判断：

- `BranchSummaryMessage` 与 `CompactionSummaryMessage` 不应直接写成 message entry
- 它们应由 `BranchSummaryEntry` / `CompactionEntry` 在构造 session context 时投影出来

### 1.4 What Not To Do

不建议：

- 新建一个很重的 `SessionMessage` 中心对象覆盖 `AgentMessage`
- 让 `message` 与 `event` 混成一个模块
- 让 `store` 直接存“当前 prompt 上下文”，而不存 `SessionEntry`

## 2. Event Skeleton

### 2.1 Stable Alignment With pi

`loushang-coding.event` 应采用：

- 基础层：`loushang-agent.AgentEvent`
- 扩展层：`AgentSessionEvent`

对齐 `pi`，`AgentSessionEvent` 建议至少包含：

- `AgentEvent`
- `queue_update`
- `compaction_start`
- `compaction_end`
- `auto_retry_start`
- `auto_retry_end`

### 2.2 Event Layering

建议明确三层语义：

- `AgentEvent`
  - agent runtime 事件
- `AgentSessionEvent`
  - coding product 扩展事件
- future boundary projection
  - 未来若接 `channel`，再从 `AgentSessionEvent` 投影边界事件

### 2.3 Event Design Rule

建议保持与 `pi` 一致：

- `message` 负责运行消息与持久化条目
- `event` 负责运行过程观察面
- 不把流式 message delta 本身塞回 store

## 3. Store Skeleton

### 3.1 Stable Alignment With pi

`store` 的第一版稳定骨架建议直接对齐 `pi SessionManager`：

- session 文件采用 `jsonl`
- 第一条记录为 `SessionHeader`
- 后续每条记录为 `SessionEntry`
- 通过 `id` / `parentId` 形成树结构

### 3.2 Recommended File Model

建议采用：

- `SessionHeader`
  - `type = "session"`
  - `version`
  - `id`
  - `timestamp`
  - `cwd`
  - `parentSession?`

- `SessionEntry`
  - 一行一个 JSON object
  - append-only 为主

这意味着：

- 单 session 文件 = `header + entries`
- `SessionManager` 负责：
  - `append_entry`
  - `load_entries`
  - `build_session_context`
  - migration

### 3.3 Context Reconstruction Rule

建议直接保留 `pi` 的基本思路：

- `build_session_context(entries, leaf_id)`
  - 从 leaf 走到 root
  - 沿路径恢复：
    - current model
    - current thinking level
    - compaction boundary
  - 然后再把相关 entry 投影成 `AgentMessage[]`

这比“直接把当前上下文缓存落盘”更稳，因为：

- 可恢复
- 可迁移
- 可分支
- 可重建

### 3.4 Store Versioning

建议一开始就保留：

- `CURRENT_SESSION_VERSION`
- migration hook

因为 `pi` 的 session 结构已经演化过：

- v1 -> v2：补 tree structure
- v2 -> v3：`hookMessage` 重命名为 `custom`

这说明 `store` 一开始就应接受：

- 文件格式会演化
- migration 是一等职责

## 4. Pythonization Rule

本轮建议遵守：

### 4.1 Object Names

对象名优先对齐 `pi`：

- `SessionHeader`
- `SessionEntryBase`
- `SessionEntry`
- `SessionContext`
- `AgentSessionEvent`
- `BashExecutionMessage`
- `CustomMessage`

### 4.2 Method Names

方法名 Python 化：

- `buildSessionContext()` -> `build_session_context()`
- `appendCustomMessageEntry()` -> `append_custom_message_entry()`
- `appendModelChange()` -> `append_model_change()`

### 4.3 Field Names

字段命名建议分两层：

- Python 内部对象字段
  - 可使用 `snake_case`
- 持久化 JSON schema
  - 建议尽量保持与 `pi` 相近的 key 语义

如果实现上采用 Python 模型库，建议通过 alias 机制保持：

- Python 代码可读
- 持久化 schema 稳定
- 与 `pi` 参考结构可直接对照

## 5. Recommended Module Skeleton

如果按 Python 包组织，当前建议至少拆成：

- `loushang/coding/message/entries.py`
  - `SessionHeader`
  - `SessionEntryBase`
  - `SessionEntry*`
  - `SessionContext`
  - 这里的共置主要是实现层组织选择，不改变 `SessionContext` 作为 `store/session` 侧读取视图的语义归属

- `loushang/coding/message/custom_messages.py`
  - `BashExecutionMessage`
  - `CustomMessage`
  - `BranchSummaryMessage`
  - `CompactionSummaryMessage`

- `loushang/coding/message/transformers.py`
  - `create_custom_message`
  - `create_branch_summary_message`
  - `create_compaction_summary_message`
  - `convert_to_llm`

- `loushang/coding/event/types.py`
  - `AgentSessionEvent`

- `loushang/coding/store/session_manager.py`
  - `SessionManager`
  - append/load/build context

- `loushang/coding/store/file_codec.py`
  - JSONL read/write
  - schema version
  - migration

## 6. Implementation Order

按当前架构决策，建议实现顺序为：

1. `message.entries`
2. `message.custom_messages`
3. `message.transformers`
4. `store.file_codec`
5. `store.session_manager`
6. `event.types`

理由：

- `message + store` 是被依赖最多的中心层
- `event` 要建立在 `AgentEvent` 与 `AgentSession` 交互方式之上
- 先稳定 entry/store，再接 `AgentSession`，返工最少

## 7. Immediate Next Step

在进入实现前，建议再补一份更窄的设计说明：

- `SessionEntry` family 字段草案
- `AgentSessionEvent` 事件族草案
- session JSONL file schema 草案

这一步完成后，再开始真正开发：

- `message`
- `store`
- `event`

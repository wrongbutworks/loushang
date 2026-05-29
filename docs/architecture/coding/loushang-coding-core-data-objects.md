# Loushang Coding Core Data Objects

## Scope

本文档作为 `loushang-coding` 核心数据对象设计的总入口。

它主要回答：

- 什么对象应算作核心数据对象
- 这些对象按什么对象族来阅读
- 哪些对象不再属于 data objects 范围

详细对象族说明统一放在：

- [core-data-objects/](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/README.md)

## Design Basis

本文档建立在以下文档之上：

- [Loushang Coding Component Structure And Responsibilities](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-structure-and-responsibilities.md)
- [Loushang Coding Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)
- [Loushang Coding Deployment Unit Terminology](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-du-terminology.md)
- [Loushang Agent Types](/home/dev/workspace/loushang/docs/architecture/agent/loushang-agent-types.md)

## What Counts As A Core Data Object

当前建议只把这类对象放进 core data objects：

- 跨组件有稳定语义的数据对象
- 需要明确 source of truth 的对象
- 可能被持久化、投影、复制、传输的对象

当前不应继续放进这里的对象：

- `AgentSessionRuntime`
- `AgentSession`

这两个对象属于服务对象，已回到：

- [Loushang Coding Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)

## Reading Rule

建议按下面顺序阅读：

1. 先看本文档，理解对象边界与阅读入口
2. 再看 [core-data-objects/](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/README.md) 进入对象族文档
3. 如需理解对象由谁协调，再回看 [Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)

对于跨多个组件出现的对象，阅读时还应额外区分：

- 哪个组件对该对象承担权威记录或重建职责
- 哪些组件只是消费、投影或转发该对象

例如：

- `SessionContext` 可被 `session`、`prompt`、`mode` 消费
- 但其重建职责仍应优先落在 `store`

## Object Family Navigation

### Runtime State Objects

- [runtime-state.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/runtime-state.md)

### Session Record Objects

- [session-records.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/session-records.md)

### Entry Family Objects

- [entry-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/entry-family.md)

### Message Family Objects

- [message-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/message-family.md)

### Event Family Objects

- [event-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/event-family.md)

### Control And Config Objects

- [control-configs.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/control-configs.md)

### Tool, Exec, And Policy Objects

- [tool-exec-policy.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/tool-exec-policy.md)

### Prompt And Compaction Objects

- [prompt-compaction.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/prompt-compaction.md)

### Resource Descriptor Objects

- [resource-descriptors.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/resource-descriptors.md)

### Diagnostic Objects

- [diagnostics.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/diagnostics.md)

## Object Classification

当前建议把核心数据对象分为五类：

1. 运行态状态对象
2. 持久化与记录对象
3. 消息与事件对象
4. 控制与装配对象
5. 资源与诊断对象

## Cross-Component Exchange Backbone

如果只看第一批最重要的跨组件交换对象，建议优先关注：

- `SessionRecord`
  - `runtime/session <-> store`

- `SessionEntry`
  - `session/store <-> message`

- `SessionContext`
  - `store/session <-> prompt`

- `AgentSessionEvent`
  - `session <-> event <-> mode`

- `ToolDefinition`
  - `session <-> tools`

- `ExecRequest` / `ExecResult`
  - `tools <-> exec`

- `PromptAssembly`
  - `session <-> prompt`

- `ResourceBundle`
  - `loader <-> session/prompt/extensions/skill/method`

- `PolicyDecision`
  - `policy <-> tools/exec/session/mode`

- `ModelSelection`
  - `control <-> session`
  - `control <-> loushang-ai`

## Related Docs

- [Loushang Coding Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)
- [Loushang Coding Component Interfaces](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-interfaces.md)
- [Loushang Coding Deployment Unit Terminology](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-du-terminology.md)
- [Core Data Object Notes](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/README.md)

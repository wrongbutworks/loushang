# `event-family`

## Scope

- coding 产品层的事件与事件封装对象

## Objects

### `AgentSessionEvent`

归属组件：

- `event`

角色：

- `loushang-coding` 层的标准事件对象

承担语义：

- session lifecycle
- run lifecycle
- mode 可观察事件
- tool execution lifecycle
- diagnostics-friendly event surface

### `EventEnvelope`

归属组件：

- `event`

角色：

- 统一包装运行事件的信封对象

承担语义：

- event kind
- source
- payload
- correlation / timestamp

## Reference Implementation Alignment

- `AgentSessionEvent` 直接对齐 `reference coding agent`
- `EventEnvelope` 当前更像概念对象，为未来 channel/protocol 投影预留

## Notes

- 如果后续引入 `channel`，`EventEnvelope` 很可能成为边界投影基础
- `PrintMode` 的 JSON projection 当前直接消费 `AgentSessionEvent`，见 [Loushang Coding JSON Mode Design](../loushang-coding-json-mode-design.md)

# `mode`

## Role

- I/O adapter 与运行表面组件

## Owns

- 用户可见运行形态：`print / json / rpc / interactive`
- `ModeAdapter` 抽象边界
- `PrintMode` / `RpcMode` / `InteractiveMode`（future）等 adapter object
- `json` 作为 `PrintMode` 的结构化输出 projection
- runtime event 到输出投影的规则

## Depends On

- `runtime`
- `session`
- `event`
- `policy`

## Commands

- `start(...)`
- `stop(...)`
- `submit_input(...)`
- `wait_for_idle(...)`
- `rebind_session(...)`
- `await dispose(...)`
- `render_event(...)`
- `normalize_mode_action(...)`
- `dispatch_mode_action(...)`

## Queries

- `get_mode_state()`

## Events

- 消费 `AgentSessionEvent`
- mode 自身当前无稳定独立事件协议

## Key Data

- `ModeConfig`
- `ModeAction`
- `ModeActionType`
- `AgentSessionEvent`

## Out Of Scope

- 运行主循环
- transcript persistence
- model / auth / settings 存储
- session/store 内部结构读取
- control policy 或状态轮换策略
- session lifecycle 实现细节，例如 clone/fork/switch 的业务规则

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 中 `InteractiveMode` / `runPrintMode` / `runRpcMode` 这组 mode adapter
- 这里的 `PrintMode` / `RpcMode` 表示 mode-level service boundary，不要求最终一定以类实现
- `json` 在架构上视为 `PrintMode` 的输出变体，而不是独立 runtime adapter
- 强调 mode 只是 I/O projection，不是另一套 runtime core
- RPC/mode handler 采用 `validate -> call session/runtime -> serialize` 结构
- `cycle_model`、`cycle_thinking_level`、`clone_session`、entry text extraction 等业务语义应由 `session` / `runtime` facade 承担
- `ModeAction` 覆盖 `start` / `stop` / `submit_input` / `render_event` / `get_state` / `wait_for_idle` / `rebind_session` / `dispose`，供 CLI/RPC/未来 interactive 共享 adapter lifecycle contract
- `normalize_mode_action(...)` 是 dataclass 与 JSON-like action payload 的唯一归一化入口；`dispatch_mode_action(...)` 先归一化再派发，避免各 mode host 各自解析 action dict
- 不追求逐字复刻 参考实现的 TypeScript shape，但保持同样的边界：mode 不直接读取 store，不实现控制策略，不拥有 session lifecycle

## Related Docs

- [Loushang Coding JSON Mode Design](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-json-mode-design.md)
- [Loushang Coding RPC Mode Surface](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-rpc-mode-surface.md)
- [RPC Component Interface](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/rpc.md)

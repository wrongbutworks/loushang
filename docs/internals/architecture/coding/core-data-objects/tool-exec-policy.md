# `tool-exec-policy`

## Scope

- 工具、执行与策略判定相关对象

## Objects

### `PolicyDecision`

归属组件：

- `policy`

角色：

- 权限 / 审批 / 执行约束的判定结果对象

承担语义：

- allow / deny / ask
- 审批来源
- 适用范围与原因

### `ToolDefinition`

归属组件：

- `tools`

角色：

- coding 工具定义对象

承担语义：

- tool identity
- prompt / UI 可见元信息
- 参数 schema 与参数预处理
- execution contract 与展示信息

### `ToolCallRecord`

归属组件：

- `tools`
- `message`
- `store`

角色：

- 工具执行派生记录对象

承担语义：

- 调用参数
- 调用时机
- 调用结果引用

### `ToolResultRecord`

归属组件：

- `tools`
- `message`
- `store`

角色：

- 工具执行结果派生记录对象

承担语义：

- 结果内容
- 结果状态
- 错误或拒绝语义

### `ExecRequest`

归属组件：

- `exec`

角色：

- 命令执行请求对象

承担语义：

- shell / subprocess 请求
- cwd / env / timeout / permission 输入

### `ExecResult`

归属组件：

- `exec`

角色：

- 命令执行结果对象

承担语义：

- stdout / stderr / exit status
- execution metadata
- sandbox / failure 信息

## Reference Implementation Alignment

- `ToolDefinition` 直接对齐 `reference coding agent`
- `PolicyDecision`、`ExecRequest`、`ExecResult` 当前不直接对齐 `reference CLI` 的稳定同名一等对象

## Notes

- `ToolDefinition` 是第一批稳定工具边界中的中心对象
- `ToolCallRecord` 与 `ToolResultRecord` 如果引入，更适合作为执行派生记录，而不是 registry 中心
- `ToolCallRecord` 与 `ToolResultRecord` 既是工具层对象，也会进入 message/store 记录面

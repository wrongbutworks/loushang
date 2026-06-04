# `policy`

## Role

- 权限、审批与 guardrail 判定组件

## Owns

- `PolicyEngine`
- `PackageSecurityPolicy`
- `PolicyDecision`
- `ApprovalRequest`
- `ApprovalDecision`
- `ApprovalResolver`
- `PolicyEnforcementError`
- destructive action guardrails
- sandbox / approval policy
- generic tool-call allow / deny / ask rules
- package/plugin source security guardrails

## Depends On

- `control`
- `exec`
- optional tool metadata as policy input

## Commands

- `evaluate_action(...)`
- `evaluate_tool_call(...)`
- `ApprovalResolver.resolve(...)`
- `PackageSecurityPolicy.evaluate_package_source(...)`
  - compatibility alias: `evaluate_plugin_source(...)`

## Queries

- 当前无稳定 query surface

## Events

- 当前无稳定事件面

## Key Data

- `PolicyDecision`
  - `disposition`: `allow` / `deny` / `ask`
  - `reason`: user-facing explanation
  - `code`: machine-readable policy reason, e.g. `tool_blocked`
- `ApprovalRequest`
  - tool name, arguments, cwd, policy reason/code
- `ApprovalDecision`
  - final `allow` / `deny` result for an `ask` policy decision
- `PolicyEnforcementError`
  - extends `PermissionError`
  - exposes `tool_result_details` so agent/event layers can project policy and approval failures without importing policy internals
  - stable details keys: `tool_name`, `cwd`, `policy_disposition`, `policy_code`, `policy_reason`,
    `approval_required`, `approval_decision`, `approval_reason`, `argument_keys`
  - path-like/command context may be included as `path`, `file_path`, or `command`; large payload fields such as file content are not projected

## Out Of Scope

- tool registration
- shell execution
- approval UI rendering
- session transcript persistence
- model selection

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 中 permissions / approvals / guardrails
- 保留显式 `PolicyEngine`，不把这层判定逻辑散落进 mode、tool、exec
- `evaluate_tool_call(...)` 对齐 `reference CLI` 的 `beforeToolCall` 判定点：工具参数校验后、实际执行前做 allow / deny / ask。
- `ApprovalResolver` 是 UI/RPC/CLI 未来承接审批交互的注入点；当前默认 `DenyApprovalResolver`
  保持无 UI 环境下的阻断语义。
- mode 可以承接审批交互呈现，但 `PolicyEngine` 自身应保持 mode-neutral
- Package/plugin source policy is also mode-neutral: local sources are allowed, HTTPS/SSH-style remote sources are allowed for registration, and insecure `http://` remote sources are denied by default.
- Package materialization is a policy enforcement point, not only CLI source registration. Denied sources must not call the materializer backend and should project as `failed` / `denied` package records.

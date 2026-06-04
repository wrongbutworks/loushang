# `bootstrap`

## Role

- `loushang-coding` 的默认装配入口

## Owns

- `BootstrapServices`
- 默认 service wiring
- `AgentSession` / `AgentSessionRuntime` 创建链

## Depends On

- `control`
- `loader`
- `prompt`
- `runtime`
- `session`
- `store`
- `loushang-agent`

## Commands

- `create_services(...)`
- `create_agent_session(...)`
- `create_agent_session_runtime(...)`

## Queries

- 当前无稳定 query surface

## Events

- 无

## Key Data

- `BootstrapServices`
- `ControlConfig`

## Out Of Scope

- session 生命周期管理
- transcript persistence
- tool / exec / policy 实现细节

## Reference Implementation Alignment

- 语义上对齐 `reference CLI` 的 `main.ts` + `agent-session-services.ts` + `sdk.ts` 装配链
- 当前保留模块级工厂函数，而不是先抽成更重的 bootstrap 对象
- `bootstrap` 表达的是 `loushang` 对分散装配链的收束边界，不要求在 `reference CLI` 中存在同名中心对象

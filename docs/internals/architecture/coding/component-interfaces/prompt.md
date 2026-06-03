# `prompt`

## Role

- 资源层与 session 运行时之间的 prompt bridge

## Owns

- base prompt 与资源片段的组装规则
- 最终 system prompt 的拼接入口
- 后续 `PromptAssembly` 的落位边界

## Depends On

- `loader`
- `tools`
- `control`
- `method`

## Commands

- `assemble_system_prompt(...)`
- `assemble_prompt(...)`

## Queries

- 无稳定 query surface

## Events

- 无

## Key Data

- `ResourceBundle`
- `PromptAssembly`

## Out Of Scope

- 资源发现
- skill / method 解析
- tool execution
- session persistence

## Pi Alignment

- 语义上对齐 `pi` 中 `system-prompt.ts` 与 session 内资源注入共同承担的 prompt assembly 职责
- `loushang` 明确保留独立 `prompt` 组件，而不把它完全埋进 `session` 或 `loader`

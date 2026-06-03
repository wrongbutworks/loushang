# `method`

## Role

- coding method 注册、选择与注入组件

## Owns

- `MethodRegistry`
- method 元数据
- method 到 prompt/skill 的投影规则
- session method 选择状态

## Depends On

- `prompt`
- `skill`
- `loader`
- `session`

## Commands

- `register_method(...)`
- `select_method(...)`
- `reload_methods(...)`

## Queries

- `get_method(...)`
- `list_methods()`
- `get_selected_method()`

## Events

- 当前无稳定事件面

## Key Data

- `MethodDescriptor`

## Out Of Scope

- skill 文件发现
- prompt 最终渲染
- session 持久化细节

## Pi Alignment

- 语义上吸收 `pi` 中 method guidance / mode behavior 的经验
- 在 `loushang` 里单独抽成 registry，避免 method 逻辑散落在 prompt 或 mode 中

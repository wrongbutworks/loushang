# `loader`

## Role

- coding 资源发现、聚合与归一化组件

## Owns

- `DefaultResourceLoader`
- `PackageResourceSummary`
- `ResourceBundle`
- 资源发现入口
- skills / prompts / extensions / themes / `AGENTS.md` 的聚合边界

## Depends On

- filesystem
- `control`

## Commands

- `discover_resources(...)`
- `reload_resources(...)`

## Queries

- `get_resource_bundle()`
- `get_skills()`
- `get_prompts()`
- `get_agents_files()`
- `get_append_system_prompt()`
- `get_system_prompt(...)`
- `get_extensions()`
- `get_resource_diagnostics(...)`
- `get_package_resource_summaries()`

## Events

- 无

## Key Data

- `ResourceBundle`
- `PackageResourceSummary`
- 资源 descriptor provenance：
  - `source`: 原始来源类型，当前主要为 `filesystem`
  - `source_kind`: `built_in` / `project_local` / `external_package`
  - `source_scope`: `builtin` / `project` / `package`
  - `source_root`: 资源所在类别目录，例如 package 的 `prompts/`、`skills/`、`extensions/`

## Out Of Scope

- prompt 最终组装
- session 生命周期
- skill / extension 执行逻辑

## Pi Alignment

- 语义上直接对齐 `pi` 的 `DefaultResourceLoader` 作为资源聚合中心的定位
- `loushang` 可以在内部继续显式拆出 skill/extension/prompt asset 的子边界，但不改变 `loader` 作为资源 hub 的主语义
- 保留显式 `loader` 边界，避免把资源发现逻辑散落进 bootstrap 或 session
- loader 是 package provenance 的源头；session / RPC / CLI 只做投影，不重新推断 package 来源
- theme discovery 对齐 pi 的资源诊断语义：themes 目录下非 `.json` 文件会跳过并记录
  `unsupported_theme_entry` warning，而不是作为 theme descriptor 暴露
- loader 查询面对齐 `pi` 的资源读取面：`AGENTS.md` 投影、append system prompt fragments、
  以及基于当前 resource bundle 的 assembled system prompt 都从 `DefaultResourceLoader` 暴露，供 runtime/RPC 复用
- package roots 不再静默失败：missing / invalid / empty package root 会产生稳定 resource diagnostic
- package summary 查询面提供 prompt / skill / extension / theme / diagnostic 计数，后续 CLI/RPC/TUI 只做展示投影

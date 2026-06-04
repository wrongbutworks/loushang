# `control`

## Role

- coding 产品的控制平面聚合边界

## Owns

- `BranchSummarySettings`
- `CompactionSettings`
- `ControlConfig`
- `ImageSettings`
- `MarkdownSettings`
- `ModelSelection`
- `QueueMode`
- `RetrySettings`
- `SettingsManager`
- `TerminalSettings`
- `WarningSettings`
- `ModelRegistry`
- settings / model selection 的统一控制平面语义

## Depends On

- `loushang-ai`
- `coding.types`

## Commands

- `SettingsManager.update_settings(...)`
- `SettingsManager.set_default_model(...)`
- `SettingsManager.set_steering_mode(...)`
- `SettingsManager.set_follow_up_mode(...)`
- `SettingsManager.set_theme(...)`
- `SettingsManager.set_transport(...)`
- `SettingsManager.set_shell_path(...)`
- `SettingsManager.set_shell_command_prefix(...)`
- `SettingsManager.set_npm_command(...)`
- `SettingsManager.set_enable_skill_commands(...)`
- `SettingsManager.set_enabled_models(...)`
- `SettingsManager.set_double_escape_action(...)`
- `SettingsManager.set_tree_filter_mode(...)`
- `SettingsManager.set_show_hardware_cursor(...)`
- `SettingsManager.set_editor_padding_x(...)`
- `SettingsManager.set_autocomplete_max_visible(...)`
- `SettingsManager.set_resource_roots(...)`
- `SettingsManager.set_package_roots(...)`
- `SettingsManager.set_plugin_sources(...)`
- `SettingsManager.set_disabled_skills(...)`
- `SettingsManager.set_disabled_plugins(...)`
- `SettingsManager.set_image_auto_resize(...)`
- `SettingsManager.set_block_images(...)`
- `SettingsManager.set_show_images(...)`
- `SettingsManager.set_image_width_cells(...)`
- `SettingsManager.set_clear_on_shrink(...)`
- `SettingsManager.set_show_terminal_progress(...)`
- `ModelRegistry.register_model(...)`

## Queries

- `SettingsManager.get_settings()`
- `SettingsManager.get_setting(...)`
- `SettingsManager.get_global_settings()`
- `SettingsManager.get_project_settings()`
- `SettingsManager.get_session_settings()`
- `SettingsManager.drain_errors()`
- `SettingsManager.get_transport()`
- `SettingsManager.get_theme()`
- `SettingsManager.get_shell_path()`
- `SettingsManager.get_shell_command_prefix()`
- `SettingsManager.get_npm_command()`
- `SettingsManager.get_thinking_budgets()`
- `SettingsManager.get_compaction_settings()`
- `SettingsManager.get_branch_summary_settings()`
- `SettingsManager.get_branch_summary_skip_prompt()`
- `SettingsManager.get_provider_retry_settings()`
- `SettingsManager.get_enable_skill_commands()`
- `SettingsManager.get_enabled_models()`
- `SettingsManager.get_double_escape_action()`
- `SettingsManager.get_tree_filter_mode()`
- `SettingsManager.get_show_hardware_cursor()`
- `SettingsManager.get_editor_padding_x()`
- `SettingsManager.get_autocomplete_max_visible()`
- `SettingsManager.get_resource_roots()`
- `SettingsManager.get_package_roots()`
- `SettingsManager.get_plugin_sources()`
- `SettingsManager.get_disabled_skills()`
- `SettingsManager.get_disabled_plugins()`
- `SettingsManager.get_image_settings()`
- `SettingsManager.get_terminal_settings()`
- `SettingsManager.get_markdown_settings()`
- `SettingsManager.get_code_block_indent()`
- `SettingsManager.get_warnings()`
- `ModelRegistry.get_model(...)`
- `ModelRegistry.list_models()`
- `ModelRegistry.resolve_model(...)`
- `ModelRegistry.build_model(...)`

## Events

- `SettingsManager.subscribe(...)`

## Key Data

- `ControlConfig`
- `ModelSelection`
- `CompactionSettings`
- `BranchSummarySettings`
- `RetrySettings`
- `ImageSettings`
- `TerminalSettings`
- `MarkdownSettings`
- `WarningSettings`

## Out Of Scope

- auth storage
- policy / approval 判定
- session runtime 状态
- prompt 内容本身

## Reference Implementation Alignment

- `SettingsManager` 与 `ModelRegistry` 的核心语义分别直接对齐 `reference CLI`
- `control` 是 `loushang` 在架构上对这些控制面服务的聚合边界，不要求对齐成单一 `reference CLI` 对象名
- settings/control 覆盖 reference implementation headless MVP 所需的 queue mode、transport、theme、shell、npm、terminal、image、thinking budget、retry provider cap、skill command enablement、enabled model cycling、resource/package source 管理等偏好
- branch summary 覆盖 reference implementation headless 可见的 `reserve_tokens` 与 `skip_prompt` 语义；`enabled` 是 loushang 为策略控制保留的扩展字段
- compaction 覆盖 参考实现的 `reserve_tokens` / `keep_recent_tokens` 语义，并额外提供全局 `compact_percent`；
  实际 threshold 由 `compaction.policy` 取 percent threshold 与 reserve threshold 中更保守者，配置通过
  `~/.loushang/coding/settings.json`、项目 `.loushang/settings.json` 与 session overrides 合并
- TUI-only 偏好，例如 double-escape action、tree filter、editor padding、hardware cursor、autocomplete max visible，已作为 headless settings surface 暴露；当前不实现对应 interactive/TUI 消费层
- provider/model 配置有意不复制 reference implementation flat provider contract，继续使用 `loushang.ai` 的 Provider -> Endpoint -> Model 分层

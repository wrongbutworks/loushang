# `cli`

## Role

- 命令行入口组件

## Owns

- 参数解析
- 命令分发
- mode 启动入口

## Depends On

- `bootstrap`
- `runtime`
- `mode`

## Commands

- `main(...)`
- `run(...)`
- `dispatch_command(...)`
- `--list-commands` 输出：`name<TAB>source<TAB>path<TAB>description`

## Args

- `list_sessions`: 列出 session；默认只查当前 session dir
- `all_sessions`: 与 `list_sessions` 配合，跨 sessions root 聚合兄弟 session dir
- `list_sessions_format`: `tsv` / `json`
- `session_index`: 与 `list_sessions` 配合，显式使用 runtime indexed summary facade
- `refresh_session_index`: 与 `list_sessions` 配合，先刷新当前或 all-session index，再走 indexed summary facade；该选项隐含 `session_index`
- `session_cwd` / `session_name_filter` / `session_parent` / `session_query` / `session_limit`: `--list-sessions` 过滤参数，映射到 `SessionQuery`
- `session_has_diagnostics`: `--session-has-diagnostics` / `--session-no-diagnostics`，映射到 `SessionQuery.has_diagnostics`
- `list_commands`: 列出当前会话可用命令（包含 extension/prompt/skill）
- `command`: 直接执行单个会话命令（`/command args` 的会话命令分发等效）
- `command_args`: 透传给目标命令的参数文本
- `package_catalog`: 与 `list_packages` 配合，读取本地 catalog JSON 并把 catalog entries 合并进 package projection；不执行网络安装
- 两阶段解析流程：先做一次 `allow_unknown=True` 引导，发现 extension flags；再按完整 flag 表重解析并下发 `extension_flag_values`
- 兼容字段：`help`/`version`/`export`/`--list-models` 早退并直接返回

## Queries

- 当前无稳定 query surface

## Events

- 无独立事件面

## Key Data

- `ModeConfig`
- `SessionCommandDescriptor`（会话暴露）：  
  - `name: str`
  - `description: str | None`
  - `source: "extension" | "prompt" | "skill"`
  - `source_info: CommandSourceInfo`
- CLI `--list-commands` 从 `AgentSession.list_commands()` 读取 typed descriptor，并投影为 CLI 的 TSV/JSON 输出
- CLI `--list-sessions` 有过滤参数时使用 runtime `find_session_summaries(SessionQuery)`；`--all-sessions` 时使用 `find_all_session_summaries(SessionQuery)` / `list_all_session_summaries()`
- CLI `--list-sessions --session-index` 使用 runtime indexed summary facade；`--refresh-session-index` 会先调用 `refresh_session_index()` 或 `refresh_all_session_indexes()`
- session listing JSON 会保留 `SessionSummary` 的轻量 index 字段，包括 diagnostics metadata；TSV 输出保持稳定的五列基础格式
- package/plugin/skill settings 管理类命令会在执行前 drain `SettingsManager` load errors，并以 `Warning (<context>, <scope> settings): ...` 输出到 stderr；warning 不改变成功命令的 exit code。
- session listing JSON 包含 `first_message` / `all_messages_text`；TSV 暂不输出这两个字段，避免破坏既有列顺序
- pi-style package 子命令在 headless MVP 中是入口别名：
  - `list` 单独出现时映射到 `--list-plugins`
  - `install <source>` 映射到 `--install-package <source>`
  - `remove <source>` / `uninstall <source>` 映射到 `--uninstall-package <source>`
  - `-l` / `--local` 被接受为本地 source 操作提示，当前 project scope 与既有 settings 行为一致
- `install https://...` registers the source and materializes the remote package; `install http://...` is rejected by package source security policy.
- `--list-packages --list-packages-format json` projects registered remote sources as `packageKind=remote_package` entries while preserving `kind=remote_plugin` for compatibility.
- Explicit package manager flags are available for headless automation:
  `--install-package`, `--uninstall-package`, `--materialize-package`, `--update-package`, `--update-packages`, `--check-package-updates`, and `--remove-package`.

## Out Of Scope

- session 核心逻辑
- transcript 持久化
- tool / exec / policy 实现
- approval UI and optional package trust hardening; explicit package signature verification is not a current pi parity requirement

## Pi Alignment

- 语义上对齐 `pi` 的 CLI / main entry surface
- 保持 CLI 只做入口与分发，不承载运行核心

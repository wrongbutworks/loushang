# Loushang vs Pi Coding Gap Report (2026-05-01)

## Scope

- 对比对象：`loushang-coding` 当前实现 vs 架构规划 interface + `pi-coding-agent` 参考对齐
- 排除范围：Interactive/TUI（暂不纳入本次清单）
- 数据来源：`docs/architecture/coding/component-interfaces/*.md` 接口清单 + 当前 `src/loushang/coding` 实现扫描
- 时间：2026-05-01

## 按组件完成度清单（规划）

| 组件 | 规划完成% | 规划差距% | 说明 |
| --- | ---: | ---: | --- |
| bootstrap | 100.0 | 0.0 | create_services / create_agent_session / create_agent_session_runtime 已对齐 |
| cli | 66.7 | 33.3 | `run_dispatch` 与 `dispatch_command` 等入口链路仍需补齐 |
| compaction | 50.0 | 50.0 | `compact_session/maybe_compact_after_turn/get_status` 等未落地 |
| control | 100.0 | 0.0 | settings / model 管理主语义完整 |
| diagnostics | 40.0 | 60.0 | startup check 与 error normalization 框架未完整 |
| event | 100.0 | 0.0 | session 事件入口/选择/序列化链路完整 |
| exec | 100.0 | 0.0 | `ExecService` 与请求/结果对象对齐 |
| extensions | 11.1 | 88.9 | 仅基础加载存在；runner 生命周期扩展接口未完整 |
| loader | 100.0 | 0.0 | 资源发现与刷新接口基本完整 |
| message | 100.0 | 0.0 | 会话消息转换与 custom message factory 覆盖到位 |
| method | 0.0 | 100.0 | 整体未独立落地 `MethodRegistry` |
| mode | 0.0 | 100.0 | 除 print/rpc 适配面，`ModeAdapter/submit_input/render_event` 等未分层抽离 |
| plugin | 0.0 | 100.0 | 插件分发与解析未独立落地 |
| policy | 100.0 | 0.0 | policy engine 基本对齐 |
| prompt | 100.0 | 0.0 | prompt 组装接口到位 |
| runtime | 100.0 | 0.0 | session 运行时切换、恢复、切换接口完整 |
| sdk | 100.0 | 0.0 | 入口工厂链路完整 |
| session | 100.0 | 0.0 | 核心 session 门面能力完整 |
| skill | 0.0 | 100.0 | skill 发现与加载入口尚未单独组件化 |
| store | 100.0 | 0.0 | 持久化与重建能力完整 |
| tools | 100.0 | 0.0 | 工具 registry + 查询链路完整 |
| utils | N/A | N/A | 当前无独立 utils 组件，作为薄层辅助未抽离 |

> 注：`utils` 当前在架构中定位为薄辅助层，不属于本次接口方法清单直接计算口径。

## 与 pi 对齐完成度清单（非 TUI）

| 组件 | 与 pi 对齐% | 与 pi 差距% | 说明 |
| --- | ---: | ---: | --- |
| bootstrap | 95 | 5 | 与 `main.ts + services + sdk` 装配链路语义一致 |
| cli | 80 | 20 | `list-models/list-commands/list-sessions` 与 command plane 部分完成，命令分发稳定性可增强 |
| compaction | 65 | 35 | 核心决策与状态位有缺口 |
| control | 95 | 5 | Settings/Model 管理边界齐全 |
| diagnostics | 60 | 40 | startup checks / 标准化错误处理仍有差距 |
| event | 90 | 10 | 事件序列化与投影完整度高 |
| exec | 90 | 10 | 命令执行边界可继续对齐更细粒度行为 |
| extensions | 40 | 60 | 运行时 hook 生命周期对齐不足 |
| loader | 90 | 10 | 资源聚合口径与扩展发现稳定 |
| message | 100 | 0 | 与 pi 的 message/event family 对齐度高 |
| method | 10 | 90 | method guidance/选择层仍缺 |
| mode | 50 | 50 | print/rpc 与 pi 的 adapter 思路接近，未形成完整 mode 接口层 |
| plugin | 20 | 80 | package/distribution 管理与展开尚未对齐 |
| policy | 70 | 30 | 关键决策核心得到实现，但细化策略与上游一致性不足 |
| prompt | 90 | 10 | prompt bridge 基础齐全 |
| runtime | 95 | 5 | runtime 生命周期高一致 |
| sdk | 95 | 5 | SDK 工厂链路高一致 |
| session | 95 | 5 | session 门面语义基本对齐 |
| skill | 10 | 90 | skill 加载/发现/注册仍是空白 |
| store | 100 | 0 | 与 pi session 持久化模型高度一致 |
| tools | 95 | 5 | 工具定义与注册链路基本齐全 |
| utils | 20 | 80 | 工具层薄化基础较弱 |

## 总体指标（非 TUI）

- 规划完成率（总体）：**69.9%**
- 规划缺口（总体）：**30.1%**
- 与 pi 对齐率（总体）：**70.7%**
- 与 pi 差距（总体）：**29.3%**

## 下一步建议（按缺口优先）

1. 先补 `method / skill / plugin`（0%）形成资源/方法链路闭环。
2. 再补 `mode`（0%）的 adapter 抽象层与状态接口。
3. 再补 `extensions / diagnostics / compaction`（低中位）以固化 runtime 边界与稳定性。

## 2026-05-01 更新（会话核心链路加固）

- 2026-05-01 继续补齐 `store/session` 基础链路稳定性：
  - `src/loushang/coding/store/file_codec.py`: `load_session_file` 改为跳过损坏的会话行，避免单条错误导致整文件不可恢复。
  - `src/loushang/coding/store/session_manager.py`: `SessionManager.list()` 改为忽略损坏的会话文件，保留可用列表返回。
  - `tests/coding/test_session_file_codec.py`: 增加 `test_load_session_file_skips_invalid_lines`。
  - `tests/coding/test_session_manager.py`: 增加 `test_list_skips_invalid_session_files`。
  - `tests/coding/test_agent_session_runtime.py`: 增加 `test_runtime_list_sessions_skips_invalid_session_files`。
- 该批改动通过相关测试（28 passed）。
- 未形成突破的核心缺口仍主要集中在：
  - `method / skill / plugin`
  - `mode`（已有基础 adapter，但未形成独立完善状态与命令行为收口）
  - `extensions`（运行时生命周期与诊断链路仍有缺口）

## 2026-05-01 更新（extensions / mode 对齐推进）

- 2026-05-01 继续补齐 `extensions` 的 session runtime hook 返回面：
  - 新增 `SessionBeforeTreeResult` / `SessionBeforeCompactResult` / `SessionBeforeForkResult`。
  - `session_before_tree` 支持 extension 覆盖 branch summary、custom instructions、replace flag、label。
  - `session_before_compact` 支持 extension 直接提供 compaction result，并在 session entry 上标记 `from_hook`。
  - 兼容旧 `SessionActionDecision` 返回，避免现有 extension hook 因类型收窄失效。
- 2026-05-01 继续补齐 `mode` 基础 adapter plane：
  - 新增 `ModeName` / `ModeConfig`。
  - 新增 `create_mode_adapter(...)`，统一从配置创建 `PrintMode` 或 `RpcMode`。
  - 新增 `run_mode(...)`，统一走 `ModeAdapter.start(...)`。
  - CLI 默认运行路径已收敛到 `run_mode(...)`。
  - 保留既有 `run_print_mode(...)` / `run_rpc_mode(...)` 以及 CLI 注入参数作为兼容入口。
- 该批改动通过相关测试：
  - `tests/coding/test_extension_runner.py`
  - `tests/coding/test_agent_session_compaction.py`
  - `tests/coding/test_agent_session_branch_summary.py`
  - `tests/coding/test_print_mode.py`
  - `tests/coding/test_rpc_mode.py`
  - `tests/coding/test_cli.py`

### 当前估算调整（非 TUI）

- `extensions` 与 pi 对齐率从约 **40%** 提升到约 **55%**：
  - 已补运行时绑定、refresh、UI request、session control hooks、tree/compact/fork typed result。
  - 仍缺完整生命周期诊断分层、extension command context 的更细粒度 PI 行为、更多 UI/runtime hook 覆盖。
- `mode` 规划完成率从旧口径 **0%** 调整为约 **70%**：
  - `ModeAdapter`、`ModeState`、`ModeConfig`、`create_mode_adapter`、`run_mode` 已落地。
  - `print/json/rpc` 已纳入统一 adapter plane。
  - 仍缺 interactive/TUI 接入前的更完整 action/state contract。
- 总体规划完成率粗估从 **69.9%** 提升到约 **74%**。
- 总体与 pi 对齐率粗估从 **70.7%** 提升到约 **74%**。

### 下一步建议

1. 补 `compaction` 的 `compact_session / maybe_compact_after_turn / get_status` 服务面。
2. 开始 `method / skill / plugin` 中最基础的 resource-to-command/method 注册闭环。
3. 继续细化 `mode` 的 action/state contract，为后续 interactive/TUI 接入预留稳定边界。

## 2026-05-01 更新（compaction service 面）

- 2026-05-01 继续补齐 `compaction` 基础服务边界：
  - 新增 `CompactionStatus`。
  - 新增 `CompactionCoordinator`。
  - `CompactionCoordinator.compact_session(...)` 统一调度 session 压缩。
  - `CompactionCoordinator.maybe_compact_after_turn(...)` 统一调度 turn-end 自动压缩检查。
  - `CompactionCoordinator.get_status()` 暴露 in-progress、last reason/result/error 等状态。
  - `AgentSession` 新增公开 `compact_session(...)`、`maybe_compact_after_turn(...)`、`get_compaction_status()`，减少外部调用私有 `_check_auto_compaction` 的需要。
- 该批改动通过相关测试：
  - `tests/coding/test_compaction_service.py`
  - `tests/coding/test_agent_session_compaction.py`
  - `tests/coding/test_branch_summarization.py`
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_agent_session_runtime.py`

### 当前估算调整（非 TUI）

- `compaction` 规划完成率从约 **50%** 提升到约 **75%**：
  - 准备、压缩、自动压缩触发、状态查询、branch summary 已有基础服务面。
  - 仍缺更完整的 abort signal wiring、独立 `CompactionArtifact` 命名对象、以及把更多 AgentSession 内部压缩逻辑下沉到 coordinator。
- 总体规划完成率粗估从约 **74%** 提升到约 **75%**。
- 总体与 pi 对齐率粗估从约 **74%** 提升到约 **75%**。

### 下一步建议

1. 开始 `method / skill / plugin` 中最基础的 resource-to-command/method 注册闭环。
2. 继续把 `CompactionCoordinator` 接入 `AgentSession` 构造链路，让 coordinator 不只是可用服务，而是默认运行路径的一部分。
3. 补 diagnostics startup check / error normalization 的统一入口。

## 2026-05-01 更新（skill / plugin P0）

- 2026-05-01 先补 `skill` 与 `plugin`，暂不推进 `method`：
  - 新增 `SkillLoader`，作为 skill-specific facade 复用现有 `DefaultResourceLoader` 的 `skills/*/SKILL.md` 解析规则。
  - `SkillLoader` 支持 `discover_skills / load_skill / reload_skills / get_skill / list_skills / list_enabled_skills / enable_skill / disable_skill`。
  - 新增 `PluginManifest` / `PluginSource` / `InstalledPlugin` / `PluginResolvedResources`。
  - 新增 `PluginResolver`，P0 支持本地目录 plugin，读取 `plugin.json`，解析为 resource-loader 可消费的 `package_roots`。
  - 新增 `PluginRegistry` 与 `PluginManager`，支持 source add/remove、enable/disable、refresh、list/get/resolve。
  - `PluginManager.resolve_package_roots()` 可直接传给 `DefaultResourceLoader(package_roots=...)`，让 plugin 中的 skills/prompts/extensions/themes 进入现有资源平面。
- 该批改动通过相关测试：
  - `tests/coding/test_skill_loader.py`
  - `tests/coding/test_plugin_manager.py`

### 当前估算调整（非 TUI）

- `skill` 规划完成率从 **0%** 提升到约 **55%**：
  - 已有独立 loader facade、发现、查询、启停。
  - 仍缺更完整的 metadata schema、可见性策略持久化、CLI/SDK 管理入口。
- `plugin` 规划完成率从 **0%** 提升到约 **45%**：
  - 已有本地 source、manifest、registry、manager、resolver、resource roots 展开。
  - 仍缺远程/source catalog、安装/卸载、持久化 registry、版本与冲突策略。
- 总体规划完成率粗估从约 **75%** 提升到约 **78%**。
- 总体与 pi 对齐率粗估从约 **75%** 提升到约 **78%**。

### 下一步建议

1. 把 `PluginManager.resolve_package_roots()` 接进 settings/bootstrap，使配置里的 plugin sources 可以自动进入 resource loader。
2. 给 `SkillLoader` / `PluginManager` 增加 CLI breadth（list/enable/disable）或 SDK 入口。
3. 再评估是否需要开始 `method`，还是先补 diagnostics startup check。

## 2026-05-01 更新（plugin sources 接入 bootstrap）

- 2026-05-01 继续把 `plugin` P0 接进默认装配路径：
  - `ControlConfig` 新增 `plugin_sources`。
  - `SettingsManager` 支持读取、合并、更新、持久化 `plugin_sources`。
  - `create_agent_session(...)` 会将 `settings.package_roots` 与 `settings.plugin_sources` 解析出的 package roots 合并后传给 `DefaultResourceLoader`。
  - 配置里的本地 plugin source 现在可以自动展开 prompts/skills/extensions/themes 到现有资源平面。
- 该批改动通过相关测试：
  - `tests/coding/test_settings_manager.py`
  - `tests/coding/test_bootstrap.py`
  - `tests/coding/test_plugin_manager.py`

### 当前估算调整（非 TUI）

- `plugin` 规划完成率从约 **45%** 提升到约 **55%**：
  - plugin source 已进入 settings/bootstrap 默认路径。
  - 仍缺 CLI/SDK 管理入口、持久化 registry、远程 source 与版本/冲突策略。
- 总体规划完成率粗估从约 **78%** 提升到约 **79%**。
- 总体与 pi 对齐率粗估从约 **78%** 提升到约 **79%**。

### 下一步建议

1. 给 `SkillLoader` / `PluginManager` 增加 CLI breadth（list/enable/disable 或 list-only 起步）。
2. 补 diagnostics startup check / error normalization 的统一入口。
3. 再评估是否需要开始 `method`。

## 2026-05-01 更新（skill / plugin CLI breadth）

- 2026-05-01 继续补 `skill` 与 `plugin` 的只读 CLI surface：
  - 新增 `--list-skills`。
  - 新增 `--list-skills-format tsv|json`。
  - 新增 `--list-plugins`。
  - 新增 `--list-plugins-format tsv|json`。
  - `--list-skills` 从当前 session/resource bundle 读取已解析 skill descriptors。
  - `--list-plugins` 从 settings `plugin_sources` 解析本地 plugin manifests。
- 该批改动通过相关测试：
  - `tests/coding/test_cli.py`
  - `tests/coding/test_skill_loader.py`
  - `tests/coding/test_plugin_manager.py`

### 当前估算调整（非 TUI）

- `skill` 规划完成率从约 **55%** 提升到约 **60%**：
  - skill 已有 loader facade 与 CLI list surface。
  - 仍缺 CLI enable/disable 持久化、metadata schema、选择策略。
- `plugin` 规划完成率从约 **55%** 提升到约 **60%**：
  - plugin 已有 settings/bootstrap 接入与 CLI list surface。
  - 仍缺 add/remove/enable/disable CLI/SDK 管理入口、持久化 registry、版本策略。
- 总体规划完成率粗估从约 **79%** 提升到约 **80%**。
- 总体与 pi 对齐率粗估从约 **79%** 提升到约 **80%**。

### 下一步建议

1. 补 diagnostics startup check / error normalization 的统一入口。
2. 给 plugin/skill 增加持久化 enable/disable 管理入口。
3. 再评估是否开始 `method`。

## 2026-05-01 更新（diagnostics startup/error 基础面）

- 2026-05-01 继续补 `diagnostics` 的 startup check 与 error normalization 入口：
  - 新增 `StartupCheckResult` 与 `StartupCheck`。
  - `DiagnosticsService.normalize_error(...)` 作为 `normalize_exception(...)` 的更通用别名入口。
  - `DiagnosticsService.capture_failure(...)` 统一完成 error normalize + record。
  - `DiagnosticsService.normalize_startup_check_result(...)` 将启动检查结果投影为 `DiagnosticRecord`。
  - `DiagnosticsService.run_startup_checks(...)` 统一执行启动检查，并把检查异常稳定记录为 `startup_check_exception`。
  - `DiagnosticSource` 补齐 `diagnostics/provider/model/agent`，为 provider/model/agent 错误投影预留稳定来源。
- 该批改动通过相关测试：
  - `tests/coding/test_diagnostics_service.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **40%** 提升到约 **70%**：
  - startup check 执行入口、启动检查结果对象、错误归一化与失败捕获已落地。
  - 仍缺更深的 bootstrap 默认 startup checks 接入，以及 provider/model/tool 结果到 diagnostics 的完整事件投影。
- `diagnostics` 与 pi 对齐率从约 **60%** 提升到约 **75%**：
  - 已具备 pi 风格的启动检查与错误归一化基础面。
  - 差距主要是运行时错误事实投影粒度和启动检查清单丰富度。
- 总体规划完成率粗估从约 **80%** 提升到约 **81%**。
- 总体与 pi 对齐率粗估从约 **80%** 提升到约 **81%**。

### 下一步建议

1. 把 diagnostics startup checks 接入 bootstrap 默认路径，先覆盖 cwd/session/model/plugin/resource 基础检查。
2. 补 provider/model/tool result 到 diagnostics 的事件投影，减少各处手工记录。
3. 给 plugin/skill 增加持久化 enable/disable 管理入口。

## 2026-05-01 更新（diagnostics bootstrap 接入）

- 2026-05-01 继续把 diagnostics startup check 接进 `bootstrap` 默认路径：
  - `create_agent_session(...)` 启动时执行 cwd/package root 基础检查。
  - cwd 不可用记录 `cwd_unavailable` warning，不阻断 session 创建。
  - package root 不可用记录 `package_root_unavailable` warning，不阻断 session 创建。
  - plugin source 解析失败记录 `plugin_source_unresolved` warning，并跳过坏 plugin source，保留其它 package/plugin resource 继续加载。
  - bootstrap 内部复用 `DiagnosticsService.run_startup_checks(...)` 与 `capture_failure(...)`，避免新增旁路诊断格式。
- 该批改动通过相关测试：
  - `tests/coding/test_bootstrap.py`
  - `tests/coding/test_diagnostics_service.py`
  - `tests/coding/test_plugin_manager.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **70%** 提升到约 **75%**：
  - startup check 不再只是服务面，已进入默认 session bootstrap。
  - 仍缺模型 auth 从 session 内部记录迁移到统一 startup/runtime check plane，以及 provider/tool 事件投影。
- `diagnostics` 与 pi 对齐率从约 **75%** 提升到约 **78%**：
  - 启动前检查和坏配置容错更接近 pi 的 startup diagnostics 语义。
  - 差距主要是诊断检查清单深度和 runtime error projection。
- 总体规划完成率粗估从约 **81%** 提升到约 **82%**。
- 总体与 pi 对齐率粗估从约 **81%** 提升到约 **82%**。

### 下一步建议

1. 补 provider/model/tool result 到 diagnostics 的事件投影，减少各处手工记录。
2. 给 plugin/skill 增加持久化 enable/disable 管理入口。
3. 继续收敛 mode/action state contract，准备后续 interactive/TUI 接入。

## 2026-05-01 更新（diagnostics runtime 投影）

- 2026-05-01 继续补 `diagnostics` 的 runtime error projection：
  - `AgentSession` 在 `tool_execution_end` 且 `is_error=True` 时记录 `tool_execution_failed`。
  - tool error 诊断使用 `source="tool"`，并带上 `tool_call_id` 与 `tool_name`。
  - tool error message 优先从 tool result text content 提取，缺失时回退 details/error/message/stderr。
  - model auth 诊断从 `source="session"` 收到 `source="model"`。
  - extension command failure 与通用 runtime exception 改走 `capture_failure(...)`，减少手工 normalize + record 旁路。
- 该批改动通过相关测试：
  - `tests/coding/test_bootstrap.py`
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_tool_registry.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **75%** 提升到约 **78%**：
  - 已覆盖 startup check、bootstrap 接入、tool runtime error projection、model source 细化。
  - 仍缺 provider/model assistant error 的一等投影，以及更多错误码/诊断级别策略。
- `diagnostics` 与 pi 对齐率从约 **78%** 提升到约 **80%**：
  - 运行期错误事实开始从 event surface 投影，而不是只依赖局部组件手工写入。
  - 差距主要是 provider/model streaming error 与 UI 可展示诊断聚合。
- 总体规划完成率粗估从约 **82%** 提升到约 **83%**。
- 总体与 pi 对齐率粗估从约 **82%** 提升到约 **83%**。

### 下一步建议

1. 补 assistant stop_reason=error 的 provider/model diagnostics 投影。
2. 给 plugin/skill 增加持久化 enable/disable 管理入口。
3. 继续收敛 mode/action state contract。

## 2026-05-01 更新（assistant provider error 投影）

- 2026-05-01 继续补 `diagnostics` 的 assistant error projection：
  - `AgentSession` 在 `agent_end` 中检测最后一条 assistant message。
  - 当 `stop_reason="error"` 且存在 `error_message` 时记录 `assistant_response_error`。
  - 诊断使用 `source="provider"`，details 带 `provider/model_id/api/response_id/stop_reason`。
  - 记录发生在 retry 判定之前；如果后续 retry 最终失败，`retry_failed` 仍会作为最后主错误。
- 该批改动通过相关测试：
  - `tests/coding/test_agent_session_retry.py`
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_bootstrap.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **78%** 提升到约 **80%**：
  - startup、bootstrap、tool runtime error、assistant provider error、model auth source 已有统一投影。
  - 仍缺更完整的诊断聚合视图、错误去重/关联策略、以及 UI/CLI 展示策略。
- `diagnostics` 与 pi 对齐率从约 **80%** 提升到约 **82%**：
  - provider/model 运行期错误不再只停留在 assistant message 内，而是进入统一 diagnostics 面。
  - 差距主要是更细的 provider error 分类、可恢复建议和前端展示。
- 总体规划完成率粗估从约 **83%** 提升到约 **84%**。
- 总体与 pi 对齐率粗估从约 **83%** 提升到约 **84%**。

### 下一步建议

1. 给 plugin/skill 增加持久化 enable/disable 管理入口。
2. 继续收敛 mode/action state contract。
3. 补 diagnostics 去重/关联策略，避免 retry 场景下 provider error 过多。

## 2026-05-01 更新（skill/plugin 持久化启停）

- 2026-05-01 继续补 `skill` / `plugin` 管理入口：
  - `ControlConfig` 新增 `disabled_skills` 与 `disabled_plugins`。
  - `SettingsManager` 支持读取、合并、持久化 disabled skill/plugin 清单。
  - `SettingsManager` 新增 `enable_skill/disable_skill/enable_plugin/disable_plugin`。
  - `create_agent_session(...)` 读取 disabled skill/plugin 配置并在 bootstrap resource 装配时生效。
  - disabled plugin 不再展开 package roots。
  - disabled skill 仍保留在 resource bundle 中用于可见性，但 `enabled=False`，preflight 不再匹配。
  - `SkillLoader` / `PluginManager` 支持初始化 disabled 清单。
  - CLI 新增 `--enable-skill` / `--disable-skill` / `--enable-plugin` / `--disable-plugin`，默认持久化到 project settings。
- 该批改动通过相关测试：
  - `tests/coding/test_settings_manager.py`
  - `tests/coding/test_bootstrap.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_skill_loader.py`
  - `tests/coding/test_plugin_manager.py`

### 当前估算调整（非 TUI）

- `skill` 规划完成率从约 **60%** 提升到约 **70%**：
  - 已有 loader facade、发现、查询、启停、持久化 disabled 清单与 CLI 管理入口。
  - 仍缺更完整 metadata schema、skill 选择/推荐策略、以及更丰富的 SDK 管理面。
- `plugin` 规划完成率从约 **60%** 提升到约 **70%**：
  - 已有 settings/bootstrap 接入、list surface、持久化 disabled 清单与 CLI 管理入口。
  - 仍缺 add/remove CLI、远程安装、版本/冲突策略、plugin catalog。
- 总体规划完成率粗估从约 **84%** 提升到约 **85%**。
- 总体与 pi 对齐率粗估从约 **84%** 提升到约 **85%**。

### 下一步建议

1. 补 plugin add/remove CLI 与 settings 持久化 source 管理。
2. 继续收敛 mode/action state contract。
3. 补 diagnostics 去重/关联策略。

## 2026-05-01 更新（plugin source 管理 CLI）

- 2026-05-01 继续补 `plugin` source 管理入口：
  - `SettingsManager` 新增 `add_plugin_source(...)` 与 `remove_plugin_source(...)`。
  - CLI 新增 `--add-plugin-source` / `--remove-plugin-source`。
  - CLI 额外提供短别名 `--add-plugin` / `--remove-plugin`，当前语义仍是本地 plugin source 管理，不做远程安装。
  - add/remove plugin source 默认持久化到 project settings。
  - plugin source 管理与 `enable/disable plugin` 共用同一 settings 管理面。
- 该批改动通过相关测试：
  - `tests/coding/test_settings_manager.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_plugin_manager.py`
  - `tests/coding/test_bootstrap.py`

### 当前估算调整（非 TUI）

- `plugin` 规划完成率从约 **70%** 提升到约 **75%**：
  - source list/add/remove、enable/disable、bootstrap 展开、CLI list surface 已有基础闭环。
  - 仍缺远程安装、版本/冲突策略、plugin catalog、签名/安全策略。
- 总体规划完成率粗估从约 **85%** 提升到约 **86%**。
- 总体与 pi 对齐率粗估从约 **85%** 提升到约 **86%**。

### 下一步建议

1. 继续收敛 mode/action state contract。
2. 补 diagnostics 去重/关联策略。
3. 评估是否启动 `method` 基础 registry。

## 2026-05-01 更新（mode action contract）

- 2026-05-01 继续补 `mode` action/state contract：
  - 新增 `ModeActionType`。
  - 新增 `ModeAction`，作为驱动 mode adapter 的轻量 action 对象。
  - 新增 `dispatch_mode_action(...)`，统一派发 `start/stop/submit_input/render_event/get_state`。
  - `ModeAction` / `dispatch_mode_action` 已从 `loushang.coding.mode` 和顶层 `loushang.coding` 导出。
  - 不改变 `PrintMode` / `RpcMode` 原有运行路径，只补 interactive/TUI 前可复用的 action plane。
- 该批改动通过相关测试：
  - `tests/coding/test_print_mode.py`
  - `tests/coding/test_rpc_mode.py`
  - `tests/coding/test_cli.py`

### 当前估算调整（非 TUI）

- `mode` 规划完成率从约 **70%** 提升到约 **78%**：
  - adapter、config、state、run entry、action dispatch 已有稳定骨架。
  - 仍缺 interactive/TUI 具体 adapter、更多 action 类型、以及 mode 自身事件/状态 reducer。
- 总体规划完成率粗估从约 **86%** 提升到约 **87%**。
- 总体与 pi 对齐率粗估从约 **86%** 提升到约 **87%**。

### 下一步建议

1. 补 diagnostics 去重/关联策略。
2. 评估是否启动 `method` 基础 registry。
3. 继续扩展 mode action 类型，但不进入 TUI 实现。

## 2026-05-01 更新（diagnostics 去重/关联）

- 2026-05-01 继续补 `diagnostics` 的 dedupe / correlation 基础策略：
  - `DiagnosticRecord` 新增 `fingerprint`。
  - `DiagnosticRecord` 新增 `occurrence_count`。
  - `DiagnosticsService.record(...)` 为记录生成稳定 fingerprint。
  - 同一 session 内相同 type/code/message/phase/source/source_path/details 的重复诊断会合并。
  - 合并后的诊断保留一条记录，并累加 `occurrence_count`。
  - `ErrorReport.related` 输出去重后的相关诊断，减少 retry/provider error 重复刷屏。
  - `capture_failure(...)` 返回实际存储后的诊断对象，便于调用方读取 fingerprint / occurrence count。
- 该批改动通过相关测试：
  - `tests/coding/test_diagnostics_service.py`
  - `tests/coding/test_agent_session_retry.py`
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_bootstrap.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **80%** 提升到约 **84%**：
  - startup、bootstrap、runtime projection、provider/model/tool source、dedupe、related correlation 均已有基础能力。
  - 仍缺更细错误分类、恢复建议、以及 CLI/RPC 可展示的诊断摘要面。
- `diagnostics` 与 pi 对齐率从约 **82%** 提升到约 **85%**：
  - retry/provider error 场景更接近稳定 UI diagnostics，而不是重复事件日志。
- 总体规划完成率粗估从约 **87%** 提升到约 **88%**。
- 总体与 pi 对齐率粗估从约 **87%** 提升到约 **88%**。

### 下一步建议

1. 补 CLI/RPC diagnostics summary surface。
2. 评估并启动 `method` 基础 registry。
3. 继续扩展 mode action 类型，但不进入 TUI 实现。

## 2026-05-01 更新（diagnostics query surface）

- 2026-05-01 继续补 `diagnostics` 的 CLI/RPC 查询面：
  - 新增 `serialize_diagnostic(...)`，统一将 `DiagnosticRecord` 投影为 JSON-safe camelCase payload。
  - 新增 `serialize_error_report(...)`，统一输出 `primary` / `related` 错误报告。
  - CLI 新增 `--list-diagnostics`。
  - CLI 新增 `--list-diagnostics-format tsv|json`。
  - CLI 新增 `--diagnostics-limit`，并对非正数返回稳定 CLI 错误。
  - RPC 新增 `get_diagnostics` command，支持 `limit`。
  - RPC 新增 `get_last_error_report` command。
- 该批改动通过相关测试：
  - `tests/coding/test_diagnostics_service.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **84%** 提升到约 **88%**：
  - 诊断采集、去重、错误报告、CLI 查询、RPC 查询已有基础闭环。
  - 仍缺更细错误分类、恢复建议、UI 分组策略、以及跨 session 诊断索引。
- `diagnostics` 与 pi 对齐率从约 **85%** 提升到约 **89%**：
  - 已从内部 service 能力推进到可被 headless host/CLI 稳定消费的 diagnostics surface。
- 总体规划完成率粗估从约 **88%** 提升到约 **89%**。
- 总体与 pi 对齐率粗估从约 **88%** 提升到约 **89%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（runtime session prefix lookup）

- 2026-05-01 继续补 `runtime/store` 与 `pi` 的 session lookup 语义：
  - `AgentSessionRuntime.restore_session(...)` / `switch_session(...)` 在 path 和完整 session id 之外，支持 session id prefix。
  - prefix 唯一匹配时恢复对应 session。
  - prefix 多匹配时抛出稳定 `Ambiguous session reference`，由 CLI/RPC 统一收口。
- 该批改动通过：
  - `tests/coding/test_agent_session_runtime.py`
  - `tests/coding`

### 当前估算调整（非 TUI）

- `runtime/store` 与 pi 对齐率从约 **90%** 提升到约 **91%**：
  - session restore lookup 更接近 pi CLI/runtime 的短 ID 使用方式。
- 总体与 pi 对齐率粗估维持约 **91%**。

### 下一步建议

1. 继续补 `store/session` 的跨 session/global listing 辅助面。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（store/runtime all-session lookup）

- 2026-05-01 继续补 `store/session` 与 `pi` 的跨 session 查询面：
  - `SessionManager.list_all_summaries(root)` 聚合 sessions root 下直接 JSONL 与一层 project/session 子目录。
  - `SessionManager.find_all_sessions(root, query)` 复用统一 summary filter。
  - `AgentSessionRuntime.list_all_session_summaries()` / `find_all_session_summaries(query)` 以当前 `session_dir.parent` 作为 sessions root 透出该能力。
- 该批改动通过：
  - `tests/coding/test_agent_session_runtime.py`

### 当前估算调整（非 TUI）

- `store/session` 与 pi 对齐率从约 **91%** 提升到约 **93%**：
  - 补齐跨 project/session dir 的 summary lookup 基础能力。
- `runtime/store` 与 pi 对齐率从约 **91%** 提升到约 **92%**：
  - runtime 不再只限定当前 session_dir 查询。
- 总体与 pi 对齐率粗估从约 **91%** 提升到约 **92%**。

### 下一步建议

1. 将 all-session lookup 接入 CLI/RPC 的 list/search commands。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（CLI/RPC all-session lookup surface）

- 2026-05-01 将上一批 `runtime/store` all-session lookup 接到对外入口：
  - CLI 新增 `--all-sessions`，与 `--list-sessions` 配合使用。
  - CLI 默认仍使用当前 session dir；`--all-sessions` 时优先调用 runtime `list_all_session_summaries()`。
  - RPC `list_sessions` 支持 `allSessions` / `all_sessions` boolean。
  - RPC `allSessions=true` 时优先调用 runtime `find_all_session_summaries(query)`，并保留现有 filters。
- 该批改动通过：
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `CLI/RPC session listing` 与 pi 对齐率从约 **90%** 提升到约 **93%**：
  - 当前项目 session listing 与跨项目/all-session lookup 都已有稳定入口。
- 总体与 pi 对齐率粗估维持约 **92%**。

### 下一步建议

1. 继续补 CLI session listing filters，减少与 RPC 查询能力的差距。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（CLI session listing filters）

- 2026-05-01 补齐 CLI `--list-sessions` 与 RPC `list_sessions` 的过滤能力：
  - 新增 `--session-cwd`。
  - 新增 `--session-name-filter`。
  - 新增 `--session-parent`。
  - 新增 `--session-query`。
  - 新增 `--session-limit`，负数会稳定返回 CLI error。
  - 普通列表调用 runtime `find_session_summaries(SessionQuery)`；`--all-sessions` 调用 `find_all_session_summaries(SessionQuery)`。
- 该批改动通过：
  - `tests/coding/test_cli.py`

### 当前估算调整（非 TUI）

- `CLI/RPC session listing` 与 pi 对齐率从约 **93%** 提升到约 **95%**：
  - CLI 与 RPC 的 session 查询参数能力基本一致。
- 总体与 pi 对齐率粗估维持约 **92%**。

### 下一步建议

1. 回到 `mode` action/adapter contract，补齐非 TUI mode lifecycle 的剩余薄层。
2. 继续补 runtime/session lifecycle diagnostics 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（mode lifecycle action contract）

- 2026-05-01 补齐非 TUI mode adapter 的薄生命周期 action：
  - `ModeActionType` 新增 `wait_for_idle`。
  - `ModeActionType` 新增 `rebind_session`。
  - `ModeActionType` 新增 `dispose`。
  - `dispatch_mode_action(...)` 统一派发这些生命周期动作。
  - `PrintMode` / `RpcMode` 实现 `wait_for_idle()`、`rebind_session()`、`dispose()`，只委托当前 session/runtime。
- 该批改动通过：
  - `tests/coding/test_print_mode.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `mode` 与 pi 对齐率从约 **78%** 提升到约 **82%**：
  - mode adapter contract 已覆盖非 TUI start/stop/input/state/event/wait/rebind/dispose 主生命周期。
- 总体与 pi 对齐率粗估维持约 **92%**。

### 下一步建议

1. 继续补 runtime/session lifecycle diagnostics 查询。
2. 评估 RPC shutdown/exit command 是否需要对齐 pi。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（session-scoped diagnostics query）

- 2026-05-01 补齐 session/runtime diagnostics 查询边界：
  - `AgentSession.get_session_diagnostics(query?)` 默认限定当前 `sessionId`。
  - `AgentSessionRuntime.get_session_diagnostics(query?)` 默认限定 current session。
  - 原有 `get_diagnostics(query?)` 保留为 diagnostics service/global 查询面。
  - 2026-05-01 后续收瘦：不保留 `getSessionDiagnostics` camelCase alias，避免非 pi 核心 API 重复暴露造成调用混乱。
- 该批改动通过：
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_agent_session_runtime.py`

### 当前估算调整（非 TUI）

- `diagnostics/runtime` 与 pi 对齐率从约 **91%** 提升到约 **92%**：
  - runtime/service 全局 diagnostics 与 current-session diagnostics 查询边界更清晰。
- 总体与 pi 对齐率粗估维持约 **92%**。

### 下一步建议

1. 评估 RPC 是否需要暴露 `get_session_diagnostics`，与现有 `get_diagnostics` 区分。
2. 评估 RPC shutdown/exit command 是否需要对齐 pi。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（pi-style session SDK breadth）

- 2026-05-01 继续补 `AgentSession` 与 `pi-coding-agent` 的直接 SDK 调用面：
  - 新增 `getSessionStats()`，从当前消息流统计 user/assistant/tool/tokens/cost/context。
  - 新增 `scopedModels` / `setScopedModels()`，并让 scoped models 参与 `cycleModel()`。
  - 新增 `promptTemplates` / `resourceLoader` 查询面，直接投影 loader/resource bundle。
  - 新增 `isRetrying`、`autoRetryEnabled`、`setAutoRetryEnabled()`、`setAutoCompactionEnabled()`。
  - 新增 `executeBash()`、`recordBashResult()`、`abortBash()`、`isBashRunning`、`hasPendingBashMessages`、`abortCompaction()`。
- 该批改动通过：
  - `tests/coding/test_agent_session.py`
  - `tests/coding`

### 当前估算调整（非 TUI）

- `session` 与 pi 对齐率从约 **90%** 提升到约 **93%**：
  - 直接 SDK surface 已覆盖 pi 非交互主调用面的大多数查询、mutator、queue、model、thinking、resource、retry、bash、stats/export。
- `runtime/session facade` 与 pi 对齐率从约 **87%** 提升到约 **90%**：
  - mode/RPC/extension 不再需要自行拼接这些 session 状态和动作。
- 总体与 pi 对齐率粗估从约 **90%** 提升到约 **91%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（pi-style slash command surface）

- 2026-05-01 继续按 `pi` 的 slash command 方式收口命令面：
  - 不引入独立 `CommandRegistry` / `SlashCommandRegistry` class。
  - `AgentSession.list_commands()` 继续作为 session-level aggregation surface，动态聚合 extension / prompt / skill。
  - `ExtensionRunner` 继续负责 extension command 注册、去重和 invocation name。
  - `commands.types` 新增 `SlashCommandSource`、`SlashCommandInfo`、`BuiltinSlashCommand` 与 `BUILTIN_SLASH_COMMANDS`。
  - `commands.slash` 新增 `parse_slash_command(...)` 与 `split_slash_command(...)`，统一 slash input parsing。
  - `prompt.preflight` 与 `AgentSession` 的 extension command preflight 复用同一 parser，避免重复 split 逻辑。
- 该批改动通过相关测试：
  - `tests/coding/test_commands.py`
  - `tests/coding/test_prompt_assembly.py`
  - `tests/coding/test_agent_session.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `commands/session command surface` 与 pi 对齐率从约 **90%** 提升到约 **93%**：
  - 类型、builtin slash list、parse helper 与 session aggregation 边界更接近 pi。
  - 明确不采用 cc-style global command registry，避免 MVP 阶段引入过重 command object 体系。
- 总体与 pi 对齐率粗估从约 **90%** 提升到约 **91%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到最后批次。

## 2026-05-01 更新（store/session cross-session read model）

- 2026-05-01 继续补 `store/session` 核心底座：
  - 新增 `SessionSummary`，作为跨 session read model。
  - 新增 `SessionQuery`，统一表达 cwd、name、parent session、text、limit 查询条件。
  - `SessionManager.get_session_summary()` 从当前 active branch context 派生 message count、last message preview 与 model。
  - `SessionManager.list_summaries(...)` 统一扫描 session store，跳过损坏或 export 文件。
  - `SessionManager.load_summary(...)` 提供单文件 summary 读取。
  - `SessionManager.find_sessions(...)` 提供上层 mode/RPC/CLI 可复用的只读查询面。
- 该批改动通过相关测试：
  - `tests/coding/test_session_manager.py`

### 当前估算调整（非 TUI）

- `store` 规划完成率从约 **86%** 提升到约 **90%**：
  - 单 session 持久化、恢复、branch/fork、context rebuild 之外，补上跨 session summary/query 基础面。
- `session/store` 与 pi 对齐率从约 **88%** 提升到约 **91%**：
  - 更接近 pi 中 SessionManager 同时承担会话文件管理和历史会话查询 read model 的定位。
- 总体与 pi 对齐率粗估从约 **92%** 提升到约 **93%**。

### 下一步建议

1. 将 `SessionSummary` 接入 RPC `list_sessions` / `get_state` 相关输出。
2. 基于 summary/query 补 diagnostics 的跨 session last error index。
3. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。

## 2026-05-01 更新（session summary runtime and RPC surface）

- 2026-05-01 将 `SessionSummary` 接入上层消费面：
  - `AgentSessionRuntime` 新增 `list_session_summaries()`。
  - CLI `--list-sessions` 优先消费 `list_session_summaries()`，并兼容旧 `list_sessions()`。
  - CLI JSON 输出在旧 `SessionRecord` 字段之外，支持 `message_count`、`entry_count`、`last_message_preview`、`model`。
  - RPC mode 新增 `list_sessions` command，优先消费 runtime summary，并输出 camelCase payload。
  - `list_sessions()` 旧契约暂时保留给 resume/continue 等路径，避免破坏旧调用方。
- 该批改动通过相关测试：
  - `tests/coding/test_agent_session_runtime.py`
  - `tests/coding/test_session_manager.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `runtime/store` 规划完成率从约 **90%** 提升到约 **92%**：
  - store summary 已进入 runtime 与 headless adapter 查询面。
- `RPC/mode` 与 pi 对齐率从约 **84%** 提升到约 **86%**：
  - RPC session listing 不再需要宿主自己扫 session files。
- 总体与 pi 对齐率粗估维持约 **93%**，跨 session 查询面更完整。

### 下一步建议

1. 基于 summary/query 补 diagnostics 的跨 session last error index。
2. 将 `list_sessions` 的 filtering 参数接到 `SessionQuery`。
3. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。

## 2026-05-01 更新（RPC session query filters）

- 2026-05-01 继续补 session summary 查询面：
  - `AgentSessionRuntime` 新增 `find_session_summaries(query)`。
  - RPC `list_sessions` 支持 `cwd`、`name`、`parentSession` / `parent_session`、`text` / `query`、`limit`。
  - RPC 过滤参数统一转成 `SessionQuery`，避免 RPC 自己实现 session file 扫描逻辑。
  - `limit` 必须是非负整数，非法输入返回稳定 RPC error。
  - 无 `find_session_summaries` 的旧 runtime 仍回退到 `list_session_summaries()` / `list_sessions()`。
- 该批改动通过相关测试：
  - `tests/coding/test_agent_session_runtime.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `runtime/store` 规划完成率从约 **92%** 提升到约 **93%**：
  - summary query 已成为 runtime 一等查询面。
- `RPC/mode` 与 pi 对齐率从约 **86%** 提升到约 **87%**：
  - headless host 可直接按条件查询 session summary。
- 总体与 pi 对齐率粗估维持约 **93%**。

### 下一步建议

1. 基于 summary/query 补 diagnostics 的跨 session last error index。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 评估是否给 CLI `--list-sessions` 增加同样的过滤参数。

## 2026-05-01 更新（diagnostics query filters）

- 2026-05-01 继续补 diagnostics 查询面：
  - 新增 `DiagnosticsQuery`，统一表达 `phase`、`source`、`level`、`session_id`、`entry_id`、`code`、`limit`。
  - `DiagnosticsService.get_diagnostics(...)` 支持 `DiagnosticsQuery` 与显式过滤参数。
  - `AgentSession.get_diagnostics(query)` 暴露当前 session diagnostics 查询面。
  - `AgentSessionRuntime.get_diagnostics(query)` 暴露 runtime 级 diagnostics 查询面，优先使用共享 diagnostics service。
  - RPC `get_diagnostics` 支持 `sessionId` / `session_id`、`entryId` / `entry_id`、`phase`、`source`、`level` / `diagnosticType` / `diagnostic_type`、`code`、`limit`。
  - RPC 没有 query-capable runtime/session 时仍回退到旧 `get_last_diagnostics(limit)`。
- 该批改动通过相关测试：
  - `tests/coding/test_diagnostics_service.py`
  - `tests/coding/test_agent_session_runtime.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `diagnostics` 规划完成率从约 **88%** 提升到约 **90%**：
  - diagnostics 已从“最近记录”推进到可过滤查询面。
- `diagnostics` 与 pi 对齐率从约 **90%** 提升到约 **91%**：
  - runtime/headless host 可以按 session 与来源筛选错误事实。
- 总体与 pi 对齐率粗估维持约 **93%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 评估是否给 CLI `--list-sessions` 增加过滤参数。
3. 后续若需要真正跨重启的 diagnostics index，应先设计 diagnostics 持久化 entry，而不是从内存 service 伪造。

## 2026-05-01 更新（per-tool execution mode pi alignment）

- 2026-05-01 继续按 `pi-agent` 补 per-tool execution mode：
  - `AgentTool` 明确拥有 `execution_mode` 字段，取值为 `parallel` 或 `sequential`。
  - `ToolDefinition` 与 wrapped tool 同步暴露 `execution_mode`。
  - agent loop 在一个 tool batch 内只要发现任一工具声明 `execution_mode="sequential"`，整批就按顺序执行。
  - 全局 `tool_execution="sequential"` 仍然强制顺序执行。
  - 旧 runtime tool 未声明 `execution_mode` 时，在 agent/registry/extension 边界默认补为 `parallel`，避免把兼容性判断散落到执行路径。
- 该批改动通过相关测试：
  - `tests/agent`
  - `tests/coding`

### 当前估算调整（非 TUI）

- `agent/tool loop` 与 pi 对齐率从约 **94%** 提升到约 **95%**：
  - per-tool sequential override 与 pi 的 batch execution decision 一致。
- `tools` 与 pi 对齐率从约 **90%** 提升到约 **92%**：
  - tool definition / runtime wrapper / registry 对 `execution_mode` 的表达更完整。
- 总体与 pi 对齐率粗估维持约 **92%**，细分工具与 agent loop 完成度提高。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（agent tool terminate semantics）

- 2026-05-01 继续按 `pi-agent` 补 agent/tool loop 基础语义：
  - `AgentToolResult` 新增 `terminate`，默认 `False`。
  - `AfterToolCallResult` 新增 `terminate`，允许 hook 将工具结果标记为终止。
  - agent loop 在一个 tool batch 执行完后，如果所有 finalized tool result 都 `terminate=True`，则在当前 `turn_end` 后直接 `agent_end`。
  - 并行 tool batch 中只要存在一个结果未 terminate，就继续后续 assistant turn。
  - `ToolResultMessage` 不携带 `terminate`，该字段只作为 agent loop 控制信号，保持对模型上下文的消息形状稳定。
- 该批改动通过相关测试：
  - `tests/agent/test_agent_loop.py`
  - `tests/agent/test_public_api.py`

### 当前估算调整（非 TUI）

- `agent/tool loop` 与 pi 对齐率从约 **90%** 提升到约 **92%**：
  - 已补齐 pi 的 tool batch early termination 语义。
- 总体与 pi 对齐率粗估从约 **90%** 提升到约 **91%**。

### 下一步建议

1. 继续补 `after_tool_call` 异常处理对齐 pi：hook 抛错应变成 error tool result，而不是中断整个 loop。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（after tool hook pi alignment）

- 2026-05-01 继续补 `AgentTool` / tool hook 与 `pi-agent` 的一致性：
  - `after_tool_call` 抛异常时，agent loop 不再中断整个 run。
  - hook 异常会被转换为 `ToolResultMessage(is_error=True)`，错误文本进入 tool result content。
  - extension `tool_result` hook 返回的 `AgentToolResult.terminate` 会透传到 `AfterToolCallResult`。
  - session 组合多个 after-tool hooks 时会保留并传递 `terminate`。
- 该批改动通过相关测试：
  - `tests/agent/test_agent_loop.py`
  - `tests/coding/test_extension_runner.py`

### 当前估算调整（非 TUI）

- `agent/tool loop` 与 pi 对齐率从约 **92%** 提升到约 **94%**：
  - after-tool hook 异常处理与 pi 一致，不再让 hook 失败破坏主 agent loop。
- 总体与 pi 对齐率粗估从约 **91%** 提升到约 **92%**。

### 下一步建议

1. 评估 per-tool `execution_mode` 覆写是否需要补齐。
2. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（tool error semantics strict pi alignment）

- 2026-05-01 按 `pi` 的 tool error 语义收口 runtime tool failure：
  - 工具执行失败仍由 agent loop 捕获异常。
  - agent loop 继续生成 `ToolResultMessage(is_error=True)` 并送回模型。
  - `AgentSession` 不再把 `tool_execution_end(is_error=True)` 投影成通用 `tool_execution_failed` diagnostics。
  - built-in `bash` 的 policy / exec / timeout / cancel failure 不再直接写 runtime diagnostics。
  - diagnostics 回到更接近 `pi` 的定位：resource/startup/provider/model/extension 等非普通工具执行结果问题。
- 该批改动通过相关测试：
  - `tests/coding/test_bootstrap.py`
  - `tests/coding/test_tool_registry.py`

### 当前估算调整（非 TUI）

- `tools` 与 pi 对齐率从约 **85%** 提升到约 **90%**：
  - tool failure 主通道与 pi 一致：throw -> error tool result -> model。
- `diagnostics` 与 pi 对齐率从约 **89%** 调整到约 **90%**：
  - 移除了 runtime tool failure 的重复 diagnostics 投影，更接近 pi 的 resource diagnostics 定位。
  - diagnostics 的查询面仍是 loushang 增强能力，不影响 pi 主语义。
- 总体与 pi 对齐率粗估从约 **89%** 提升到约 **90%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（RPC session diagnostics facade）

- 2026-05-01 继续按 session/runtime 分层收口 RPC diagnostics 查询面：
  - RPC 新增 `get_session_diagnostics` command。
  - `get_session_diagnostics` 复用 `get_diagnostics` 的过滤字段，但优先调用 `AgentSessionRuntime.get_session_diagnostics(query)` 或 `AgentSession.get_session_diagnostics(query)`。
  - `get_diagnostics` 保持 runtime/global diagnostics 查询语义；`get_session_diagnostics` 明确为 current-session scoped 查询语义。
  - 不新增 camelCase Python alias，避免 `get_session_diagnostics` / `getSessionDiagnostics` 双入口造成调用混乱。
- 该批改动通过相关测试：
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `rpc` 与 pi-style session/runtime 分层对齐率从约 **88%** 提升到约 **90%**：
  - diagnostics 查询入口更清楚地区分 global service 查询与 current-session 查询。
- `diagnostics` 与 pi 对齐率维持约 **90%**：
  - 查询能力是 loushang 增强面，但普通 tool failure 主通道仍按 pi 语义走 error tool result。
- 总体与 pi 对齐率粗估维持约 **90%**。

### 下一步建议

1. 继续补 `mode` action 类型和 adapter contract，但不进入 TUI。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（mode action normalization）

- 2026-05-01 继续补 `mode` action/adapter contract：
  - 新增 `normalize_mode_action(...)`，统一把 `ModeAction` dataclass 或 JSON-like dict payload 归一化为 validated `ModeAction`。
  - `dispatch_mode_action(...)` 现在接受 `ModeAction | dict[str, object]`，派发前统一归一化。
  - 不进入 interactive/TUI，只补 CLI/RPC/未来 host 可复用的 mode lifecycle action contract。
- 该批改动通过相关测试：
  - `tests/coding/test_print_mode.py`

### 当前估算调整（非 TUI）

- `mode` 规划完成率从约 **72%** 提升到约 **75%**：
  - adapter lifecycle contract 更稳定，可被 headless host 直接消费。
- `mode` 与 pi-style 边界对齐率从约 **68%** 提升到约 **72%**：
  - 仍不包含 interactive/TUI，但非 TUI action 派发边界更清晰。
- 总体与 pi 对齐率粗估维持约 **90%**。

### 下一步建议

1. 继续补 `mode` action 覆盖面：增加对 session/runtime lifecycle facade 的 action 表达，但不把业务逻辑放入 mode。
2. 补 `store/session` 的跨 session diagnostics/index 查询。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（session diagnostics index metadata）

- 2026-05-01 继续补 `store/session` 的跨 session lookup 基础面：
  - `SessionSummary` 新增轻量 diagnostics index 字段：`has_diagnostics`、`diagnostic_count`、`last_diagnostic_code`、`last_diagnostic_level`。
  - `SessionQuery` 新增 `has_diagnostics` 过滤条件。
  - `SessionManager` 可从 `custom_type="diagnostic" | "diagnostics"` 的 custom entry 汇总 diagnostics metadata。
  - CLI `--list-sessions` 新增 `--session-has-diagnostics` / `--session-no-diagnostics`。
  - RPC `list_sessions` 新增 `hasDiagnostics` / `has_diagnostics` filter。
- 该批改动通过相关测试：
  - `tests/coding/test_session_manager.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `store/session` 规划完成率从约 **86%** 提升到约 **88%**：
  - 跨 session summary/query 已能表达 diagnostics metadata。
- `store/session` 与 pi 对齐率从约 **88%** 提升到约 **90%**：
  - 更接近 pi 的 SessionManager all-session lookup 能力，同时保留 loushang 的 diagnostics 增强索引。
- 总体与 pi 对齐率粗估维持约 **90%**。

### 下一步建议

1. 评估是否需要让 `AgentSession` 在记录关键 runtime diagnostics 时同时写入 lightweight diagnostic metadata entry。
2. 继续补 `mode` action 覆盖面，但避免把 RPC command plane 混进 mode lifecycle。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（pi-style session list/search metadata）

- 2026-05-01 按 pi 的 `SessionInfo` 语义继续补 session list/search：
  - `SessionSummary` 新增 `first_message`，对应 pi 的 `firstMessage`。
  - `SessionSummary` 新增 `all_messages_text`，对应 pi 的 `allMessagesText`。
  - `SessionQuery(text=...)` 现在会搜索 all-message text，不再只依赖 last-message preview 和元信息。
  - `updated_at` 改为优先取 user/assistant message activity timestamp；metadata-only entries 不再把旧 session 顶到最近。
  - CLI JSON 和 RPC `list_sessions` 会透出新增字段；CLI TSV 保持原有列格式。
- 该批改动通过相关测试：
  - `tests/coding/test_session_manager.py`
  - `tests/coding/test_cli.py`
  - `tests/coding/test_rpc_mode.py`

### 当前估算调整（非 TUI）

- `store/session` 与 pi 对齐率从约 **90%** 提升到约 **92%**：
  - session list/search 的核心索引字段与排序语义更贴近 pi。
- 总体与 pi 对齐率粗估从约 **90%** 提升到约 **91%**。

### 下一步建议

1. 继续补 extension command context 的 `newSession` / `fork` / `switchSession` / `withSession` 细节。
2. 继续补 command registry/slash command 执行语义。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（extension replaced context stale hardening）

- 2026-05-01 继续补 pi-style extension command context replacement 语义：
  - `ReplacedSessionContext.sendMessage(...)` 在执行前会检查 context 是否仍属于当前 generation。
  - `ReplacedSessionContext.sendUserMessage(...)` 同样经过 stale-context 检查。
  - session replacement 后，旧 replaced ctx 不能继续写 custom message 或 user message 到旧 session。
- 该批改动通过相关测试：
  - `tests/coding/test_agent_session_runtime.py`

### 当前估算调整（非 TUI）

- `extensions` 与 pi 对齐率从约 **86%** 提升到约 **88%**：
  - replacement 后 stale ctx 防护更接近 pi，减少 extension command 写错 session 的风险。
- 总体与 pi 对齐率粗估维持约 **91%**。

### 下一步建议

1. 继续补 `fork(position="before")` 的边界测试：非 user message 报错、selected text 返回、withSession 新 ctx。
2. 继续补 command registry/slash command 执行语义。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-01 更新（extension fork default before alignment）

- 2026-05-01 继续补 pi-style extension command context fork 语义：
  - `ctx.fork(entryId)` 默认从 `position="before"` fork，与 pi 保持一致。
  - 对 assistant/non-user message 使用 `position="before"` 会抛出稳定错误。
  - 需要 clone/fork 到目标 entry 时必须显式传 `{"position": "at"}`。
  - `ctx.fork(entryId, {"position": "before", "withSession": ...})` 的 `withSession` 会拿到新 fork session 的 fresh context。
- 该批改动通过相关测试：
  - `tests/coding/test_agent_session_runtime.py`

### 当前估算调整（非 TUI）

- `runtime/session/extensions` lifecycle 与 pi 对齐率从约 **88%** 提升到约 **90%**：
  - extension command context 的 fork 默认值、selected text、withSession 语义更贴 pi。
- 总体与 pi 对齐率粗估维持约 **91%**。

### 下一步建议

1. 继续补 command registry/slash command 执行语义。
2. 继续补 extension command context reload / stale behavior 的边界。
3. 将 `method` 基础 registry 放到后续批次。

## 2026-05-02 更新（extension provider/control API facade）

- 2026-05-02 继续补齐 pi-style extension provider 与 runtime API 面：
  - `after_provider_response` 通过 `StreamOptions.on_response` 从 provider 层桥接到 `AgentSession` 和 `ExtensionRunner`。
  - OpenAI Responses、OpenAI Completions、Anthropic provider 已在获得 stream/response 对象后触发 `on_response`。
  - `ExtensionAPI` 可在 extension factory 闭包中读取当前 runtime 状态：`get_commands()`、`get_active_tools()`、`get_all_tools()`、`get_flag(name)`。
  - `ExtensionAPI` 可在 command/hook 闭包中执行 runtime action：`append_entry()`、`send_message()`、`send_user_message()`、`set_session_name()`、`get_session_name()`、`set_label()`。
  - `ExtensionAPI` 新增 control facade：`set_active_tools()`、`set_model()`、`get_thinking_level()`、`set_thinking_level()`，通过 runtime bindings 落到当前 `AgentSession`。
  - `ai` / `agent` 包回归中顺手清理两个未使用 import，保持直接包 ruff 通过。
- 该批改动通过相关测试：
  - `ruff check src/loushang/ai src/loushang/agent tests/ai tests/agent`
  - `pytest tests/ai tests/agent -q`
  - `pytest tests/coding/test_extension_api.py tests/coding/test_extension_runner.py tests/coding/test_agent_session.py -q`
  - `pytest tests/coding -q`

### 当前估算调整（非 TUI）

- `extensions` 与 pi 对齐率从约 **90%** 提升到约 **92%**：
  - provider request/response lifecycle、runtime-bound API reads/actions/control facade 已覆盖 pi 示例中的主要非 TUI extension 用法。
  - 仍缺 provider registration facade（`registerProvider` / `unregisterProvider`）和 message renderer/theme/TUI UI 面。
- `ai/agent` 直接包稳定性维持高位：
  - 本轮新增 `on_response` 传递链路后，直接包回归通过。
- 总体与 pi 对齐率粗估从约 **91%** 提升到约 **92%**。

### 下一步建议

1. 补 provider registration facade，但要先确认 loushang `ModelRegistry`/provider registry 的边界，避免把 provider 动态注册塞错层。
2. 补 command registry/slash command 的剩余执行语义与 diagnostics 细节。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（extension provider registration P0）

- 2026-05-02 继续补齐 pi-style `registerProvider` / `unregisterProvider` 的非 TUI P0：
  - `ExtensionAPI.register_provider(name, config)` 支持 extension load-time 调用；runtime bindings 尚未就绪时先排队，绑定后自动应用。
  - `ExtensionAPI.unregister_provider(name)` 支持绑定后立即移除 provider。
  - `AgentSession` 通过 extension runtime bindings 将 provider registration 落到当前 `ModelRegistry`。
  - `loushang.ai.model.ModelRegistry` 新增 `unregister_provider(provider_id)`。
  - P0 当时支持直接注册 `Provider` 对象，并临时支持 pi-style dict config（`name` / `baseUrl` / `api` / `apiKey` / `headers` / `models`）。
    后续由 `ARD-003` 修正方向：dict 入口应改为 loushang-native schema，而不是继续承诺 pi-style flat config。
- 该批改动通过相关测试：
  - `ruff check` 针对 ai model registry、control model registry、extensions、session 与目标测试文件
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `extensions` 与 pi 对齐率从约 **92%** 提升到约 **93%**：
  - provider model registration 的 load-time pending 与 bound runtime immediate apply 语义已补齐。
  - 仍缺 `streamSimple` 自定义 API provider 注册、OAuth provider registration、以及 TUI/message renderer/theme 相关 API。
- 总体与 pi 对齐率粗估维持约 **92%** 到 **93%** 区间。

### 下一步建议

1. 继续补 command registry/slash command 的剩余执行语义与 diagnostics 细节。
2. 评估是否把 `streamSimple` provider registration 接到 `ApiProviderRegistry`，但需要先稳定 source cleanup 和 API provider source ownership。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（command execution resource command alignment）

- 2026-05-02 继续补齐 command registry/slash command 的非 TUI 执行语义：
  - `AgentSession.execute_command_async()` 现在接受带 `/` 前缀的 command name。
  - extension command 仍保持最高优先级。
  - 当没有同名 extension command 时，`execute_command_async()` 可执行 prompt template command，返回展开后的 prompt text。
  - `execute_command_async()` 可执行 `skill:<name>` command，返回展开后的 skill block text。
  - `get_commands()` 中暴露的 extension/prompt/skill command 现在都有对应的 session-level command execution 投影。
- 该批改动通过相关测试：
  - `ruff check src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `session/mode/command` 与 pi 对齐率从约 **93%** 提升到约 **94%**：
  - slash command 的 listing 与 execution surface 更一致，CLI/RPC/SDK 可以复用同一 `execute_command_async()` 入口。
  - 仍缺 interactive/TUI 的 builtin command handling，以及 method registry 相关 command 分发。
- 总体与 pi 对齐率粗估维持约 **93%** 到 **94%** 区间。

### 下一步建议

1. 补 `streamSimple` provider registration 到 `ApiProviderRegistry`，前提是先明确 source cleanup 和 unregister 行为。
2. 继续补 command diagnostics：区分 command not found、resource command unresolved、extension command failed 的稳定 code。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（command diagnostics alignment）

- 2026-05-02 继续补齐 command registry/slash command 的 diagnostics 语义：
  - `AgentSession.execute_command_async()` 在没有 extension/resource command 匹配时记录 `command_not_found` runtime warning。
  - resource command 解析失败仍保留 loader/preflight 产生的稳定资源诊断，例如 `unresolved_prompt_reference`，不额外混入 `command_not_found`。
  - extension command 执行异常继续使用既有 `extension_command_failed` runtime error。
  - 这样 command 执行的三个主要结果面已经可以被 diagnostics 稳定区分：未找到、资源未解析、extension 执行失败。
- 该批改动通过相关测试：
  - `ruff check src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `session/mode/command/diagnostics` 与 pi 对齐率从约 **94%** 提升到约 **95%**：
  - slash command listing、execution、resource fallback 与 diagnostics 区分已基本闭环。
  - 仍缺 interactive/TUI builtin command handling、method registry、以及部分 provider registration 的 streamSimple/OAuth API 面。
- 总体与 pi 对齐率粗估维持约 **94%** 到 **95%** 区间。

### 下一步建议

1. 补 `streamSimple` provider registration 到 `ApiProviderRegistry`，收口 provider source ownership 与 unregister cleanup。
2. 继续盘点 runtime/session/store 是否还有 pi-style lifecycle/query 小缺口。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（streamSimple provider registration P0）

- 2026-05-02 继续补齐 pi-style provider registration 的 API provider 面：
  - `AgentSession` 现在支持 extension provider config 中的 `streamSimple` / `stream_simple`。
  - `streamSimple` registration 要求显式 `api`，并注册到 `ApiProviderRegistry`。
  - API provider 使用 `provider:<name>` 作为 source ownership；重复注册会先清理同 source 的旧 API provider。
  - `unregisterProvider(name)` 现在同时移除 model provider 与同 source 的 API provider。
  - Agent 默认 streaming registry 已统一到 `loushang.ai` 默认 `ApiProviderRegistry`，避免 extension 注册 API provider 后 Agent runtime 仍使用另一份私有 registry。
- 该批改动通过相关测试：
  - `ruff check src/loushang/agent/agent.py src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py tests/ai tests/agent -q`

### 当前估算调整（非 TUI）

- `extensions/provider/runtime` 与 pi 对齐率从约 **93%** 提升到约 **95%**：
  - model provider registration 与 `streamSimple` API provider registration 已形成同一 extension lifecycle。
  - 仍缺 OAuth provider registration、pi 完整 provider request config/compat 细节，以及 TUI/message renderer/theme API 面。
- 总体与 pi 对齐率粗估提升到约 **95%** 区间。

### 下一步建议

1. 继续盘点 runtime/session/store 的 lifecycle/query 缺口，优先补非 TUI MVP 必需面。
2. 补 extension provider registration 的 OAuth/request config 细节时，要先看 auth/login 组件边界。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（OAuth provider registration P0）

- 2026-05-02 继续补齐 pi-style `registerProvider({ oauth })` 的最小非 TUI 语义：
  - extension provider config 中的 `oauth` 会注册到 `OAuthProviderRegistry`。
  - OAuth provider id 强制使用 provider name，与 pi 保持一致。
  - 支持 pi-style `login` / `refreshToken` / `getApiKey`，并兼容 snake_case `refresh_token` / `get_api_key`。
  - OAuth registration 使用同一个 `provider:<name>` source ownership；`unregisterProvider(name)` 会同步清理 OAuth provider。
  - OAuth callback 可返回 `OAuthCredentials` 或 dict，dict 会规范化为 loushang `OAuthCredentials`。
- 该批改动通过相关测试：
  - `ruff check src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `extensions/provider/auth` 与 pi 对齐率从约 **95%** 提升到约 **96%**：
  - model provider、API stream provider、OAuth provider 三条 registration 路径已有统一 lifecycle/source cleanup。
  - 仍缺完整 `/login` UI/TUI 交互、provider request config 的全部兼容字段和 method registry。
- 总体与 pi 对齐率粗估提升到约 **95%** 到 **96%** 区间。

### 下一步建议

1. 继续盘 runtime/session/store lifecycle/query 是否还有非 TUI MVP 缺口。
2. 收口 provider request config/compat 字段映射，但避免提前做 TUI login 交互。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（provider config validation/compat alignment）

- 2026-05-02 继续补齐 pi-style provider config 的校验与字段落地：
  - extension provider config 定义 `models` 时，按 pi 规则要求 `baseUrl`。
  - extension provider config 定义 `models` 时，按 pi 规则要求 `apiKey` 或 `oauth`。
  - model config 必须能从 model 或 provider config 解析出 `api`，不再隐式兜底成 `anthropic-messages`。
  - provider-level `compat` / `defaults` 会落到 endpoint，并通过 endpoint binding 合并到 model。
  - model-level `compat` / `defaults` 会落到 Model，并覆盖/扩展 endpoint 级字段。
  - extension provider config 校验失败沿用 loushang 当前 runtime bind 诊断策略，记录 `extension_runtime_bind_failed`，避免半注册 provider。
- 该批改动通过相关测试：
  - `ruff check src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `extensions/provider/model-config` 与 pi 对齐率从约 **96%** 提升到约 **97%**：
  - provider registration 的 model/API/OAuth/request config P0 已基本闭环。
  - 仍缺更完整的 provider request config storage/override-only 更新语义、TUI login 交互、message renderer/theme API 和 method registry。
- 总体与 pi 对齐率粗估提升到约 **96%** 到 **97%** 区间。

### 下一步建议

1. 继续盘 runtime/session/store lifecycle/query 是否还有非 TUI MVP 缺口。
2. 评估 provider override-only 更新语义是否需要在 loushang `ModelRegistry` 支持 partial provider update。
3. 将 `method` 基础 registry 放到最后一批非 TUI MVP 收口。

## 2026-05-02 更新（provider override-only update alignment）

- 2026-05-02 继续补齐 pi-style `registerProvider` 的 override-only 更新语义：
  - 当 extension provider config 不包含 `models` 且 provider 已存在时，不再清空/替换 provider。
  - 无 `models` 的二次注册会更新已有 endpoint 的 `baseUrl`、auth headers、`compat`、`defaults`。
  - 更新后保留已有 models，并重新通过 endpoint binding 合并 endpoint-level `compat` / `defaults`。
  - 这对齐 pi 中 `baseUrl` / `headers` override-only 更新已有 provider models 的行为。
- 该批改动通过相关测试：
  - `ruff check src/loushang/coding/session/agent_session.py tests/coding/test_agent_session.py`
  - `pytest tests/coding/test_agent_session.py -q`

### 当前估算调整（非 TUI）

- `extensions/provider/model-config` 与 pi 对齐率从约 **97%** 提升到约 **98%**：
  - provider registration 的 full replacement 与 override-only update P0 均已覆盖。
  - 仍缺完整 TUI login 交互、message renderer/theme API 和 method registry。
- 总体与 pi 对齐率粗估提升到约 **97%** 区间。

### 下一步建议

1. 继续盘 runtime/session/store lifecycle/query 的剩余边角，确认是否还有非 TUI MVP 必需缺口。
2. 若不再发现高价值非 TUI 缺口，下一步应进入 `method` 基础 registry 或开始 CLI/TUI 外围。

## 2026-05-02 更新（provider/model boundary decision）

- 2026-05-02 补充架构决策 `ARD-003: Provider And Model Boundary`：
  - `loushang-ai` 的 `Provider -> Endpoint -> Model` graph 是内部权威模型。
  - `models.json` 与 `loushang-ai` registry loader 不应为了 pi-style provider config 降级成扁平结构。
  - `ExtensionAPI.register_provider(name, dict)` 可以保留 dict 入口，但 dict schema 应是 loushang-native，
    对齐 `models.json` / `Provider -> Endpoint -> Model`，不是 pi-style flat provider config。
  - native `Provider` 输入是优先 typed path。
  - `streamSimple` / OAuth / model registry 不应混进同一个 pi-style provider dict；如需迁移 pi extension，应做独立 adapter。
- 同步更新 `component-interfaces/extensions.md` 的 provider registration 边界说明。

### 当前估算调整（非 TUI）

- 完成度不因文档更新直接提升，但 provider/model 后续工作边界更清晰：
  - 已明确停止把 pi flat provider config 当 dict 入口目标。
  - 下一步应转向 runtime/session/store、method registry 或 CLI/TUI，而不是继续扩 pi-style provider 字段。

## 2026-05-02 更新（provider dict implementation boundary）

- 2026-05-02 按 `ARD-003` 修正实现方向：
  - `ExtensionAPI.register_provider(name, Provider)` 继续作为 typed path。
  - `ExtensionAPI.register_provider(name, dict)` 改为 loushang-native `Provider -> Endpoint -> Model` schema。
  - 新 dict schema 使用 provider-level `displayName` / `website` / `auth`、endpoint-level
    `api` / `baseUrl` / `authOverride` / `compat` / `defaults`、以及 endpoint `models` dict。
  - 旧 pi-style flat dict（顶层 `api` / `baseUrl` / `apiKey` / `models` list）不再被 core 接受。
  - `streamSimple` / `oauth` 不再混在 provider/model dict 中注册；未来如需要直接迁移 pi extension，
    应新增显式 adapter 或独立 API/OAuth registration 面。
  - native dict 二次注册仍支持对已有 endpoint 做局部更新，并保留已有 models 后重新 binding endpoint 级
    `compat` / `defaults`。
- 这会回退之前报告里“pi-style streamSimple/OAuth provider dict 已闭环”的结论：
  - 生命周期清理语义仍保留，但 provider dict 不再承载 API stream / OAuth 注册职责。
  - provider/model 对齐目标从“字段形态对齐 pi”改为“生命周期语义对齐 pi，数据模型对齐 loushang-ai”。

### 当前估算调整（非 TUI）

- 与 pi 的 provider config 字段形态对齐率刻意下调，因为这是有意不对齐：
  - provider/model 语义完成度约 **97%**：注册、注销、局部更新、diagnostics 都覆盖。
  - pi flat provider config 兼容度约 **0%**：core 明确拒绝，未来只通过 adapter 承接。
  - overall 非 TUI MVP 完成度维持约 **95%** 到 **96%**，不因刻意拒绝 pi flat schema 视为核心倒退。

## 2026-05-02 更新（store/runtime session entrypoints）

- 2026-05-02 补齐一批 pi-style store/session 基础入口，但使用 loushang snake_case 命名：
  - `SessionManager.open(session_file, session_dir=None, cwd_override=None, persist=True)`
  - `SessionManager.continue_recent(session_dir, cwd, persist=True)`
  - `SessionManager.in_memory(cwd=".")`
  - `SessionManager.fork_from(source_file, target_cwd, session_dir, persist=True)`
- `AgentSessionRuntime.restore_session()` 与 `import_from_jsonl()` 改为复用 `SessionManager.open()`，
  将 `session_dir` / `cwd_override` 语义收口到 store 层。
- 与 pi 语义关系：
  - 覆盖 pi `open` / `continueRecent` / `inMemory` / `forkFrom` 的核心能力。
  - 不新增 camelCase alias，避免重复 API 面。
  - 不改变 loushang 现有 JSONL 格式、summary index 或 diagnostics index。

### 当前估算调整（非 TUI）

- `store/session entrypoints` 与 pi 对齐率从约 **90%** 提升到约 **95%**：
  - session 创建、打开、最近恢复、内存 session、跨 cwd fork 的基础入口已覆盖。
  - 仍未刻意复刻 pi 的延迟 flush 细节，当前 loushang 仍保持即时 header/session 文件创建。
- overall 非 TUI MVP 完成度粗估提升到约 **96%**。

## 2026-05-02 更新（AgentSession thinking/abort control surface）

- 2026-05-02 补齐一批 `AgentSession` 控制面 snake_case facade：
  - `supports_thinking()`
  - `supports_xhigh_thinking()`
  - `get_available_thinking_levels()`
  - `abort_compaction()`
  - `abort_branch_summary()`
- 同时修正 `cycle_thinking_level()` 语义：
  - 当前模型不支持 reasoning 时返回 `None`。
  - thinking level 会 clamp 到可用 levels，不再在非 reasoning 模型上保留高 thinking level。
- 与 pi 语义关系：
  - 对齐 pi `supportsThinking()` / `supportsXhighThinking()` / `getAvailableThinkingLevels()` /
    `cycleThinkingLevel()` / `abortCompaction()` / `abortBranchSummary()` 的核心行为。
  - loushang 对外优先新增 snake_case，不继续扩大 camelCase alias 面。

### 当前估算调整（非 TUI）

- `session/control` 与 pi 对齐率从约 **94%** 提升到约 **96%**。
- overall 非 TUI MVP 完成度维持约 **96%**，剩余主要集中在 method registry、TUI/interactive 外围和少量 UI 相关 extension API。

## 2026-05-02 更新（allowed tool boundary）

- 2026-05-02 补齐 `AgentSession.allowed_tool_names` / `create_agent_session(..., allowed_tool_names=...)`：
  - 对齐 pi `allowedToolNames` 的核心语义：限制当前 session 可见工具和可激活工具。
  - `get_all_tools()` / `getToolDefinition(name)` 只返回 allowlist 内工具。
  - 初始 active tools 与后续 `set_active_tools(...)` 会过滤掉 allowlist 外工具。
  - extension-contributed tools、built-in tools、custom registry tools 统一通过同一个 session allowlist 过滤。
- 边界选择：
  - allowlist 属于 `AgentSession`，不是 `ToolRegistry`。
  - `ToolRegistry` 继续保存完整定义集合；session 决定暴露和注入给 agent 的工具子集。
  - 对外新增 snake_case 参数，不新增 `allowedToolNames` camelCase alias。

### 当前估算调整（非 TUI）

- `tools/session active tool boundary` 与 pi 对齐率从约 **95%** 提升到约 **97%**。
- overall 非 TUI MVP 完成度粗估维持约 **96%** 到 **97%**；剩余非 method 缺口主要在 command/slash 执行边角、少量 extension UI API，以及 TUI/interactive 外围。

## 2026-05-02 更新（CLI/runtime tools allowlist mapping）

- 2026-05-02 将 allowlist 继续透传到 runtime 和 CLI：
  - `create_agent_session_runtime(..., allowed_tool_names=...)` 透传到每个新建/恢复 session factory。
  - CLI `--tools/-t` 现在同时映射为 allowed tools 和 initial active tools。
  - CLI `--no-tools/-nt` 现在映射为空 allowed tools，而不仅是空 active tools。
- 与 pi 语义关系：
  - 对齐 pi SDK 中 `options.tools -> allowedToolNames + initialActiveToolNames`。
  - 对齐 pi SDK 中 `noTools=all -> allowedToolNames=[]` 的硬禁用语义。
  - loushang 保留已有 `--no-builtin-tools` 语义：它仍是 registry 层不注册 built-ins，与 `--no-tools` 的 session allowlist 边界不同。

### 当前估算调整（非 TUI）

- `CLI/runtime tools configuration` 与 pi 对齐率从约 **90%** 提升到约 **96%**。
- overall 非 TUI MVP 完成度粗估小幅提升到约 **97%**；剩余非 method 缺口继续集中在 command/slash execution 边角、extension UI/TUI API、以及 interactive/TUI。

## 2026-05-02 更新（default active tools）

- 2026-05-02 对齐 pi 默认 active tools 规则：
  - 默认只激活核心 built-ins：`read`、`bash`、`edit`、`write`。
  - `ls`、`find`、`grep` 仍在 `get_all_tools()` 中可见，但不默认注入 prompt / agent runtime。
  - custom tools 与 extension-contributed tools 默认 active，保持扩展安装后即可用。
  - 显式 `allowed_tool_names` 存在时，默认 active set 为 allowlist 内所有可用工具，继续对齐 pi `allowedToolNames` 语义。
- 影响：
  - 默认 prompt 更瘦，减少非必要工具 schema/说明进入模型上下文。
  - 用户仍可通过 `--tools`、`active_tool_names` 或 extension `set_active_tools()` 激活 `ls/find/grep`。

### 当前估算调整（非 TUI）

- `tools/default runtime injection` 与 pi 对齐率从约 **88%** 提升到约 **97%**。
- overall 非 TUI MVP 完成度继续维持约 **97%**；这批主要降低默认运行时差异，不改变工具能力覆盖。

## 2026-05-02 更新（tool sourceInfo projection）

- 2026-05-02 补齐 `AgentSession.getAllTools()` 的 `sourceInfo` 投影：
  - builtin tools 返回 synthetic provenance：`<builtin:name>` / `source="builtin"` / `origin="package"`。
  - SDK/custom tools 返回 synthetic provenance：`<sdk:name>` / `source="sdk"` / `origin="top-level"`。
  - `sourceInfo` 不再是空占位，extension/SDK 侧可直接消费工具来源信息。
- 边界：
  - 本轮只补 projection，不改 `ToolDefinition` 和 `ToolRegistry` 存储结构。
  - extension package 级精确 provenance 仍需要后续给 registry entry 增加 source metadata。

### 当前估算调整（非 TUI）

- `tool introspection/source provenance` 与 pi 对齐率从约 **80%** 提升到约 **90%**。
- overall 非 TUI MVP 完成度维持约 **97%**；剩余主要是精确 extension tool provenance、message renderer/theme/TUI API、interactive builtin command handling，以及 method registry。

## 2026-05-02 更新（extension tool provenance）

- 2026-05-02 将 tool source metadata 下沉到 `ToolRegistry` entry：
  - `ToolRegistry.register_tool(..., source_info=...)` 保存可选来源信息。
  - `ExtensionRunner` 为 extension tools 记录 `_source_info_from_extension(...)`。
  - bootstrap 注册 extension tools 时把真实 extension sourceInfo 写入 registry。
  - `AgentSession.getAllTools()` 优先使用 registry entry sourceInfo；没有 metadata 时才回退 synthetic builtin/sdk provenance。
- 与 pi 语义关系：
  - 对齐 pi `RegisteredTool { definition, sourceInfo }` 到 session `ToolInfo.sourceInfo` 的主路径。
  - extension tool 现在能返回真实 `path/source/scope/origin/baseDir`，不再误标为 sdk。

### 当前估算调整（非 TUI）

- `tool introspection/source provenance` 与 pi 对齐率从约 **90%** 提升到约 **97%**。
- overall 非 TUI MVP 完成度仍约 **97%**；剩余非 method 缺口进一步集中到 message renderer/theme/TUI API、interactive builtin command handling、以及少量 provider/UI 交互边缘。

## 2026-05-02 更新（message renderer registry）

- 2026-05-02 补齐 extension message renderer 的 headless registry：
  - `ExtensionAPI.register_message_renderer(custom_type, renderer)`
  - `ExtensionAPI.registerMessageRenderer(custom_type, renderer)`
  - `LoadedExtension.message_renderers`
  - `ExtensionRunner.get_message_renderer(custom_type)` / `getMessageRenderer(custom_type)`
- 与 pi 语义关系：
  - 对齐 pi `registerMessageRenderer(...)` 和 runner `getMessageRenderer(...)` 的注册/查询主路径。
  - 同 custom type 多个 extension 注册时，按 extension 加载顺序 first wins。
  - 本轮只做 headless registry contract，不实现 TUI component rendering。

### 当前估算调整（非 TUI）

- `extension/message renderer registry` 与 pi 对齐率从约 **0%** 提升到约 **70%**。
- overall 非 TUI MVP 完成度仍约 **97%**；剩余差距是 renderer 的真实 TUI消费、theme/UI细节、interactive builtin command handling，以及 method registry。

## 2026-05-02 更新（pi-style resources_discover paths）

- 2026-05-02 补齐 extension `resources_discover` 的 pi-style path result：
  - handler 可返回 `promptPaths`、`skillPaths`、`themePaths`。
  - runner 将这些 path 转成 loushang 现有 `PromptFragmentDescriptor`、`SkillDescriptor`、`ThemeDescriptor`。
  - 继续保留原有 `ExtensionResourceContribution` typed path。
- 与 pi 语义关系：
  - 对齐 pi `emitResourcesDiscover()` 返回 path arrays 的主语义。
  - loushang 内部仍使用 descriptor/bundle 作为 canonical resource model。

### 当前估算调整（非 TUI）

- `extension/resource discovery` 与 pi 对齐率从约 **88%** 提升到约 **96%**。
- overall 非 TUI MVP 完成度维持约 **97%**，剩余主要是 TUI/interactive 消费层、theme UI 细节、method registry。

## 2026-05-02 更新（extension resource path diagnostics）

- 2026-05-02 补齐 extension `resources_discover` path result 的诊断收口：
  - `promptPaths` 指向不存在或不可读文件时返回 `extension_prompt_path_not_found` / `extension_prompt_path_read_failed`。
  - `skillPaths` 指向不存在或不可读 skill 文件时返回 `extension_skill_path_not_found` / `extension_skill_path_read_failed`。
  - `themePaths` 指向不存在路径时返回 `extension_theme_path_not_found`。
  - contribution diagnostics 统一进入 `discover_resources()` 的 diagnostics 汇总，再同步到 runner 全局 diagnostics。
- 与 pi 语义关系：
  - 对齐 pi resource loading 对坏资源产出 warning diagnostics 的主行为。
  - loushang 仍保持 descriptor/bundle 为 canonical model，但不再对 extension 显式声明的坏 path 静默跳过。

### 当前估算调整（非 TUI）

- `extension/resource discovery diagnostics` 与 pi 对齐率从约 **70%** 提升到约 **92%**。
- overall 非 TUI MVP 完成度仍约 **97%**；这批主要降低诊断可见性差距。

## 2026-05-02 更新（session command listing）

- 2026-05-02 对齐 pi `get_commands` / `list_commands` 的 extension command listing 语义：
  - pi 的 `RegisteredCommand` 没有 `hidden` 过滤层，RPC `get_commands` 会返回 runner 注册的全部 extension commands。
  - loushang `AgentSession.list_commands()` 不再按 `hidden=True` 过滤 extension commands。
  - `RegisteredCommand.hidden` 与 `ExtensionAPI.register_command(hidden=...)` 已删除，避免 API 语义继续分叉。

### 当前估算调整（非 TUI）

- `commands/session command surface` 与 pi 对齐率从约 **93%** 提升到约 **96%**。
- overall 非 TUI MVP 完成度仍约 **97%**；剩余 command 差距主要在 interactive builtin command 消费层与 TUI autocomplete。

## 2026-05-02 更新（queued extension command error）

- 2026-05-02 对齐 pi `steer()` / `followUp()` 遇到 extension command 时的错误文案：
  - loushang 现在返回 `Extension command "/name" cannot be queued. Use prompt() or execute the command when not streaming.`
  - 行为仍保持不执行 command handler，只拒绝进入 queue。

### 当前估算调整（非 TUI）

- `commands/queued command semantics` 与 pi 对齐率从约 **95%** 提升到约 **99%**。
- overall 非 TUI MVP 完成度维持约 **97%**；这是 SDK-facing 错误契约收口。

# Kimi CLI Candidate Subsystems

## Scope

本文档给出 `kimi-cli` 的候选子系统划分。

这里的“候选”有两个含义：

- 当前划分用于建立后续系统环境图与黑盒分析的基础边界
- 当前划分不是最终架构定稿，后续仍可继续合并、拆分或重命名

与第一版候选划分相比，本文不再只按目录做平铺盘点，而是结合已经完成的黑盒分析，改为按“架构边界候选”组织。

## Candidate Subsystems

## Internal Candidate Subsystems

以下对象可视为 `kimi-cli` 内部的候选子系统。

### Foundational Runtime Boundaries

- `config`
  - 配置加载、配置校验、配置持久化、默认配置与 legacy 配置迁移边界

- `llm`
  - `LLM Binding Layer`
  - 负责把 provider/model/config/oauth/env/session 参数绑定成可运行的 `LLM`

- `session`
  - 负责 session 元数据、context file、wire file、session state 与 session 生命周期

- `wire`
  - 负责跨边界消息承载、wire message、wire server、root hub 与事件转发

### Core Runtime Boundaries

- `soul`
  - 负责 agent personality、dynamic injection、toolset 装配与核心对话运行逻辑

- `subagents`
  - 负责 subagent 构建、运行、恢复与状态持久化

- `tools`
  - 负责工具定义、工具家族、工具输入输出与工具显示块

- `auth`
  - 负责平台认证、OAuth、provider 凭证解析与平台模型同步相关逻辑

- `plugin`
  - 负责插件管理、插件工具桥接与插件运行时接入

- `hooks`
  - 负责 hook 配置、hook 事件、hook 执行引擎与 hook runner

- `background`
  - 负责后台任务、后台 worker、后台状态与后台任务视图

- `notifications`
  - 负责通知对象、通知存储、通知管理与通知观察逻辑

### Interaction Boundaries

- `ui`
  - 负责 terminal shell、print 模式等本地交互表面

- `web`
  - 负责 Web API、Web runner、Web session store 与 Web 会话承载

- `vis`
  - 负责 tracing / session visualization 的服务端承载与访问入口

- `acp`
  - 负责 ACP 协议适配、ACP server 与 ACP 消息转换

- `cli`
  - 负责命令行入口、子命令路由、启动模式切换与进程级装配

### Supporting / Composition Boundaries

- `skill`
  - 负责 skill 装载、frontmatter 解析与 skill 运行时入口

- `skills`
  - 负责内置 skill 资源内容
  - 更接近运行时资源集合，而不是复杂执行内核

- `utils`
  - 负责共享工具函数、日志、路径、IO、rich 辅助、子进程环境等共用能力

- `prompts`
  - 负责 prompt 资源与提示文本组织

- `agents`
  - 负责内置 agent 资源与 agent 定义模板

- `approval_runtime`
  - 负责审批请求运行时与相关中间逻辑

- `deps`
  - 负责依赖兼容或工程支撑组织

## External Foundational Systems

以下对象不是 `kimi-cli` 内部子系统，但它们已经足够稳定，应该作为候选架构边界在总图中显式出现。

- `Kosong Chat Provider Layer`
  - `kimi-cli` 直接依赖的 LLM abstraction / provider adapter 层
  - 位于 `llm` 与外部 provider API 之间

- `Provider APIs`
  - 外部模型服务系统
  - 包括 `kimi`、`openai-legacy`、`openai-responses`、`anthropic`、`gemini`、`vertexai`

## Role Classification

为了后续架构分析方便，候选边界可以进一步标注为四类角色。

### Foundational Subsystem

这些边界更像 `kimi-cli` 的底层稳定能力边界：

- `config`
- `llm`
- `session`
- `wire`

它们的共同特点是：

- 为多个上层边界提供基础能力
- 依赖方向更集中地指向它们
- 更适合作为系统环境图的优先起点

### Core Runtime Subsystem

这些边界更像 `kimi-cli` 的核心运行时能力：

- `soul`
- `subagents`
- `tools`
- `auth`
- `plugin`
- `hooks`
- `background`
- `notifications`

它们的共同特点是：

- 直接参与 agent 运行、工具调用、状态推进或运行时协作
- 常常装配或消费 foundational subsystem

### Interaction Subsystem

这些边界更像 `kimi-cli` 面向用户或外部客户端的交互表面：

- `ui`
- `web`
- `vis`
- `acp`
- `cli`

它们的共同特点是：

- 承接用户输入、客户端输入或可视化输出
- 更多承担入口、适配、呈现与交互职责

### Supporting / Composition Subsystem

这些边界当前更适合作为支撑边界或组合边界来看待：

- `skill`
- `skills`
- `utils`
- `prompts`
- `agents`
- `approval_runtime`
- `deps`

它们的共同特点是：

- 为核心运行时或交互边界提供资源、辅助逻辑或局部运行时能力
- 某些边界未来可能被并入更大的正式子系统

## Boundary Notes

当前候选划分采用以下原则：

- 目录边界仍然重要，但不再机械等同于正式子系统边界
- 已经完成黑盒分析的对象，应优先提升为明确候选边界
- 下层稳定边界优先于上层装配边界

因此，相比第一版候选划分，这一版做了几个关键修正：

- 不再把 `app/session/llm/config` 视为一个粗粒度组合边界
- 把 `config`、`llm`、`session` 明确拆开
- 把 `wire` 明确提升为 foundational subsystem
- 把 `Kosong Chat Provider Layer` 与 `Provider APIs` 显式列为外部基础系统

同时需要注意：

- `skills`、`prompts`、`deps` 当前仍更像资源或工程支撑边界
- `ui`、`web`、`vis`、`acp` 后续仍可能在更高层级被归并为统一的 interaction surfaces
- `soul` 与 `subagents` 后续也可能被提升或重组为更明确的 runtime core 结构

## Next Step

基于当前候选划分，后续系统环境图建议优先从尚未完成的 foundational / core runtime 黑盒继续分析。

推荐顺序为：

1. `session`
2. `wire`
3. `soul`
4. `tools`
5. `subagents`

原因是：

- `config -> llm -> Kosong Chat Provider Layer -> Provider APIs` 这一条底层链路已经基本清楚
- 下一步最值得补的是承接会话、消息与运行时控制的黑盒

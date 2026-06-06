# Loushang Product Surfaces And Roadmap

## Scope

本文档用于收敛 `loushang` 的对外产品面、核心入口语义与分阶段路线图。

本文档重点回答：

- `loushang` 对外应以什么品牌和入口面出现
- `code / ppt / research / work` 之间是什么关系
- `init` 与 `intake` 应如何区分
- V1 到 V5 的产品演进路径是什么
- 运行时事实模型与方法资产模型如何分层

本文档不展开：

- 具体交互稿
- 具体命令行参数设计
- 具体数据对象字段草案
- 具体实现计划

## Design Basis

本文档建立在以下文档与讨论结论之上：

- [Loushang Strategy](strategy.md)
- [ARD-001: Loushang Coding Product Boundaries](../architecture/coding/ARD-001-coding-product-boundaries.md)
- [Loushang Coding System Context](../architecture/coding/loushang-coding-system-context.md)

同时吸收以下外部参考的启发：

- `pi-coding-agent` 的 runtime 主骨架
- `superpowers` 的方法化研发流程
- `gstack` 的技能路由、项目接入与 host 适配经验

## Product Principle

当前接受以下产品原则：

### 1. 对外只有一个主品牌：`loushang`

`loushang` 是统一主品牌，不拆成多个平级主品牌。

因此，当前不建议把以下名称作为主品牌：

- `loushangcode`
- `loushangwork`
- `lscode`

### 2. 产品入口可以分化，但结构上必须统一

`loushang` 可以对外暴露多个一级入口，以降低用户理解成本；但这些入口不应演化为彼此割裂的独立产品。

### 3. 第一版先跑通真实价值闭环

第一版首先保证一个真实可用、可验证、可持续演进的 `code` 主场景跑通，而不是一开始同时做全量 `work` 愿景。

### 4. 方法资产高于 prompt 技巧

`loushang` 的核心差异点不应建立在单轮 prompt 编排上，而应建立在：

- 方法
- 阶段
- 角色
- work product
- acceptance
- world model

这些可运行资产之上。

## Product Surface Model

### Primary Brand

- `loushang`

### Primary Entry Surfaces

当前建议接受以下一级入口：

- `loushang`
- `loushang code`
- `loushang ppt`
- `loushang research`
- `loushang work`

### Surface Roles

#### `loushang`

统一主入口。

职责：

- 接收用户自然语言输入
- 执行 `intake`
- 根据上下文进入合适的工作面

默认行为：

- 在 repo 内运行时，默认偏向 `code`
- 在非 repo 目录运行时，优先做一次轻量 `code / work` 分流

#### `loushang code`

第一阶段主战场。

定位：

- 面向软件研发与变更交付的工作面

职责：

- feature / bug / PR / incident 等研发工作
- 方法化研发推进
- review / acceptance / delivery 留痕

#### `loushang ppt`

一级入口，但概念上属于 `work` 领域。

定位：

- 面向 deck 交付的工作面

职责：

- 根据目标、受众与交付场景匹配 deck 方法
- 推进 brief / storyline / outline / review / polish / deliver

说明：

- `ppt` 值得提升到一级入口，因为它是一个足够强的高价值主战场
- 但在概念层仍然视为 `work` 的特化工作流

#### `loushang research`

一级入口，但概念上属于 `work` 领域。

定位：

- 面向研究、判断形成与上游输入准备的工作面

职责：

- framing / gather / synthesis / review / handoff
- 为 `ppt`、`code`、未来的 report/proposal 等提供输入

#### `loushang work`

统一上位工作面。

定位：

- 面向复杂知识工作与跨流编排的工作台

第一阶段角色：

- 保留一级入口
- 作为抽象上位面与轻量入口占位
- 不作为第一版主推的成熟专业流

长期角色：

- 统一组织 `code / ppt / research`
- 成为个人复杂工作的工作台
- 在 daemon 支撑下逐步演化为 method-native personal chief of staff

## `init` And `intake`

当前接受以下术语区分：

### `init`

显式初始化动作。

例子：

- `loushang init`

语义：

- 明确初始化或重初始化某个项目或 run
- 允许更显式、更重的控制与确认

### `intake`

自然语言进入时的隐式入口解析动作。

语义：

- 识别当前工作类型
- 选择或推荐方法
- 选择入口阶段
- 生成 `run draft`

说明：

- `loushang + 自然语言` 默认触发的是 `soft intake`
- 它不等于显式 `init`

## Surface Relationships

### `code / ppt / research / work` 共享什么

当前建议共享以下通用骨架：

- `RunIntake`
- `RunDraft`
- `ActiveRun`
- `MethodDescriptor`
- `StageDescriptor`
- `WorkProductSpec`
- `AcceptanceCriterion`
- `SessionMethodBinding`
- `IterationScope`
- `HandoffPack`
- `ModelProfile`
- `GatewayUsageRecord`

同时共享以下交互模式：

- 自然语言触发 `intake`
- 显式 `/method`
- 显式 `/stage`
- interactive 中的 `Tab` 阶段选择
- 局部迭代
- review / acceptance 留痕
- handoff 到其他工作面

### 哪些必须保持各自语言体系

不应强行统一以下语义：

- 阶段 vocabulary
- 方法 taxonomy
- work product 名称
- acceptance 表达方式

例如：

- `code` 的阶段语言不应等同于 `ppt`
- `research` 的判断产物不应被命名成 `code` 风格的工件

原则是：

- 共享骨架
- 保留语义语言

## Roadmap

### V1: `loushang code`

目标：

- 先镜像 `pi` 的核心 runtime 主骨架
- 形成一个真实可跑、可用、可验证的 `code` 产品闭环

对外建议：

- 主入口仍为 `loushang`
- 明确支持 `loushang code`

这一阶段不要求：

- 完整 `work` 工作台
- 完整 `ppt / research`
- daemon
- team
- managed

但必须预留以下最小接缝：

- `MethodDescriptor`
- `SessionMethodBinding`
- `RunIntake`
- `GatewayUsageRecord`

### V2: `loushang work`

目标：

- 把 `code` 放回统一工作台语义下
- 建立 `work` 作为上位工作面
- 让 `ppt` 与 `research` 成为真实工作面，而不是纯命名占位

这一阶段的核心定位：

- `work` 是个人复杂工作的 workbench
- `code / ppt / research` 是专业执行流

### V3: daemon + market + gateway

目标：

- 增加连续性与后台运行能力
- 引入方法论市场
- 引入模型网关、计量与分账基础设施

说明：

- daemon 是运行底座，不是主品牌
- market 与 gateway 是平台供给层，不是主用户入口

### V4: team

目标：

- 从个人工作系统演化为团队工作系统

可能能力：

- shared runs
- team methods
- approvals
- team budgets
- audit / governance

### V5: managed

目标：

- 演化为托管的复杂工作操作系统

可能能力：

- managed runtime
- long-running background runs
- remote workers / sandboxes
- org-level control plane

说明：

- V5 不应只是“云上跑 agent”
- 它应托管的是 method-bound runs 与复杂工作系统

## Asset Model vs Runtime Fact Model

### Runtime Fact Model

第一阶段运行时事实对象应保持轻量，只表达这次运行中真实发生的事实。

当前接受以下最小“未来友好”字段习惯：

- 稳定 `id`
- `created_at`
- `updated_at`
- `source_ref` 或 `origin`
- 薄 `external_refs`
- 可选 `metadata`

这组字段用于：

- run records
- stage records
- work product records
- usage records

### Asset Model

方法资产层应承载比运行时事实更稳定的结构资产。

当前建议未来方法资产可逐步包含：

- `MethodDescriptor`
- `StageDescriptor`
- `WorkProductTemplate`
- `AcceptanceAsset`
- `WorldModelAsset`

### `WorldModelAsset`

当前接受以下判断：

- `WorldModelAsset` 属于方法论资产层
- 它不是 V5 内部数据模型的别名
- 它的目标是支撑 AI-native agent 或 app 的构建
- managed/runtime/team 等只是它未来的消费者之一

这意味着：

- V1 不需要理解完整 world model
- V1 只需保留薄引用位，例如 `method_ref`、`asset_refs`、`world_model_ref`

## Workbench vs Chief Of Staff

当前接受以下定位：

- `loushang work` 第一版先做个人复杂工作工作台
- 不在第一版主打泛聊天助理
- chief-of-staff 风格的主动行为后置到 daemon 与更成熟的工作图谱之后

因此：

- 第一版是 workbench
- 后续在 continuity、background jobs、agenda、follow-up 成熟后，再逐步获得 chief-of-staff 关系感

## Consequences

### Positive

- `loushang` 对外品牌保持统一
- V1 可以先跑通，不被全量愿景阻塞
- `ppt` 与 `research` 的一级入口价值被保留
- `work` 不会沦为空壳，因为它有明确上位工作台角色
- 运行时对象与方法资产对象的边界更清楚

### Negative

- 第一阶段用户仍会较强地把 `loushang` 感知成 coding 起家的产品
- `work` 在早期可能会显得比 `code` 更抽象
- V2 之前，`ppt / research` 只能先作为命名和入口占位逐步成形

## Next Step

基于当前路线图，后续建议优先继续收敛：

1. `loushang code` 的 V1 最小产品范围
2. `ppt` 与 `research` 的方法匹配与阶段骨架
3. `work` 与 `code / ppt / research` 的 run 关系模型
4. 方法论市场与模型网关的最小业务闭环

# WorkBuddy 对 Loushang 的启示

## 状态

Draft / reference note.

本文档沉淀对 WorkBuddy 产品形态、架构图和公开文档的观察，用作
`loushang.harness`、`loushang.method`、`loushang.work` 后续设计输入。

本文档不是已接受架构决策。若本文档与当前代码、测试、ARD 或 live
architecture note 冲突，以 live source 为准。

## 参考来源

- WorkBuddy 专家和专家团架构图：用户提供的头条图片直链。
- WorkBuddy 专家设计拆解图：用户提供的头条图片直链。
- WorkBuddy 专家团工作方式图：用户提供的头条图片直链。
- WorkBuddy 新建任务栏：
  https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Task-Bar
- WorkBuddy 权限模式：
  https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes
- WorkBuddy 技能：
  https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market
- WorkBuddy 连接器：
  https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector
- WorkBuddy 评论文章：
  https://baijiahao.baidu.com/s?id=1869854506123667076&wfr=spider&for=pc
- OpenClaw GitHub：
  https://github.com/openclaw/openclaw

## 核心判断

WorkBuddy 的价值不在于发明新的底层 Agent 原语，而在于把 Agent 的不确定执行
包装成用户可理解、可管理、可复用的任务产品。

它面向用户暴露的是：

- 新建任务栏
- Ask / Plan / Craft 工作模式
- 专家
- 专家团
- 技能
- 连接器
- 权限模式
- 项目、任务、工作区和产物

它隐藏的是：

- prompt 结构
- context 装配
- tool schema 和工具调用
- 多 Agent 调度
- 工作流状态
- 权限判断和高风险操作 gate

这对 Loushang 的启示是：底座要提供可靠机制，产品适配层要把机制包装成稳定
交付入口。

## 与 Loushang 的分层映射

| WorkBuddy 概念 | Loushang 对应层 | 备注 |
| --- | --- | --- |
| 新建任务栏 | product adapter / prepared turn assembly | UI 和默认值不进 harness |
| Ask / Plan / Craft | product mode + method projection + approval policy | 模式语义由产品解释 |
| 专家 | `loushang.method` | role、workflow、deliverables、success criteria |
| 专家团 | product orchestration / future cowork layer | 运行事实落到 `work` |
| 技能 | `harness.tools.contribution` + product skill adapter | harness 只做中立贡献和解析 |
| 连接器 | product connector adapter + neutral tool contracts | 授权、账号、票据不进 harness |
| 权限模式 | `harness.approval` + product policy | harness 不拥有风险策略 |
| 任务状态和历史 | `loushang.work` | run、event、projection、artifact refs |
| 最终交付 | `work.ArtifactRef` + `harness.presentation` + product renderer | 交付模板属于产品或 method |
| 项目共享配置 | product store / future collaboration product | 指令、专家、技能、连接器、资料库自动注入 |

## 对 Harness 的启示

Harness 应继续保持 product-neutral substrate，而不是变成 WorkBuddy 产品概念的
集合。

适合进入 harness 的机制：

- prepared run / prepared turn contract
- tool definition、tool registry、tool contribution resolver
- neutral diagnostics
- approval request / decision / resolver
- neutral presentation records
- opaque metadata passthrough

不应进入 harness 的产品概念：

- ExpertDefinition
- ExpertSquad
- TaskBar
- Project
- workspace store
- connector authorization
- model defaults
- Ask / Plan / Craft 默认行为
- prompt templates
- role / workflow / deliverable semantics
- agent team scheduling policy

对当前 Slice 1b 的直接结论：`harness.tools.contribution` 是正确方向，但它应只
解决 tool contribution、pack、include、enable/disable、deterministic
resolution 和 diagnostics，不应解释专家、任务、工作流或交付模板。

## 对 Method 的启示

WorkBuddy 的“专家”本质是稳定交付模板，而不是自由聊天 persona。

`loushang.method` 可以吸收这种设计思想，把 method 视为结构化 work contract：

- role：谁在执行这种任务
- workflow：按什么步骤推进
- constraints：哪些边界不能越过
- expected artifacts：应该产出什么
- acceptance expectations：怎样算完成
- guidance：执行过程中的方法论和注意事项
- gates：哪些步骤需要确认、审阅或降级

Method 不应负责执行工具，也不应记录实际产物。它定义 expected artifacts；
`work` 记录 actual artifact refs。

## 对 Work 的启示

WorkBuddy 的任务列表、任务状态、工作区、结果查看和最终交付说明：真实产品需要
可观察、可恢复、可审计的运行事实层。

`loushang.work` 应重点承载：

- `WorkRun`
- `WorkEvent`
- run status projection
- step / plan lifecycle projection
- actual artifact refs
- replay / inspect 所需事件日志
- failure、pending、approval、completed 等状态事实

Work 不应成为 orchestration engine。它记录“发生了什么”，不决定“应该怎样协作”。

## 对 Product Adapter 的启示

WorkBuddy 的新建任务栏可以被理解为一个产品级 `Prepared Task Capsule`：

```text
mode
model
workspace
tool packs / skills
connectors
approval mode
context sources
project defaults
task prompt
```

在 Loushang 中，这类 capsule 应由产品适配层组装，再调用 harness、method、work
等底层能力。

对未来 coding / design / research / ppt / cowork 产品线，推荐方向是：

- 提供用户可理解的 task preset 或 expert-like 入口。
- 按任务启用能力，避免全局注入所有 skills/tools。
- 将工作目录、权限模式、模型选择、上下文来源显式化。
- 把计划、执行、产物和失败状态投影成稳定的 inspect surface。
- 让 product adapter 拥有默认值和 UI 行为。

## Loushang 是否支持完成 WorkBuddy

架构上支持。

当前 Loushang 已经具备或正在建设 WorkBuddy 类产品所需的关键底座：

- `loushang.harness`：prepared run、approval、tools core、presentation 等中立机制。
- `loushang.method`：结构化工作契约、method resource、compile、projection。
- `loushang.work`：运行事实、事件日志、projection、artifact reference 方向。
- `loushang.coding`：产品适配层示例，负责默认工具、策略、session、UI 集成。
- `loushang.tui`：通用终端 UI primitives。
- `loushang.ai`：provider/model/auth 边界。

Loushang 与 WorkBuddy 的差异在于：WorkBuddy 已经是完整产品体验；Loushang 当前
更像可构建多个 WorkBuddy 类产品的分层 substrate。

## Loushang 能否超越 WorkBuddy

有可能，但前提是继续保持边界纪律。

潜在优势：

- `harness`、`method`、`work`、`ai`、`tui`、product adapter 边界更明确。
- `method` 可把专家方法论建模为结构化 contract，而不是只靠 prompt blob。
- `work` 可提供可回放、可审计、可检查的 runtime fact layer。
- harness 可服务 coding、design、research、ppt、cowork 和 OEM 产品，不绑定单一产品形态。
- import-boundary tests 和 slice migration 让长期演进更可控。

当前短板：

- 还没有 WorkBuddy 那样完整的新建任务栏、项目、专家、专家团产品入口。
- connector 授权、项目资产、团队协作、自动化调度仍不是完整产品能力。
- 多 Agent 主理人调度和任务派发还没有成为稳定公共层。
- deliverable-first 的产品体验还需要 method/work/presentation/product adapter 一起补齐。

结论：现在不能说功能已经超越 WorkBuddy；但架构潜力更大，尤其适合做多产品线、
可审计、可扩展的 Agent operating substrate。

## WorkBuddy 是否开源

截至本文档编写时，未找到 WorkBuddy 核心产品的官方开源仓库或开源许可证。
公开资料显示它是 CodeBuddy / 腾讯云代码助手体系下的产品。

需要区分：

- WorkBuddy 核心产品：未见官方开源。
- WorkBuddy Skill 生态：支持上传本地技能包、查找和创建技能，也提到兼容
  OpenClaw 社区技能导入；这是扩展生态开放，不等于核心开源。
- OpenClaw：开源项目，GitHub 仓库公开且标注 MIT License。WorkBuddy 与
  OpenClaw 生态或功能形态相关，不代表 WorkBuddy 本身开源。

## 对近期 Harness 工作的建议

近期仍应推进 Slice 1b：tool contribution resolver。

推荐落点：

- 新增 `loushang.harness.tools.contribution`。
- 定义 neutral `ToolContribution`、`ToolPackDefinition`、resolver result 和 diagnostics。
- 支持 deterministic ordering、pack includes、enable/disable、duplicate 和 missing diagnostics。
- 允许 opaque metadata 透传，但 harness 不解释领域语义。
- coding 通过 adapter 调用 resolver，保持现有行为不变。

明确不做：

- 不迁移 concrete coding tools。
- 不实现 expert / squad / workflow / task bar。
- 不引入 workspace、context、memory、session 等新顶层包。
- 不把 product defaults、prompt templates、model defaults、connector auth 放进 harness。

一条可复用原则：

> Method defines stable work contracts; Work records runtime facts and
> deliverables; Harness provides neutral execution and contribution mechanisms;
> product adapters package them into expert-like user experiences.

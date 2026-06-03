# Loushang 方法论体系参考架构调研

## 状态

Draft.

本调研从方法论体系整体出发，不限定 P3、P4 或某个版本边界。目标是回答：

- Loushang 现有方法元模型已经具备哪些骨架。
- Superpowers、gbrain、gstack、Hermes、Kimi、Dify、LangChain/LangGraph、OpenAI Agents、ADK、OpenClaw、Codex、Pi、Claude Code 等项目能提供哪些参考点。
- 哪些能力应进入 `loushang.method` / `loushang.work` / `loushang.agent.harness`，哪些应作为后续治理、演化或产品层能力。
- `SKILL.md`、`METHOD.md`、`SOUR.md` 等文件标准应如何定位。

本文件不是实现计划，也不要求 P3/P4 一次落地所有能力。

## Loushang 已有方法论骨架

Loushang 当前 `docs/experimental/methodology/` 已经定义了比较完整的骨架：

- 方法元素 taxonomy：`phase`、`activity`、`task`、`role`、`guidance`、`workproduct`。
- 元阶段：`PLAN`、`EXPLORE`、`DESIGN`、`BUILD`、`VERIFY`。这些是价值检查点，不是固定瀑布流程。
- 5+1 元角色：`PLANNER`、`EXPLORER`、`DESIGNER`、`DELIVER`、`VALIDATOR`、`CONDUCTOR`。
- SPEM 风格层级：`Phase > Activity > Task > Step`。
- 方法资源目录：`methods/{phase,activity,task,role,guidance,workproduct}/{name}/SKILL.md`。
- 执行模式：fixed、autonomous、hybrid。
- 方法适配：通用骨架 + domain-specific flesh，允许阶段跳过、合并、扩展。

因此外部项目不应替换这套 taxonomy。更合适的吸收方式是：

- 用外部项目补足资源加载、计划执行、可恢复、评估、演化、channel 触发等机制。
- 保持 `method` 是方法资产与编译层，`work` 是执行与事件层，`harness` 是单 agent turn 层。
- 不把 flow engine、agent framework、TUI queue、memory system 混成一个大包。

## 参考项目矩阵

| 项目 | 可参考层 | 可采纳点 | 应避免或延后 |
| --- | --- | --- | --- |
| Superpowers | 方法资源、执行计划 | 可执行 Markdown plan、步骤验证、检查点、TDD/回归门 | P3 不引入完整 subagent-driven development |
| gbrain | 方法资产治理 | Thin harness, fat skills；resolver；skillpack scaffolding；SkillOpt 需验证门 | 不做隐式自改方法，不把 registry 做成早期包管理平台 |
| gstack | 方法 workflow 与 gate | preflight、freeze、checkpoint、hook、plan-tune | 不把 telemetry/sidebar 产品化系统放进 P3 core |
| Hermes Agent | 自动化触发、批处理、Kanban | cron/webhook/API 作为 channel->work；checkpoint/resume；task/run/event 分离；curator | P3 不复制 Kanban DB 和动态任务图 |
| Kimi CLI | Flow DSL | `type: flow` + Mermaid/D2 可作为可视化/输入格式；BEGIN/END/task/decision 最小子集 | Mermaid 不应成为 canonical internal schema |
| Dify | 工作流运行时 | node execution snapshot、variable/state、child engine、execution limits | 不引入完整 GraphEngine/VariablePool/数据库复杂度 |
| LangChain/LangGraph | 状态图与 checkpoint | StateGraph、START/END、middleware、checkpointer、Mermaid projection | 不把 Python framework 作为 Loushang core 依赖 |
| OpenAI Agents | 多 agent handoff、guardrail、trace | agent = instructions/tools/guardrails/handoffs；handoff input filter；RunState schema version；trace span | 不让 provider-specific SDK 决定方法模型 |
| ADK | 工作流 runtime、评估、服务边界 | node state、interrupt/resume、input/output schema、retry/timeout、artifact/memory/eval service | 不走 code-first 方法定义路线 |
| OpenClaw | 产品化 host/channel/session/skills | gateway/channel/workspace/session/skills 分层；SOUL/AGENTS/USER/MEMORY 文件边界；skill workshop；background tasks | 不把 host/channel 与 Loushang method/work 混同 |
| Codex | Coding harness 与权限 | turn-local input queue、mailbox、approval action、skill telemetry、rollback/replay | 不把 coding CLI 语义硬编码进通用 method |
| Pi | 扩展与轻量 agent 协作 | plan-mode、permission-gate、subagent markdown definitions、resource loader override | 不把方法语义散落在 extension 代码里 |
| Claude Code | 成熟 coding UX 与 skill evolution | skillify、skill improvement hook、agent wizard、permission mode、fork subagent | 不允许主执行链路静默改写 method |

## 建议的 Loushang 方法论体系分层

### 1. Method Asset Layer

负责方法资产本身，核心对象是 `MethodElement`：

- `phase`：价值阶段和检查点，如 `DESIGN`、`VERIFY`。
- `activity`：阶段内可组合的工作活动。简单方法可以省略 activity，但不应把 activity 概念从 taxonomy 删除。
- `task`：可执行任务模板，是 coding 第一版最常用的承载单元。
- `step`：运行时 plan 的展开结果，不一定作为独立资源长期存在。
- `role`：执行者视角、职责、温度、禁忌和产出要求。
- `guidance`：跨任务或跨角色的约束、风格、gate、policy。
- `workproduct`：阶段或任务期望产物，如设计文档、PR、测试报告、审阅意见。

文件标准建议：

- `SKILL.md`：原子方法元素。兼容现有 skill 生态，是最小可执行/可投影单位。
- `METHOD.md`：组合方法、方法包、流程模板或 domain methodology 的 manifest。应该保留，未来用于描述 imports、phase/activity/task 编排、适用条件、版本和演化策略。
- `SOUR.md`：可选的长期角色源文件，适合个人助理、团队角色、组织风格等长期存在且会演化的 role source。它不应替代 `role/SKILL.md`，而是给 role projection 提供长期人格、边界、偏好、授权和演化历史。

`SOUR.md` 的定位要谨慎：

- 它是长期 role source，不是 task，不是 phase，也不是普通 memory。
- 它可以影响 role projection，但不能绕过 `guidance`、approval gate 或 domain policy。
- 它应有版本、来源、更新时间、适用范围和人工确认状态。
- 如果目标只是“人格/灵魂”文件，OpenClaw 的 `SOUL.md` 命名更直观；如果采用 `SOUR.md`，建议明确为 `Source Of User Role` 或 `Source Of Role`，避免语义漂移。

### 2. Method Registry And Resolver Layer

负责发现、索引、过滤和选择方法资产。

可参考：

- OpenClaw skill loading：来源优先级、ignore 文件、diagnostics、frontmatter 校验。
- Pi resource loader override：允许 SDK/host 注入、过滤、替换资源。
- Codex skill telemetry：显式/隐式 skill invocation 应可记录。
- gbrain resolver：不要一次性加载所有方法，按触发条件和上下文选择。

建议能力：

- 多来源加载：project、workspace、user、managed、bundled、plugin。
- 稳定 ID：`loushang://methods/{type}/{id}`。
- 来源优先级和冲突策略：project method > project skill > user/managed/bundled。
- diagnostics：invalid metadata、duplicate id、missing description、unsafe source、version conflict。
- applicability：domain、phase、role、task type、risk、tool requirement、input shape。
- invocation telemetry：explicit、implicit、suggested、auto-selected。

P0-P2 已经证明 `MethodLoader` 和 `MethodRegistry` 可以保持轻量。后续不要急着做完整 marketplace，但要从第一天保留 provenance 和 diagnostics。

### 3. Method Compilation And Projection Layer

负责把方法资产编译成可执行或可投影的结构。

核心分工：

- `MethodCompiler`：`MethodDescriptor/MethodElement -> MethodPlan`。
- `MethodProjector`：`MethodPlan + MethodStep + MethodContext -> MethodProjection`。
- `DomainApp`：把 projection 映射到 domain-specific prompt、tool set、expected artifacts、approval gates。

建议原则：

- `MethodPlan` 是结构化对象，不是 Markdown checklist。
- Markdown、Mermaid、D2 可以作为输入或展示，不是 canonical schema。
- `MethodProjection` 可以是 prompt prefix 的第一版，但接口上应保留 role、phase、activity、task、temperature、allowed tools、expected artifacts、approval gates。
- activity 可以在极简场景省略，但不应永久泛化成 phase。phase 是价值阶段，activity 是阶段内工作组织单元。

参考吸收：

- Superpowers 的 executable plan：每步有动作、验证和预期输出。
- Kimi 的 flow parsing：可支持最小 BEGIN/END/task/decision 图输入。
- LangGraph/ADK/Dify：长期可支持图、checkpoint、condition、join，但早期先支持 fixed linear plan。

### 4. Work Execution Layer

负责运行、事件、日志、恢复和交付。它不拥有方法知识，只执行编译结果。

建议对象：

- `WorkRun`：一次方法指导下的工作运行。
- `WorkStepRun`：计划步骤的运行记录。
- `WorkEvent`：外部可观察事件。
- `EventLogBackend`：append/query/subscribe/replay。
- `ArtifactRef`：产物引用。
- `DeliveryPolicy`：是否立即交付、合并交付、仅最终交付。

参考吸收：

- Hermes batch checkpoint：每个 item/step 可记录进度、失败和重试。
- Hermes Kanban：task/run/event 分离，parent gating、heartbeat、blocked/complete。
- ADK NodeState：status、input、attempt_count、interrupts、resume_inputs、run_id、parent_run_id。
- OpenClaw background tasks：queued/running/succeeded/failed/timed_out/cancelled/lost，completion push，不靠轮询。
- Dify node execution snapshot：每步输入、输出、错误、耗时、限制可追踪。

P3 最小可落地形态：

- fixed linear `MethodPlan`。
- `WorkStepStarted` / `WorkStepCompleted` / `WorkStepFailed`。
- `plan_id`、`step_id`、`method_id` 写入 `WorkRun`/`WorkEvent`。
- 失败可记录，但不需要复杂自动 retry。

### 5. Harness And Agent Layer

负责一次 prepared agent turn、tool call、approval、interrupt、queue。

参考吸收：

- Codex input queue：turn-local pending input 与 inter-agent mailbox 分开。
- OpenClaw steering/follow-up queue：steering 在当前 assistant turn 的 tool calls 完成后进入下一 LLM call。
- Pi plan-mode：只读探索阶段可以由工具 allowlist 和 permission gate 实现。
- OpenAI Agents handoff：handoff 是结构化 tool call，有 input schema 和 input filter。
- Claude Code permission mode：plan/default/accept/bypass 等是 harness policy，不是 method taxonomy。

建议边界：

- `harness` 可以知道 tools、approval、interrupt、turn state。
- `harness` 不应知道 phase/activity/task 的业务语义。
- `method` 通过 projection 指定“建议工具/禁止动作/approval gates”，最终由 `harness` 和 policy 执行。

### 6. Method Governance And Evolution Layer

方法演进不是 role 独有的。至少有三个维度：

- Role evolution：长期角色、个人助理、团队角色的偏好和边界演化，可由 `SOUR.md` / `role/SKILL.md` 承载。
- Method element evolution：task、guidance、phase、workproduct 的改进，如步骤调整、成功标准调整、工具建议调整。
- Execution evidence evolution：WorkRun、EventLog、EvalCase、rubric、artifact outcome 提供证据，但它们自身不应直接变成方法。

参考吸收：

- gbrain SkillOpt：优化必须有验证门和 benchmark。
- Hermes curator：空闲/间隔/干跑/归档不删除/报告。
- Claude Code skillify：从会话提炼 repeatable process，但需要用户确认。
- Claude Code skill improvement hook：运行中发现改进建议，适合 proposal queue，不适合静默落盘。
- ADK eval：EvalCase、Invocation、trajectory、rubric、threshold。
- OpenClaw Skill Workshop：agent 草拟，用户审阅，批准后写入。

建议机制：

- `MethodEvolutionProposal`：记录建议来源、目标文件、修改原因、证据 run/event、风险级别。
- `MethodReviewGate`：人工确认或自动评估通过前不得写入 canonical method。
- `MethodEvalSuite`：每个重要 method 可以绑定 regression cases。
- `archive not delete`：废弃方法先归档，保留 lineage。
- `pin`：关键方法可锁定，禁止自动改写。

### 7. Collaboration Layer

多 agent 协作是方法体系的自然扩展，但不应过早进入 P3 core。

可参考：

- OpenAI Agents：handoff 与 agents-as-tools 的区别。
- ADK Task API / Workflow：delegation、multi-turn task mode、agent as node。
- Hermes Kanban：parent/child task、heartbeat、blocked、claim、handoff metadata。
- Pi subagent：markdown agent definition、parallel/chain、输出上限、abort propagation。
- Claude Code fork subagent：继承父上下文、隔离 worktree、结构化报告、禁止递归 fork。
- OpenClaw multi-agent routing：agent 是 workspace + state dir + auth + sessions 的完整隔离范围。

建议抽象：

- `AgentLane`：一个可调度执行 lane，可能是当前 agent、subagent、remote agent 或 domain agent。
- `Handoff`：角色/任务交接事件，包含 input、expected output、scope、context filter。
- `TaskLedger`：跨 lane 的任务状态账本。
- `CollaborationBus`：event-based communication，不共享所有上下文。

约束：

- 不把 subagent 变成默认执行方式。
- 不让多 agent 共享未过滤的完整 memory/session。
- 不让 role handoff 绕过 permission/guidance/work policy。

### 8. Channel And Automation Layer

方法可以由用户输入触发，也可以由自动化触发。

参考吸收：

- Hermes cron/webhook/API：触发源、prompt、profile、skills、delivery、workdir、silent/no_agent 都结构化。
- OpenClaw cron/webhook/background tasks：调度器和 task ledger 分离。
- OpenClaw session routing：不同 channel/peer/account/session 的隔离策略。

建议原则：

- channel 只负责入口、身份、地址、交付，不理解方法细节。
- automation trigger 产生 `WorkOperation`，而不是直接调用 agent。
- delivery 要有策略：immediate、coalesce、final_only、silent。
- 背景任务应 push completion，不鼓励轮询。

## 关键设计判断

### Activity 不应完全泛化为 Phase

极简实现里可以没有 activity 字段，或让 `activity=None`。但概念上不建议把 activity 删除并泛化为 phase：

- phase 是价值阶段和检查点，例如 DESIGN。
- activity 是阶段内可组合的工作活动，例如 architecture-review、api-design、test-planning。
- task 是可执行任务模板，例如 “为 CLI 参数添加回归测试”。

如果 activity 被 phase 吞掉，后续一个 phase 下的多个活动会只能靠 task/tag 硬撑，method composition 会变差。

### 演进不只属于 Role

role 会演进，method 也会演进，guidance/task/workproduct 也会演进。

更清晰的划分是：

- `SOUR.md` / role：演进“谁在执行、以什么人格/偏好/边界执行”。
- `METHOD.md` / task/guidance/phase：演进“怎么做、按什么流程做、如何判断做完”。
- `MEMORY.md` / session memory：演进“事实、偏好、上下文记忆”。
- `WorkRun/EventLog/Eval`：提供“演进证据”，不直接成为方法。

### METHOD.md 应保留

`SKILL.md` 很适合原子方法元素，但未来组合方法需要更强的 manifest：

- imports：引用哪些 phase/activity/task/role/guidance/workproduct。
- applicability：适用 domain、复杂度、风险、输入类型。
- execution mode：fixed、autonomous、hybrid。
- plan template：固定 skeleton 或可由 conductor 补全。
- gates：进入/退出条件、人类确认点、危险操作。
- evals：绑定回归样例和 rubric。
- evolution policy：是否可自动建议、是否需要人工确认、是否 pinned。

因此 `METHOD.md` 可以成为 Loushang 立标准的机会。早期不用实现完整语义，但文档标准可以先稳定。

### Mermaid 应作为投影格式

Kimi CLI 证明 Mermaid/D2 对用户可读 flow 很有价值。但内部 canonical schema 不建议直接使用 Mermaid：

- Mermaid 解析和语义边界容易受语法变化影响。
- method/work 层需要稳定字段、ID、状态、artifact、gate、retry、approval。
- Mermaid 更适合作为 `MethodPlan` 的 visual projection 或 import adapter。

### Memory、Role、Method 必须分开

OpenClaw 的文件分工提供了很好的反例和参考：

- `SOUL.md`：persona。
- `AGENTS.md`：操作指令。
- `USER.md`：用户画像。
- `MEMORY.md`：长期事实与偏好。
- `skills/`：工具使用和可复用流程。

Loushang 也应保持：

- role source 不等于 memory。
- memory 不等于 method。
- method 不等于 execution history。
- execution evidence 可以推动 method evolution proposal，但不能直接改写 method。

## 建议路线

### M0：冻结方法元素标准

- 明确 `SKILL.md` 原子元素 schema。
- 明确 `METHOD.md` composite manifest 的最小字段。
- 明确 `SOUR.md` 是否采用，以及它和 `role/SKILL.md`、memory 的边界。
- 保持 `phase/activity/task/role/guidance/workproduct` taxonomy。

### M1：补强 Registry / Resolver

- provenance、source priority、diagnostics、conflict strategy。
- exact selection + applicability filter。
- invocation telemetry。

### M2：Fixed MethodPlan

- fixed linear steps。
- step lifecycle work events。
- step expected artifacts / success criteria。
- method projection 仍可 prefix 到单 agent turn。

### M3：METHOD.md Composite

- 支持 imports 和 plan template。
- 支持 phase/activity/task 层级。
- 支持 Mermaid/D2 projection 或 import adapter。

### M4：Governance And Evolution

- method evolution proposal。
- review gate。
- eval/rubric。
- archive/pin/version lineage。

### M5：Hybrid Conductor

- CONDUCTOR 生成或补全 plan flesh。
- 决策日志结构化：reasoning、confidence、next role、expected output、switch type。
- 规则 + LLM 混合，而不是纯 prompt 自由发挥。

### M6：Multi-Agent Collaboration

- AgentLane、Handoff、TaskLedger、CollaborationBus。
- context filter、workspace isolation、permission inheritance。
- parent/child lineage 和 terminal delivery。

### M7：Automation And Channel Integration

- cron/webhook/API triggers -> WorkOperation。
- DeliveryPolicy。
- background task ledger。
- cross-channel session isolation。

## 对 P3/P4 的含义

P3 不需要做完整方法论体系，但 P3 的 schema 要避免未来返工：

- `MethodPlan` 保留 `phase/activity/task` 字段。
- `MethodStep` 保留 `role` / `role_variant` / `expected_artifacts` / `success_criteria`。
- `WorkRun` / `WorkEvent` 记录 `method_id`、`plan_id`、`step_id`。
- `MethodProjection` 保留 `meta_role`、`temperature`、`allowed_tools`、`approval_gates`。
- 内部 canonical plan 不用 Mermaid，但可导出 Mermaid。

P4 可以开始多 agent，但应先完成：

- work event replay 可靠。
- step lifecycle 稳定。
- approval/gate 语义清楚。
- method evolution 不会静默改写 canonical resources。

## 结论

Loushang 的优势不应是“再造一个 flow engine”或“再造一个 coding CLI”，而是把方法论作为第一等资源：

- 用 SPEM 风格 taxonomy 保持方法资产可组合。
- 用 `work` 把执行变成可观察、可恢复、可审计。
- 用 `harness` 保持单 turn、tool、approval 的稳定边界。
- 用 `METHOD.md` 表达组合方法，用 `SKILL.md` 承载原子方法元素。
- 用 `SOUR.md` 或类似角色源文件承载长期角色演化，但不混同 memory/method/work。
- 用治理层处理方法演化，而不是让 agent 在执行中隐式自改。

这样 Loushang 可以兼容现有 skill 生态，同时逐步发展出比单一 agent 工具更清晰的方法论操作系统。

# P3 Fixed MethodPlan Flow 调研

## 状态

Draft; historical research note.

本调研用于支持 issue #46 的 P3 设计刷新。目标不是把外部 workflow
系统搬进 `loushang`，而是在 P0-P2.7 已完成的边界上判断：

- P3 是否应该引入 fixed multi-step `MethodPlan`。
- `MethodPlan` 与 work/event/coding domain app 应如何衔接。
- 哪些 flow 能力应在 P3 做，哪些应推迟到 P4+。

截至 2026-06-04，P3 的大部分底座已经落到 `main`：fixed MethodPlan
编译、work plan/step 生命周期、step policy/deviation metadata、tool approval
audit events，以及 coding domain 非交互路径的逐 step 执行。本文保留为设计
来源和取舍记录，不再代表当前实现清单。

## 调研时 Loushang 约束

P0-P2.7 当时形成以下约束：

- `loushang.method` 负责方法资源、选择、编译和投影，不负责执行。
- `loushang.coding.domain` 负责把 method projection 映射成 coding prompt。
- `loushang.work` 负责 `WorkRun`、`WorkEvent`、event log 和 replay 入口。
- `AgentSession` 仍保持原有单 turn 执行语义。
- `CodingDomainApp.prepare_turn(...)` 当时只消费 `plan.steps[0]`，并把 guidance
  prefix 到一次 user prompt。
- `WorkRun` 当时只记录 `method_id`，还没有 `plan_id`、`step_id` 或 step lifecycle。

因此 P3 的第一原则是：在不破坏单 turn 快速路径的前提下，把“一个 method 可以编译成固定步骤计划”
变成可观察、可回放的 work 层能力。

## 调研对象

### Superpowers

参考文件：

- `/home/dev/workspace/superpowers/skills/writing-plans/SKILL.md`
- `/home/dev/workspace/superpowers/skills/subagent-driven-development/SKILL.md`

可采纳：

- 计划首先应是线性、可执行、可验证的步骤列表。
- 每一步应有明确动作、预期输出和验证方式。
- 检查点、提交、回归验证是计划质量的一部分，不只是执行后的附属记录。

不采纳到 P3：

- 不在 P3 引入 subagent 调度。
- 不把计划写成只适合人工阅读的 Markdown checklist；Loushang 需要结构化 plan，
  Markdown/Mermaid 可以作为投影或资源格式。

### gbrain

参考文件：

- `/home/dev/workspace/gbrain/docs/ethos/THIN_HARNESS_FAT_SKILLS.md`
- `/home/dev/workspace/gbrain/docs/guides/scaling-skills.md`
- `/home/dev/workspace/gbrain/docs/designs/SKILLPACK_REGISTRY_V1_SPEC.md`
- `/home/dev/workspace/gbrain/docs/guides/skillpacks-as-scaffolding.md`
- `/home/dev/workspace/gbrain/docs/guides/skillopt.md`
- `/home/dev/workspace/gbrain/skills/skill-optimizer/SKILL.md`

可采纳：

- “Thin harness, fat skills”：runtime/work/harness 要薄，方法资产本身承载主要知识。
- Skill/Method 资源应可被用户拥有、复制、改写和演进。
- 自进化需要验证门槛和基准，不应隐式修改 method 资源。
- resolver/trigger 可以后续用于自动选择 method，但 P3 不必做智能选择。

不采纳到 P3：

- 不做自动 skill/method 优化。
- 不做长期 role 记忆或个人助理画像写入。
- 不把 method registry 做成完整包管理器。

### gstack

参考文件：

- `/home/dev/workspace/gstack/SKILL.md`
- `/home/dev/workspace/gstack/spec/SKILL.md`
- `/home/dev/workspace/gstack/autoplan/SKILL.md`
- `/home/dev/workspace/gstack/plan-tune/SKILL.md`
- `/home/dev/workspace/gstack/freeze/SKILL.md`
- `/home/dev/workspace/gstack/docs/designs/SIDEBAR_MESSAGE_FLOW.md`

可采纳：

- 方法执行需要 preflight、gate、review、checkpoint 等外围约束。
- flow 的状态应可显示、可检查、可恢复，而不是埋在 prompt 里。
- hooks/gates 更适合作为 step metadata 与 work events，而不是 P3 核心控制流。

不采纳到 P3：

- 不引入 telemetry、learning、sidebar message flow 等产品化系统。
- 不把 P3 设计成完整 agent coordination runtime。

### Hermes Agent

参考文件：

- `/home/dev/workspace/hermes-agent/README.md`
- `/home/dev/workspace/hermes-agent/hermes-already-has-routines.md`
- `/home/dev/workspace/hermes-agent/batch_runner.py`
- `/home/dev/workspace/hermes-agent/tests/test_batch_runner_checkpoint.py`
- `/home/dev/workspace/hermes-agent/cron/jobs.py`
- `/home/dev/workspace/hermes-agent/cron/scheduler.py`
- `/home/dev/workspace/hermes-agent/hermes_cli/webhook.py`
- `/home/dev/workspace/hermes-agent/hermes_cli/kanban_db.py`
- `/home/dev/workspace/hermes-agent/hermes_cli/kanban_decompose.py`
- `/home/dev/workspace/hermes-agent/agent/prompt_builder.py`
- `/home/dev/workspace/hermes-agent/agent/curator.py`
- `/home/dev/workspace/hermes-agent/skills/devops/kanban-orchestrator/SKILL.md`
- `/home/dev/workspace/hermes-agent/skills/devops/kanban-worker/SKILL.md`

可采纳：

- Scheduled routines / webhook / API triggers 本质上是 `channel -> work`
  的自动触发入口：触发源、prompt、skills、delivery、workdir、profile 等都应结构化记录。
- Cron job 支持 script pre-processing、`context_from`、`no_agent`、`[SILENT]`
  抑制交付和 delivery target，这些对后续 `SurfaceRequest`、`DeliveryPolicy`
  和 background work 很有参考价值。
- `batch_runner` 的 checkpoint/resume 值得借鉴：增量 checkpoint、失败项可重试、
  按内容扫描已有输出恢复，避免只依赖易漂移的 index。
- Kanban 的 task/run/event 分离、parent gating、heartbeat、blocked/complete、
  structured handoff metadata 和 audit event 适合 P4 多 agent，但 P3 可以先借鉴
  step lifecycle 和 handoff metadata 的形状。
- `kanban_decompose` 说明“计划生成”可以独立于执行：先生成 2-6 个任务图，再原子落库。
  P3 可以借鉴“先 compile plan，再执行”，但计划应固定，不在执行中动态改图。
- Curator 的 self-improvement gate 值得保留为长期方向：idle/interval/dry-run、
  archive instead of delete、pin、pre-run snapshot、report。Method evolution 应是受控后台任务，
  不应混进 fixed plan executor。

不采纳到 P3：

- 不引入 Hermes Kanban 的完整 SQLite board、dispatcher、profile fleet 或 multi-board。
- 不做 cron/webhook 平台，也不把 P3 变成 routines 系统。
- 不做 LLM decomposer 生成动态 task graph。
- 不做 goal-mode judge loop。
- 不做 curator 式自动 skill/method 整理。

### Kimi Agent Flow

参考文件：

- `/home/dev/workspace/kimi-cli/klips/klip-10-agent-flow.md`
- `/home/dev/workspace/kimi-cli/tests/core/test_agent_flow.py`

可采纳：

- `type: flow` 的 SKILL 资源扩展思路有价值。
- 从 Markdown 中解析 Mermaid/D2 flow 可作为资源兼容路径。
- 最小 flow 可以只支持 BEGIN、END、task、decision 和 labeled edge。
- `max_moves`、无效选择重试等安全阈值适合 P4+ branching flow。

不采纳到 P3：

- P3 不做 LLM-driven decision branching。
- P3 不把 Mermaid/D2 作为内部 canonical schema。
- P3 不支持循环、条件边和复杂 graph execution。

### Dify Workflow

参考文件：

- `/home/dev/workspace/dify/api/core/workflow/workflow_entry.py`
- `/home/dev/workspace/dify/api/core/workflow/node_runtime.py`
- `/home/dev/workspace/dify/api/repositories/api_workflow_node_execution_repository.py`
- `/home/dev/workspace/dify/api/core/repositories/sqlalchemy_workflow_execution_repository.py`

可采纳：

- workflow run 和 node/step execution 应分开记录。
- 每个 step execution 应有 status、index、started_at、finished_at、elapsed 等可观测数据。
- workflow 应有执行上限，避免无限执行。

不采纳到 P3：

- 不引入 GraphEngine、VariablePool、数据库 execution repository。
- 不做 loop/iteration/child workflow。
- 不把业务 node 类型硬编码进 work 层。

### LangChain / LangGraph

参考文件：

- `/home/dev/workspace/langchain/libs/langchain_v1/langchain/agents/factory.py`
- `/home/dev/workspace/langchain/libs/core/langchain_core/runnables/graph.py`

可采纳：

- state graph、checkpoint、middleware 是成熟 agent workflow 的长期方向。
- graph 可以投影为 Mermaid，用于查看和调试。

不采纳到 P3：

- workspace 中没有独立 LangGraph 源码，P3 不依赖 LangGraph 语义。
- 不在 P3 引入 state graph/checkpointer/middleware 链。
- Mermaid 只作为展示或资源解析格式，不作为内部执行模型。

### Mermaid

本地没有单独 Mermaid 仓库；调研主要来自 Kimi 的 Mermaid flow 解析和 LangChain
的 graph 可视化输出。

可采纳：

- Mermaid 适合作为 `MethodPlan` 的查看/导出格式。
- 如果未来 `METHOD.md` 中出现 flow diagram，可以先解析有限子集。

不采纳到 P3：

- 不支持完整 Mermaid 语法。
- 不让 Mermaid 控制 runtime 语义。

## P3 建议决策

### 1. P3 做 fixed linear plan，不做 full workflow graph

P3 的最小能力应是：

```text
MethodDescriptor
  -> MethodCompiler
  -> MethodPlan(mode="fixed", steps=[step1, step2, ...])
  -> Work executes step1..stepN
  -> each step becomes one prepared coding turn
```

P3 不做：

- branching decision
- loops
- dynamic graph rewrite
- subagent lanes
- cross-domain orchestration
- variable pool
- automatic method evolution
- scheduled routines / webhook triggers

这样能验证“方法指导多步骤 coding”的核心假设，同时避免把 P3 做成 Dify/LangGraph
级别的 workflow runtime。

### 2. Internal schema 使用 MethodPlan，Mermaid 只是投影

`MethodPlan` 应保持 Loushang 内部 canonical schema。Mermaid/D2 可以：

- 从 `METHOD.md` 或 `SKILL.md` 中作为可选资源内容被解析。
- 从 `MethodPlan` 导出用于预览。
- 在 P4+ 支持有限 flow graph。

但 P3 不能让 Mermaid 语法决定执行模型。

### 3. METHOD.md 可以保留为未来标准入口

P1 已支持 `skills/**/SKILL.md` 和 `methods/**/SKILL.md`，这保证了现有 skill
生态兼容。未来仍建议保留 `METHOD.md`，但它不应在 P3 成为必需条件。

建议标准：

- `SKILL.md`：单个可复用方法元素，适合 `task`、`role`、`guidance`、
  `phase`、`workproduct`。
- `METHOD.md`：组合型方法入口，适合声明一个完整 method、默认 phase/order、
  固定 plan、资源依赖和导出视图。
- `SOUR.md`：如果保留，应定位为长期演化 role/persona/source-of-role 资源，
  不是 P3 fixed plan 的执行格式。

P3 可以先实现 `SKILL.md` 编译 fixed plan 的能力，同时把 `METHOD.md` 列为
P3.5/P4 的资源标准化工作。

### 4. Step lifecycle 应落在 work 层

`method` 编译 plan，但不执行 plan。P3 应让 `work` 对 step lifecycle 可观察：

```text
WorkRunStarted
WorkStepStarted
ContentDelta / ToolCallStarted / ToolCallCompleted / ...
WorkStepCompleted
WorkStepFailed
WorkRunCompleted
```

每个 step event 至少携带：

- `method_id`
- `plan_id`
- `step_id`
- `step_index`
- `step_title`

这比只在 prompt 中写入 “Step 1/3” 更稳，因为 replay/search/audit 不需要解析自然语言。

### 5. CodingDomainApp 负责准备 step，不负责调度全 plan

P2 的 `CodingDomainApp.prepare_turn(...)` 已经验证了 method projection 到 prompt
的边界。P3 建议新增或扩展：

```python
prepare_step(request, plan, step) -> CodingDomainPreparedTurn
```

调度顺序由 `work` 控制：

- `work` 接收 operation。
- `work` 选择/编译 method plan。
- `work` 按 step 顺序调用 domain app 准备 prompt。
- `work` 逐步交给 harness/AgentSession 执行。

这样 domain app 不会变成 workflow manager，method 也不会变成 runtime。

### 6. Single-turn 是 one-step fixed plan 的退化形态

P3 不应分裂 single-turn 和 fixed-plan 两条路径。建议语义：

- `mode="single_turn"`：P1/P2 兼容路径，可视为一个 `main` step。
- `mode="fixed"`：按顺序执行多个 step。

公共事件和 metadata 应统一携带 plan/step 信息；single-turn 可以使用：

```text
plan_id = method_id + ":single_turn"
step_id = "main"
step_index = 0
```

如果没有 method，则仍保持 P0/P2.7 当前行为，不强行生成 plan。

### 7. Gates/hooks 先作为 metadata，不作为核心控制流

P3 可以允许 step metadata 包含：

- `approval_gates`
- `expected_artifacts`
- `verification`
- `preflight`

但 P3 不应实现完整 hook lifecycle。可做的最小落点是：

- projection 中继续暴露 `approval_gates`。
- work event payload 记录 gate metadata。
- 对危险操作仍沿用现有 approval/policy 机制。

## 建议的最小数据模型

当前 `MethodStep` 已有：

```python
@dataclass(frozen=True)
class MethodStep:
    id: str
    title: str
    executor: str
    role_variant: str | None = None
    projection: Mapping[str, object] = field(default_factory=lambda: _EMPTY_METADATA)
```

P3 可先不新增复杂字段，把 step 细节放到 `projection` / `metadata` 中；如果需要更清晰，
可以 additive 增加：

```python
kind: str = "turn"
description: str | None = None
expected_artifacts: tuple[str, ...] = ()
metadata: Mapping[str, object] = field(default_factory=lambda: _EMPTY_METADATA)
```

`WorkRun` 可 additive 增加：

```python
plan_id: str | None = None
current_step_id: str | None = None
```

`WorkEvent.payload` 对 step events 增加：

```python
{
    "method_id": "...",
    "plan_id": "...",
    "step_id": "...",
    "step_index": 0,
    "step_title": "...",
}
```

暂不建议在 P3 引入 public `TaskFlow`、`AgentLane`、`CollaborationBus`。

## P3 实施切片建议与当前状态

以下切片是调研时建议。合入 `main` 后，P3.1-P3.3 已基本落地，剩余重点是
失败语义和 UI/RPC 可见性硬化。

### P3.1 MethodPlan fixed schema - landed

- 让 `MethodCompiler` 能从 method metadata/body 生成多个 `MethodStep`。
- 支持 `mode="fixed"`。
- 保持 P1/P2 single-turn compiler 行为不变。
- 测试 `MethodPlan` 解析、fallback、无 method 情况。

### P3.2 Work step lifecycle - landed

- 增加 `WorkStepStarted`、`WorkStepCompleted`、`WorkStepFailed`。
- event log 可回放完整 step 序列。
- `WorkRun` 或 metadata 可记录 plan/step 状态。
- 可借鉴 Hermes batch/Kanban：失败 step 可重试，step 结果和结构化 handoff
  应作为事件/metadata 保存，而不是只写在自然语言回复里。

### P3.3 CodingDomain step preparation - landed for non-interactive CLI

- 新增 `prepare_turns(...)` 或等价 facade。
- 每个 step 仍映射为一次现有 AgentSession turn。
- 不改 AgentSession 的核心 prompt assembly。

### P3.4 CLI/manual validation path

- 优先覆盖 headless `-p` / `--mode print` / JSON 路径。
- 手工验证一个固定两步 coding method。
- TUI/RPC 暂不进入 P3 首批。

### P3.5 Optional Mermaid preview

- 把 `MethodPlan` 导出 Mermaid，便于 review。
- 不做 Mermaid 执行器。

## 开放问题

1. P3 的 fixed plan 资源应优先从 `SKILL.md` frontmatter、body 约定，还是新增
   `METHOD.md` 组合入口？
2. step event 命名使用 `WorkStepStarted` 还是 `PlanStepStarted`？
3. `work` 是否负责 method select/compile，还是继续由 `CodingDomainApp` 内部完成？
   架构上更推荐 work 控制 plan lifecycle，domain app 准备具体 turn。
4. step 间上下文传递是否只依赖现有 session transcript？P3 建议先如此，暂不引入 variable pool。
5. P3 是否允许 verification step 自动执行命令？建议首批只作为普通 coding turn 或 metadata，
   不新增自动命令执行器。

## 结论

P3 应从“固定线性 MethodPlan”开始，而不是从 workflow graph 开始。

最值得采纳的是：

- Superpowers 的线性可执行计划与验证意识。
- gbrain 的 thin harness / fat skills 和 method 可演进但需 gate 的原则。
- gstack 的 gate/checkpoint 作为外围约束的思路。
- Hermes 的 routines、checkpoint/resume、Kanban handoff、curator gate 经验。
- Kimi 的 `type: flow` 与有限 Mermaid 解析经验。
- Dify 的 step execution 可观测性。
- LangChain/LangGraph 的长期 state graph/checkpoint 方向。

最应该摈弃或延后的，是把 P3 做成 full graph runtime、LLM decision flow、
variable pool、多 agent orchestration、自动自进化或产品化 workflow 平台。

P3 的正确落点是：`MethodPlan(mode="fixed")` + work step lifecycle +
coding domain step preparation。这样既能服务 coding domain 的快速可用，也不会堵死 P4+
多 agent、跨 domain、branching flow 和自进化 method 的演进空间。

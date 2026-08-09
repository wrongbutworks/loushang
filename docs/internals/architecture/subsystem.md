# Loushang Subsystems

## Scope

本文档定义 `loushang` 的主要子系统及其职责边界。
它关注系统分工，不展开实现细节、类型系统或边界协议。

## Subsystem List

当前已落地的核心包级子系统包括：

- `loushang.ai`
- `loushang.agent`
- `loushang.channel`
- `loushang.harness`
- `loushang.harnesstui`
- `loushang.coding`
- `loushang.method`
- `loushang.tui`
- `loushang.harnesswork`
- `loushang.work`（迁移期 compatibility/integration namespace）

当前已落地的支撑/实验性包包括：

- `loushang.foundation`
- `loushang.ontology`

`loushang.runtime` 不再作为子系统保留。若某个 worktree 中仍存在
`src/loushang/runtime`，它只是待删除的旧 command/effect 临时路径；迁移目标是
`loushang.harness.commands`，不保留 runtime shim。跨产品 host / adapter /
command substrate 的目标归属是 `loushang.harness`，见
[ARD-002: Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。

目标产品线概念包括：

- `loushang.design`
- `loushang.research`
- `loushang.ppt`
- `loushang.cowork`

`loushang.channel` 已有对应 Python package implementation。现有
`loushang.coding.mode.RpcMode` 仍是 Coding-local transitional adapter；它的
命令表与 UI payload 不属于长期 Channel core。

## Subsystem Responsibilities

### loushang-foundation

产品无关、只依赖 Python 标准库的共同底座。当前 canonical implementations 是：

- `loushang.foundation.json`，负责唯一的严格 `JSONValue` algebra、校验、复制
  与编码；
- `loushang.foundation.observability`，负责日志上下文、问题记录、trace/debug
  事件、sink 路由、运行时配置与运行时身份。

旧顶层包 `loushang.protocol` 和 `loushang.observability` 已退出；所有调用方直接
使用上述 canonical owners。Foundation 不负责 Product 策略、Agent/Harness 编排、
Work 权威事件、Channel schema，或者为诊断投影之外的新 wire schema 提供任意
Python 对象到 JSON 的容错转换。

### loushang-ontology

可选的 operational ontology infrastructure。它把 Product / Domain adapter
提供的版本化 schema 和 immutable FactBatch 转成受约束、可重建的语义对象图，
并返回稳定对象 ID、typed query、不可变投影构建坐标与独立 freshness diagnostics。

```text
Product / Domain Adapter
          | FactBatch
          v
     +----------+-------> Memory / SQLite v2 FactStore
     | Ontology |-------> immutable ProjectionSnapshot
     +----------+-------> Memory / SQLite ProjectionStore
          |
          +-------------> typed QueryResult

Ontology -> Foundation JSON
```

Ontology core 不依赖 Harness、HarnessWork、Agent、AI、Channel 或 Product。
当前没有 ontology/HarnessWork Action bridge；未来 Action contract 成立后由
Product adapter 同时依赖两者，HarnessWork 不反向拥有 ontology 类型。

当前已完成 schema kernel、Wave 2A 和 Phase 2：除 immutable
Fact/Provenance、双时间选择和 typed query 外，还提供独立的 Fact/Projection
端口、纯 commit planner、不可变 ProjectionSnapshot、全量原子 replace，以及互不
委托的 Memory/SQLite adapters。SQLite 当前格式直接为带
`storage_layout=phase2` 的 v2；不提供 v1 或旧 v2 reader/migrator。
ARD-003 的首个 correctness slice 还提供原子 `FactSelection`、纯 freshness evaluator
和 SQLite 单读事务快照。当前 Fact-only runtime 仍只从 FactStore 物化；目标架构允许
后续 mapped source input 按声明的 `StateAuthority` 参与物化。`ontology.core`、直接对象
mutation 与兼容 facade 已退出源码和公共面。
它尚不包含 OWL/SHACL、Action/Decision runtime、SDK 生成、分布式 serving 或行业领域包。详见
[Loushang Ontology Architecture](./ontology/README.md)。

### loushang-ai

模型接入、统一调用与流式语义层。

负责：

- `model` 抽象
- 统一 AI 调用入口
- `provider` 适配
- 流式输出协议
- tool schema / tool call / tool result message 语义
- 与上游模型 API 的能力映射

不负责：

- `Agent` 生命周期
- tool orchestration policy
- tool execution scheduling
- tool execution hook policy
- 边界协议建模

### loushang-agent

agent 运行内核。

负责：

- `Agent`
- `AgentLoop`
- `AgentMessage`
- `AgentEvent`
- `AgentTool`
- `AgentContext`
- `AgentState`

不负责：

- provider 接入细节
- prepared agent run contract
- UI 渲染
- 跨边界 transport
- coding / design / research / ppt / cowork 产品语义
- work / method 投影语义

### loushang-harness

跨产品的 product-adapter substrate。它在唯一 prepared agent run contract
之上组合 Product-neutral runtime、Session、Conversation、Transcript、Context、
Tools、Policy、Approval、Sandbox、Capability、Host、Events、Continuity 和
Workspace 机制。完整当前 owner 以
[Harness Current Owner Map](./harness/current-owner-map.md) 为准。

负责：

- `AgentRunSpec`
- `AgentRunResult`
- `run_agent()`
- headless agent run 编排
- runtime cancellation、retry/scheduling、Runtime Profile resolution 与 binding
- Session lifecycle、conversation repository、transcript、context packing 与 replay
- tool authoring/hosting、Policy、Approval、Sandbox 和 execution-profile mechanics
- resources、extensions、capabilities 与 scoped activation
- product-neutral adapter、host、CLI、events、presentation、diagnostics、continuity
  和 workspace contracts
- command/effect value objects, such as `loushang.harness.commands`

不负责：

- `Agent` 生命周期
- low-level agent loop ownership
- coding / design / research / ppt / cowork 产品语义
- coding command catalog、command handlers、slash parsing 或 command execution policy
- work / method 投影语义
- provider auth / model default persistence
- TUI render loop、layout、input 或 screen state

`loushang.harness` 位于 low-level agent loop 之上，依赖 `loushang.agent` 并
复用现有 loop，不另写第二套 loop。`loushang.agent` 不依赖
`loushang.harness`。`AgentRunSpec`、`AgentRunResult` 和 `run_agent()` 是唯一
prepared-run contract，不引入第二套 `HarnessRunSpec`。原
`src/loushang/agent/harness` / `loushang.agent.harness` compatibility path 已删除；
新代码应从 `loushang.harness` import。详见
[Agent Harness and Product Adapter Boundaries](./agent/ARD-001-agent-harness-and-product-adapters.md)
和
[Harness Product Adapter Substrate](./agent/ARD-002-harness-product-adapter-substrate.md)。
后续 harness 迁移准则、shared capability 边界和 coding 迁移 inventory 见
[Loushang Harness Architecture](./harness/README.md)。

### loushang-channel

边界协议与 transport 层。该源码包已落地，并保持为由 Product host ports
注入业务操作的 transport-first 层。

当前负责：

- `WorkOperation` / `WorkEvent` 和已投影 `RuntimeEventView` 的边界值契约
- JSONL envelope/framing 与严格 wire values
- request / response correlation
- accepted ACK 与随后到达的 event delivery
- 当前 `rpc_jsonl` adapter

目标扩展包括 capability negotiation、interaction request/response、subscription
cursor/resume，以及按需求增加的 in-process、IPC、HTTP/WebSocket 等 adapter。
这些目标能力不能当作当前已实现事实。

不负责：

- agent 内核状态机
- 本地 UI 组件实现
- 方法层调度
- coding / design / research / ppt / cowork 产品内部 session
- 产品 adapter 注册之外的业务执行

`channel` 可以服务 TUI、WebUI、AppUI、SDK host 和 RPC client，但不是所有
Session/App 操作的强制总线。它承载选定的 `WorkOperation` / `WorkEvent` 和
已完成产品投影的 `RuntimeEventView`；具体 Product adapter 由 host 装配，
Channel 不解释或产生该 view，也不拥有 Work/Session truth。

### loushang-tui

通用终端 UI 基础层。

负责：

- prompt / composer / toolbar / terminal output 等交互原语
- keybinding / history / TTY fallback 等终端交互能力
- 真实 terminal scrollback 与 transient composer 的协调
- 为产品适配层提供可复用的终端 UI primitives
- render planning、terminal operations、diagnostics 和性能预算
- product-neutral terminal playback、scenario suite 和 artifact mechanics

不负责：

- agent 内核语义
- provider 接入
- 方法层定义
- coding session/runtime 语义
- coding-specific model / tool / diagnostics policy

相关文档：

- [Loushang-TUI Architecture](./tui/README.md)
- [Terminal Playback Harness](./tui/native-terminal-core/key-designs/KD-010-terminal-playback-harness.md)

### loushang-harnesstui

Harness conversation contract 与通用 TUI 之间的 product-neutral composition
层。它可以同时依赖 `loushang.harness` 和 `loushang.tui`，但二者都不反向依赖
它；它也不得依赖 `loushang.coding`、AI provider 或 Product policy。

负责：

- neutral conversation snapshot/event 到 TUI records、surfaces 和 status 的投影
- conversation input、queue、abort/steer/follow-up 和 approval presentation routing
- transcript reader、tool transcript、settings/selection/surface 等共享交互
- Agent-free neutral conversation ports，以及可选 Agent binding profile
- 基于 neutral ports 的 direct render、decoded-input 和 screen-loop playback
- playback conversation state、routed action 和 terminal artifact 的组合证据

不负责：

- terminal decoding/render-loop/terminal-write 内核
- Harness Session、Conversation 或 Work 的权威状态
- Coding intent、prompt、tool policy、模型选择策略或最终 Product copy
- 第二套 Agent loop、conversation persistence 或 transcript renderer

相关文档：

- [Loushang Harness TUI](./harnesstui/README.md)

### loushang-method

方法层。

负责：

- `skill`
- `MethodDescriptor`
- `MethodPlan`
- `MethodStep`
- `MethodProjection`
- method resource loading
- fixed method compilation
- `guidance`
- `work product`
- 方法元与投影关系

不负责：

- 底层模型接入
- 边界协议承载
- TUI 交互实现
- 通用 work lifecycle
- 普通产品 turn 的强制执行路径

`method` 是可选的结构化工作组织层。产品线可以在 plan / guided / staged
workflows 中使用 `method`，但轻量 turn 可以直接使用 `loushang.harness` 和
`work`。

### loushang-harnesswork / loushang-work compatibility

`loushang.harnesswork` 是可选的跨产品持久履约扩展。它接受具有可判定终局的业务意图，
并拥有该承诺的产品中立运行事实、事件日志与 run projection。迁移期间
`loushang.work` 对已迁 kernel 提供 forwarding，并暂时保留 plan、CLI 和 Agent/session
integration surfaces。

负责：

- `WorkOperation`
- `WorkRun`
- `WorkEvent`
- `ArtifactRef`
- artifact references / work product projections
- work event log
- plan/step lifecycle projection
- method run replay / inspect 的基础语义

不负责：

- coding-specific tool policy
- method resource 编译
- TUI 呈现
- 外部 transport
- coding / design / research / ppt / cowork 产品语义

HarnessWork 是 coding、design、research、ppt、cowork 等产品线共享的业务工作抽象。
Method 可选；选用 Method 时，Work 拥有编译后 plan 的一次真实履约。它不依赖这些
产品线，也不依赖 `method` 类型。

详细边界、状态机和 SPEM 2.0 对齐关系参见
[Loushang Work Architecture](./work/README.md)。
逐文件 owner 和兼容门禁见
[HarnessWork Migration Ledger](./harnesswork/migration-ledger.md)。

Artifact 分层规则：

- `method` 定义 expected artifact，即结构化工作“应该产出什么”
- `work` 记录 actual artifact reference，即“实际产出了什么、在哪里、状态如何”
- `coding` / `design` / `research` / `ppt` / `cowork` 定义具体 artifact 类型、内容、
  加载、渲染、校验和物化逻辑

因此 `work` 层优先引入 `ArtifactRef`，而不是抽象 `Artifact` ABC。若未来需要
统一加载或渲染行为，应通过 provider/protocol 接口扩展，不把产品行为塞进
`work`。

### loushang-coding

面向 coding 场景的产品装配层。

负责：

- 默认工具
- 默认策略
- coding workflow
- CLI 入口
- 与 `tui`、`method`、`work` 的产品化集成
- transitional RPC/JSONL mode adapter
- `loushang.coding.ui` 终端产品适配层
- session/runtime 与 terminal UI 的交互编排

不负责：

- 通用模型协议定义
- agent 核心类型系统
- 通用边界协议定义
- 通用 terminal UI primitives

`coding` 可以直接依赖 `loushang.harness` 处理轻量 coding turn；只有被受理为持久
业务承诺的工作才进入 `work`，其中需要结构化 / guided 方法的工作再选择性消费
`method`。

## Layer Relationship

当前 V1 coding 产品的主链路为：

```text
loushang.coding
  -> loushang.harness
  -> loushang.agent
  -> loushang.ai
```

相邻集成链路为：

```text
loushang.method -> Product adapter -> loushang.harnesswork
loushang.coding.adapters.harnesswork -> loushang.harnesswork
loushang.channel.adapters.harnesswork -> loushang.harnesswork
loushang.coding.ui -> loushang.coding feature-local TUI adapters
loushang.coding.ui -> loushang.harnesstui -> loushang.tui
loushang.coding feature-local TUI adapters -> loushang.harnesstui
```

跨产品执行目标链路为：

```text
loushang.ai
  <- loushang.agent

loushang.agent
  <- loushang.harness
  <- loushang.coding / loushang.design / loushang.research / loushang.ppt / loushang.cowork
```

跨产品工作抽象链路为：

```text
loushang.method
  -> Product Work Preparer, only for structured work
  -> loushang.harnesswork

loushang.coding / loushang.design / loushang.research / loushang.ppt / loushang.cowork
  -> Product Work Preparer
  -> loushang.harnesswork
```

长期目标边界为：

```text
external host/client
  -> embedded host or AppService
      -> Product Session binding -> loushang.harness
      -> Product Work Preparer -> loushang.harnesswork
           -> Product Work Executor -> loushang.harness
```

轻量 Session turn 与受理后的 structured Work 是显式不同的路径；并非所有
Product turn 都必须经过 `channel`、`work` 或 `method`。`channel` 是可选的
operation/event 边界，不是 Product runtime 的统一入口。Product 本身承担领域
语义，长期目标不再引入独立的 `DomainApp` runtime。

其中：

- `ai` 提供模型接入能力
- `agent` 提供运行语义
- `harness` 提供跨产品 prepared-run contract 以及 product-neutral host /
  adapter / command substrate
- `harnesstui` 提供跨产品的 Harness/TUI conversation interaction 与
  presentation composition，以及基于中性 ports 的 conversation input、
  render 和 screen-loop playback testing；可依赖 `harness` 和 `tui`，不可依赖
  `coding`
- `channel` 提供选定的 operation/event、订阅、关联和回放边界，不承担通用
  Product 路由或 transport/runtime 总线职责
- `tui` 提供通用终端交互原语、render/terminal diagnostics 与确定性 playback
  substrate
- `method` 提供可选的方法组织与 plan/projection
- `work` 提供业务 work acceptance、运行终态、事件、日志与 projection
- `coding` 提供 coding 产品装配；feature-local adapter 解释 Coding 语义，
  `loushang.coding.ui` 只保留最终 UI composition、具体 surface 和 terminal
  binding
- `design`、`research`、`ppt`、`cowork` 是目标产品线概念，和 `coding` 并列，而不是
  `work` 或 `agent` 的子层

## Future Dependency Map

目标二级组件依赖关系。本节中 `A -> B` 表示 `A` 可以依赖 / 调用 `B`。

```text
all Python packages -> observability

method / work / Product implementation Python packages -> ontology
  # only when semantic typing is needed

agent -> ai
Product implementation Python packages -> ai
  # only for product-level helper AI calls

harness -> agent
Product implementation Python packages -> harness
Product implementation Python packages -> agent
  # only through stable agent primitives when bypassing harness is justified

Product implementation Python packages -> harnesswork
Product implementation Python packages -> work
channel -> work
  # the latter two are migration edges through compatibility/integration surfaces

Product implementation Python packages -> method
  # optional and only for structured work; Product binds Method output to Work

product TUI adapters -> tui

UI clients / SDK hosts / RPC clients -> channel
```

Product implementation Python packages are peers:

```text
coding
design
research
ppt
cowork
```

Product implementation Python packages should not depend on each other
directly. Cross-Product coordination should go through explicit adapters,
`work` events, `channel` protocol, or a future host-level orchestration layer.

Multi-UI target shape:

```text
TUI / WebUI / AppUI / SDK / RPC client
  -> channel client
  -> channel server / host assembly
  -> WorkOperation / WorkEvent / RuntimeEventView
  -> product adapter
  -> harness
```

The channel core transports and replays work operations/events and can deliver
already-projected runtime views. It does not render UI, create runtime views,
or own product execution internals.

## Loop Boundaries

`loushang` 有多个循环边界，不能合并成一个“大 runtime”：

| Loop | Owner | Responsibility | Does not own |
| --- | --- | --- | --- |
| Provider stream loop | `loushang.ai` | provider/model/auth/stream protocol and upstream API capability mapping | agent state, product policy, UI |
| Agent loop | `loushang.agent` | message/tool-call turn execution, low-level events, abort/error semantics | product preparation, work/method projection, UI |
| Product-run loop | `loushang.harness` plus product adapter | prepared run handoff, product-neutral host/adapter/lifecycle contracts, shared engines | second agent loop, product defaults, provider behavior |
| Work/method loop | `loushang.work` and optional `loushang.method` | durable operations/events/projections, method plan/step guidance | model streaming, product UI, harness execution mechanics |
| Channel loop | `loushang.channel` | external operation/event transport, subscription, replay, correlation | local UI widgets, product internals, agent state machine |
| TUI render loop | `loushang.tui` plus product UI adapter | terminal input/render planning, terminal operations, and product-specific final wiring | agent loop, provider behavior, harness policy, durable transcript truth |

This split lets `harness`, `tui`, `agent`, and `ai` develop in parallel. A
harness change should affect those lanes only when it intentionally changes a
stable cross-boundary contract. Otherwise:

TUI playback is not another runtime loop or a second conversation replay
engine. It drives the existing input, render, terminal, and optional
HarnessTUI screen-loop boundaries with scripted events, then records semantic
state and physical terminal evidence. Its value is precisely that it tests the
cross-boundary sequence without taking ownership away from Conversation,
Session, Work, Product presentation, or the live render loop.

- TUI changes stay in `loushang.tui` or product-owned UI adapters.
- Agent changes stay in `loushang.agent`.
- Provider/model/auth changes stay in `loushang.ai`.
- Harness changes stay in product-neutral contracts, shared registries,
  lifecycle shapes, and helper engines consumed by product adapters.

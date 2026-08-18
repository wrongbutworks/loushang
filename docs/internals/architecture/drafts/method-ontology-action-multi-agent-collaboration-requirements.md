# Method / Ontology Action 驱动的多 Agent 共享协作需求

## 状态

Draft / experimental requirements.

本文只定义问题、边界、需求和验证场景，不提出目标架构，不选择数据库、
消息系统或一致性算法，也不承诺新的公共 API。后续方案必须以当前已接受的
Method、Ontology、Harness、HarnessWork 和 Multi-Agent 边界为约束。

## 背景

当前 Harness Multi-Agent 已能提供子 Agent 派生、通信、等待、终止、上下文
派生和 workspace 隔离等技术态能力。Agent Transcript、Runtime Event 和 JSONL
也能用于会话记录、回放与外部监测。

这些能力尚不能完整回答更高层的协作问题：

- 一个 Method 如何声明多角色、阶段、关卡、验收和预期产物；
- 多个 Agent 如何共同履行一次 Method，而不把业务语义写进 Harness；
- 一个 Ontology Action 如何从请求、纯规划、授权、执行推进到结果与观察；
- Agent 如何共享与上述业务过程有关的状态、决定、证据和交接；
- 共享状态如何被选择性投影给模型，而不是反复把全部历史塞入 prompt；
- 技术运行成功、业务步骤完成和本体状态已经变化如何保持可区分。

因此需要探索一种可共享写入、查询、订阅和审计的协作能力。本文暂称其为
“共享协作空间”；“白板”“日志”“账本”都只是候选呈现或实现隐喻，不是已经
接受的组件名称。

## 平面定义

本文采用以下边界，不使用“业务面”泛指所有持久化数据。

### 业务面

业务面特指：

- `loushang.method` 所表达的工作方法语义；
- `loushang.ontology` 所表达的 Ontology Action 语义。

Method 关注角色、阶段、步骤、约束、关卡、预期产物、验收和偏差。Ontology
Action 关注语义目标、状态前提、权威来源、计划、授权要求、效果、结果和观察。

二者都不得因为多 Agent 协作而依赖具体 Agent 树、mailbox、prompt、模型、工具
调用、进程或存储后端。

### 技术面

技术面特指基础 Harness 及其下层执行设施，包括：

- prepared Agent run、Session 和运行生命周期；
- Harness Multi-Agent 的 Agent 身份、树、消息和技术状态；
- Agent loop、模型调用、工具执行、审批机制、sandbox 和 workspace；
- transcript、runtime event、context 组装和技术诊断；
- 为上述机制服务的存储、通知、查询和恢复设施。

这里的 Harness 指基础执行底座。`HarnessWork` 虽然以 Harness 为底座，但包含
Work 的业务履约与权威运行事实；它在本需求中属于需要单独澄清的跨平面接缝，
不能仅因包名而自动归入技术面，也不能吸收 Method 或 Ontology 的领域语义。

### 跨平面装配

业务面提出“什么应当成立”和“什么语义动作被请求”；技术面提供“如何运行和
调用能力”。二者之间需要 Product-owned 的绑定与投影，但本文不决定该绑定最终
由哪个新组件、现有组件或 adapter 承担。

后续方案必须保持：

```text
Method / Ontology Action
        business semantics
                |
                | Product-owned binding and correlation
                v
Harness and lower runtime
        technical execution
```

## 目标

本实验需求希望验证以下能力是否值得形成正式架构：

1. 让多个 Agent 围绕同一次 Method 履行共享必要的业务状态与证据。
2. 让 Ontology Action 的请求、计划、授权、执行、结果和观察可被协作过程引用。
3. 让业务语义与技术执行事实可关联、可追踪，但不混为同一种状态。
4. 让 Agent 能增量读取与当前责任相关的信息，并安全发布协作结果。
5. 让人、Host 和 Agent 对“谁在做什么、依据是什么、目前到哪一步”形成一致视图。
6. 在不牺牲正确性的前提下，限制协作状态对模型输入和 prompt cache 的破坏。

## 非目标

当前需求阶段不包含：

- 设计一个新的通用 `Action` 基类统一 Method 与 Ontology Action；
- 把 Method 变成 workflow executor；
- 把 Ontology 变成工具调用或分布式事务引擎；
- 在 Harness 中复制 Method、Ontology 或 Work 的业务状态机；
- 新建第二套 Agent loop 或 Multi-Agent runtime；
- 让多个 Agent 直接并发修改同一个 transcript/JSONL 文件；
- 用共享协作空间替代 Agent Transcript、Ontology Fact Store 或业务产物仓库；
- 预先确定 SQLite、PostgreSQL、CRDT、事件溯源或消息队列；
- 承诺跨主机执行、崩溃自动恢复或任意外部效果的 exactly-once；
- 设计最终 TUI、Web UI 或对外协议。

## 核心概念区分需求

后续设计与实现必须能表达以下区分，不能只靠命名约定：

| 业务面概念 | 技术面概念 | 必须区分的原因 |
| --- | --- | --- |
| Method role | Agent type / Agent instance | 一个角色可由多个 Agent 履行，一个 Agent 也可先后承担多个角色 |
| Method step occurrence | Agent turn / invocation / task | 一步业务工作可以跨多个调用，单次调用结束不代表步骤完成 |
| 业务责任或分工 | 技术 claim / lease | 责任仍然存在时，某个执行者的临时占用可能过期或迁移 |
| Method gate / acceptance | tool approval / policy decision | 业务验收与某次危险操作授权是不同决定 |
| expected artifact | workspace snapshot / tool output | 技术输出只有被产品解释和关联后才成为业务产物或证据 |
| Ontology ActionPlan | tool call plan / prompt plan | 语义计划受 projection guard 和 authority 约束，不等于调用步骤 |
| Action execution accepted | invocation succeeded | 技术调用成功不一定证明外部效果被接受 |
| Action outcome | later Ontology observation | 外部写入被接受不代表新状态已进入本体投影 |
| Method deviation | runtime error | 合法改变方法路径不一定是技术失败，技术失败也不一定导致方法偏差 |

## 业务面需求：Method

### M-01 方法定义独立

Method 必须继续以产品无关方式表达角色、阶段、步骤、约束、关卡、预期产物、
验收和证据要求。它不得包含具体 Agent path、模型名称、mailbox、数据库行、
进程 ID 或工具调用 ID。

### M-02 一次履行的稳定引用

系统必须能把一个可复用 `MethodPlan` 与某次实际协作履行相关联，并区分方法
定义、run-specific binding 和实际发生的 step occurrence。方法定义后续演进
不得静默改变已经开始的协作历史。

### M-03 角色与责任可见

参与者必须能确定当前 Method 所需角色、每个角色的责任、当前阶段和仍未满足的
关卡。角色分配的业务含义不能仅从当前 Agent 树反推。

### M-04 产物与证据可关联

Method 声明的预期产物和证据要求，必须能与实际产出的稳定引用相关联。业务面
只依赖稳定引用和解释结果，不要求把完整产物复制进共享状态。

### M-05 验收与偏差显式化

步骤完成、关卡通过、验收失败、计划修订和 Method deviation 必须成为显式、
可审计事实，不能由模型在 prompt 中静默宣布或改写。

### M-06 局部自主性

在 Method 约束和授权边界内，Agent 应保留选择模型、工具顺序、局部任务分解和
是否派生子 Agent 的自主性。共享协作需求不得把临时认知脚手架固化为 Method。

### M-07 未来 Method Action 的语义边界

当前 canonical Method 模型是 `MethodPlan` / `MethodStep`，本文不预设已经存在
`MethodAction` 类型。若未来需要引入 Method Action，它必须表达方法履行中的业务
意图或受控转换，例如请求进入下一阶段、提交步骤结果、请求审阅、处理 gate 或记录
偏差；它不能只是 tool call、Agent command 或 prompt plan 的别名。

Method Action 与 Ontology Action 可以在同一次协作中相关，但二者不得被强制继承
同一个通用 Action 类型。前者受方法履行和验收语义约束，后者受 Schema、projection
guard 和 StateAuthority 约束；共同基础设施只应关联它们的稳定引用、执行和证据。

## 业务面需求：Ontology Action

### O-01 语义请求完整

协作过程必须能引用完整、稳定的 Ontology Action 请求身份，包括目标、参数、
Schema/Profile 身份、projection guard、request id 和 actor context reference。

### O-02 纯规划边界

Ontology Action planning 必须继续是纯的、snapshot-guarded 的语义规划。协作
设施不得在读取“最新白板状态”后替 ActionPlan 静默换 guard 或重新规划。

### O-03 权威路由保留

协作过程必须保留 Ontology-owned、source-backed 和 derived 状态的不同处理要求。
技术执行设施不得因为拥有写工具就获得修改任意本体属性的语义权威。

### O-04 授权绑定计划

授权、审批或 policy decision 必须绑定确切的 ActionPlan 身份或 digest。共享
状态中的笼统“已批准”标记不得授权参数、目标、guard 或路由已经变化的计划。

### O-05 阶段不可折叠

至少必须能区分：

```text
requested
planned
authorized or rejected
execution accepted / rejected / unknown
observed / not observed / observation unknown
```

这些状态不是一个线性成功状态机；例如 execution accepted 后仍可能尚未 observed。

### O-06 幂等与未知结果

协作设施必须保留 Action request idempotency、execution receipt 和 observation
结果的不同身份。外部效果为 `unknown` 时，不能通过换 request id 或重复派生 Agent
来掩盖不确定性。

### O-07 证据链

从 ActionRequest、ActionPlan、授权决定、技术执行到后续 Ontology observation，
必须能用稳定引用建立因果和证据关系，而不要求 Ontology import Harness 类型。

## 技术面需求：Harness 及以下

### T-01 技术身份独立

系统必须能区分逻辑 Agent、Agent incarnation、Session、turn、invocation 和 tool
call。业务面只能通过稳定且最小的相关引用观察这些事实，不能把技术身份当作
Method role 或 Ontology actor 的唯一身份。

### T-02 多写者安全

多个 Agent 必须能并发发布协作信息，而不会破坏存储、覆盖他人事实或产生无法
识别的重复结果。所有写入必须经过可验证的写边界；直接并发改写 transcript 或
共享 JSONL 不满足此需求。

### T-03 顺序、幂等与冲突

技术面必须为需要顺序的 scope 提供明确顺序，为重试提供幂等身份，并在并发
更新不兼容时返回可观察冲突。不得依赖“最后一次写入看起来合理”。

### T-04 增量读取

每个 Agent 或 Host 必须能从稳定位置继续读取相关变化，并区分“没有新内容”、
“尚未送达”和“已经消费”。是否需要 ack、cursor 或 subscription 是后续方案问题，
但这些语义必须可表达。

### T-05 执行占用与迁移

当多个 Agent 竞争同一项技术执行责任时，系统必须防止过期执行者继续提交权威
结果，并能区分业务责任转移与技术执行占用变化。具体采用 lease、fencing 或其他
机制留待方案阶段决定。

### T-06 通信与状态共享分离

点对点消息、完成通知、共享事实和大体积产物必须可区分。消息没有自动成为业务
事实；共享事实也不应被广播成每个 Agent prompt 中的完整消息历史。

### T-07 失败语义

技术面必须区分失败、取消、超时、进程丢失、投递未知和外部效果未知。Agent
结束、Session 关闭或 tool call 返回都不能自动决定 Method 或 Ontology Action 的
业务结论。

### T-08 权限与隔离

共享协作不得绕过现有 capability、approval、policy、sandbox、workspace 和 secret
边界。一个 Agent 能看到协作条目，不等于它有权读取条目引用的产物或执行对应动作。

### T-09 可观测性

Host 必须能观察 Agent 拓扑、技术运行状态、相关业务引用、阻塞原因和最后活动，
同时避免把内部推理、secret 或不必要的完整 prompt 暴露为监控数据。

### T-10 Transcript 边界

Agent Transcript 和模型输入记录必须继续服务于会话恢复、回放、调试和模型调用
复现。它们可以作为只读 changefeed 的来源，但不能自动成为跨 Agent 共享写入的
权威协作状态。

## 跨平面需求

### X-01 依赖方向

Method 和 Ontology core 不得 import Harness、Agent、AI 或具体协作存储类型。
Harness core 和 Harness Multi-Agent 不得 import Method 或 Ontology 领域类型。跨面
绑定由 Product-owned composition 或 adapter 完成。

### X-02 稳定相关关系

系统必须能关联但不合并以下身份：

```text
MethodPlan / method step occurrence
Ontology ActionRequest / ActionPlan
business enactment or Work reference
Agent / invocation / tool execution reference
artifact / evidence / authorization / receipt reference
```

### X-03 业务结论权威

技术面只能报告执行事实。Method 的步骤、关卡、验收和偏差，以及 Ontology
Action 的语义结果与观察状态，必须由相应业务语义和 Product binding 判定。

### X-04 投影而非复制

一个统一“白板”可以作为面向人或 Agent 的组合视图，但必须能追溯每条信息的
原始 owner、版本和 authority。组合视图不得成为无法判断来源的第三份真相。

### X-05 命令与观察分离

查看共享状态、申请执行、提交证据、请求业务状态变化和执行技术工具必须是可
区分的操作。读取某条业务记录不得隐式触发 Action 或工具调用。

### X-06 生命周期解耦

业务协作的生命周期可能长于任一 Agent Session；技术 Agent 也可能在没有 Method
或 Ontology Action 的情况下运行。后续方案必须同时支持这种可选组合，而不是让
所有 turn 自动升级成业务协作。

### X-07 HarnessWork 待澄清约束

后续方案必须明确 HarnessWork 在跨面相关、业务履约、journal、evidence 和 replay
中的作用，同时满足：

- 不把 Method 定义或 Ontology Action 语义搬进 HarnessWork core；
- 不让基础 Harness 反向依赖 HarnessWork；
- 不把一次 Agent invocation 等同于一次业务 Work；
- 不建立与现有 Work 权威事实竞争的第二套业务账本。

本文不进一步决定共享协作空间是否属于 HarnessWork、Product 或独立 projection。

## 模型上下文与缓存需求

### C-01 共享状态不是 prompt

共享协作状态必须独立于任一 Agent 的模型输入。模型只接收当前任务需要的投影，
不能把完整共享历史当作固定拼接块。

### C-02 稳定前缀

Method 的稳定约束、角色纪律和 Product 指令应尽量保持稳定；频繁变化的协作增量
应与稳定前缀分离，避免无关写入持续破坏 prompt cache。

### C-03 相关增量

Agent 必须能按责任、步骤、Action、topic、时间位置或其他稳定条件取得相关增量。
系统应能证明投影来自哪个共享状态版本或读取位置。

### C-04 按需检索

大体积产物、旧讨论和低相关技术日志应通过引用按需读取。协作设施不得因为内容
“可能有用”就默认注入所有 Agent 上下文。

### C-05 私有与共享边界

Agent 的临时推理、草稿和局部计划默认不是共享业务事实。只有通过显式发布边界
产生的决定、证据、状态或产物引用才进入共享协作视图。

### C-06 模型输入可复现

当需要审计某次模型调用时，必须能确定它看到了哪些共享投影、版本、checkpoint
或引用。是否由 MIR、transcript 或独立 manifest 记录，留待后续方案决定。

## 安全与治理需求

1. 每条共享记录必须具有可判定的来源和 authority。
2. 读权限、写权限、执行权限和批准权限必须分开判断。
3. 对敏感业务对象的可见性必须在进入 Agent prompt 之前执行。
4. 共享状态不得保存可由稳定引用替代的 credential、secret 或完整外部响应。
5. 删除、更正和保留策略必须区分业务审计事实、技术诊断和可重建投影。
6. 人工介入必须能看见所批准的确切业务计划及其技术执行范围。

## 质量属性需求

### 正确性优先

共享状态延迟或 cache miss 可以降级性能，但不得导致越权 Action、重复外部效果、
错误业务终态或丢失已接受证据。

### 渐进组合

需求必须允许以下组合分别成立：

- 单 Agent，无 Method，无 Ontology Action；
- Multi-Agent，仅技术协作；
- Method 驱动的 Multi-Agent 协作；
- Ontology Action 由单 Agent 或 Multi-Agent 请求和执行；
- Method 与 Ontology Action 同时参与一次长期履约。

### 可替换实现

本地单进程、本地多进程和未来远端部署可以采用不同技术实现，但必须保持本文的
身份、authority、幂等、冲突、阶段和证据语义。

### 有界成本

需要能够测量共享状态大小、单次模型投影大小、读取增量、索引成本、重复写入、
冲突率、投递延迟以及模型缓存命中情况。不能只以“功能可运行”作为实验成功标准。

## 验证场景

以下场景用于验证需求，不暗示具体实现。

### V-01 Method 多角色履行

一个 Method 要求研究者、实施者和审阅者依次提供证据。三个 Agent 可以看到各自
责任和已满足条件；技术 Agent 更换后，业务角色和历史仍可追踪；一次 invocation
结束不会自动让 Method step 通过。

### V-02 并行证据汇总

两个 Agent 同时为同一 Method step 发布互不覆盖的证据，审阅者能判断来源和版本；
重复提交可识别，不兼容结论可并存并进入显式裁决，而不是最后写入覆盖前者。

### V-03 Method deviation

执行中发现原步骤不适用。系统记录原计划、偏差理由、批准或拒绝、修订后责任和
最终验收，不静默重写 MethodPlan。

### V-04 Ontology Action 并发冲突

两个 Agent 基于同一旧 projection 请求冲突 Action。每个计划保留自己的 guard 和
digest；技术执行能力不能绕过语义冲突，其中一个计划失败时不会被自动重规划成
新计划。

### V-05 外部效果未知

Agent 在提交 source-backed Action 后失联，外部返回未知。新的 Agent 能看到原
request、plan、授权和 receipt 状态，但不能使用新幂等键盲目重试；后续观察结果
独立记录。

### V-06 技术 lease 过期

一个 Agent 仍承担业务责任，但其技术执行占用已经过期并转交给另一个 Agent。
旧 Agent 的迟到技术结果不会覆盖新执行者的权威结果，业务责任转移也不会被错误
推断。

### V-07 Prompt 增量

一个 Agent 只接收当前 Method step 和相关 Action 的新增事实。其他 Agent 发布无关
技术日志时，稳定 prompt 前缀不变；需要旧证据时可按引用取回，并能复现当时模型
实际看到的投影。

### V-08 只读会话监测

Host 可以从 transcript/runtime events 观察 Agent 活动并投影到监控视图，但对
这些日志的读取或解析不会取得写入业务协作状态的权限。

## 实验成功判据

进入方案阶段前，至少应能为以下问题定义可执行验收：

1. 是否能在测试中证明业务状态与技术状态不会互相伪造终态？
2. 是否能证明重复请求、重复投递和迟到结果不会产生第二份权威效果？
3. 是否能从组合视图追溯到 Method、Ontology Action 和技术执行的原始引用？
4. 是否能在 Agent 更换、Session 结束或投影重建后保留必要业务连续性？
5. 是否能限制模型每轮接收的共享增量，并测量缓存与 token 成本？
6. 是否能在没有 Method/Ontology 的普通 Harness 使用中保持现有轻量边界？
7. 是否能在不让 Method/Ontology import Harness 类型的情况下完成端到端关联？

## 待回答问题

以下问题留到需求评审后，不在本文预先给答案：

1. “共享协作空间”首先服务一个 Product、一个 Work、一个 Session，还是一个业务
   object scope？
2. 哪些内容必须是权威事实，哪些只需要可重建 projection？
3. HarnessWork 应承担哪些跨面相关与履约事实，哪些仍应留在 Product adapter？
4. Method 是否需要新的协作约束词汇，还是现有 role/step/gate/artifact 已足够？
5. Ontology Action 是否只被引用，还是需要面向协作过程的 discovery/read model？
6. 人类是否是一等协作者，是否需要与 Agent 相同的 cursor、责任和交接语义？
7. 技术协作状态需要保持到 Session、Work 终局，还是更长期？
8. 本地多进程与跨主机是否属于同一阶段的必要需求？
9. 哪些 prompt-cache 指标和投影大小可以作为可接受阈值？
10. 是否存在必须支持同一业务条目的富文本共同编辑需求，还是追加事实和显式修订
    已经足够？

## 与当前文档的关系

- [Method Architecture](../method/README.md) 定义 Method 是结构化工作契约，
  不拥有执行和持久化。
- [Ontology ARD-012](../ontology/ARD-012-authority-aware-action-planning-and-product-hosted-write-back.md)
  定义 Action planning、authority、authorization、execution receipt 和 observation
  边界。
- [Harness Multi-Agent Architecture](../harness/multiagent/README.md) 定义当前已实现的
  纯技术态 Agent 协作能力。
- [HarnessWork Architecture](../harnesswork/README.md) 定义可选持久业务履约扩展和
  Work 权威事实。
- [Agent Transcript File Store Boundary](../harness/agent-transcript-file-store-boundary.md)
  定义当前 Agent Transcript JSONL 的存储职责；它不是共享写入业务账本。

本文若与上述已接受文档冲突，以上述文档和当前代码/测试为准。本文只有在需求评审
完成、验证场景得到确认后，才进入候选方案、实验设计或 ARD 阶段。

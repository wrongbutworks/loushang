# Loushang Architecture Principles

## Scope

本文档定义 `loushang` 的通用架构准则。  
它回答的是“在架构决策上应优先坚持什么”，而不是某个具体子系统应如何实现。

本文档主要面向：

- 子系统边界设计
- 运行时与协议设计
- 工具、能力与安全边界设计
- 方法层与产品装配层设计

本文档不直接回答：

- 某个模块的类图或目录结构
- 某个 provider / UI / transport 的具体实现
- 单次重构任务的实现步骤

---

## Relationship To Other Docs

本文档位于 `architecture-overview` 与各子系统设计文档之间。

关系如下：

- [Architecture Overview](/home/dev/workspace/loushang/docs/architecture/architecture-overview.md)
  - 定义整体分层与子系统地图
- 本文
  - 定义跨层通用的架构判断准则
- 子系统文档
  - 在各自边界内落实这些准则

因此：

- `overview` 回答“系统由哪些层构成”
- 本文回答“设计这些层时优先坚持什么”
- 子系统文档回答“这些准则如何落到具体结构上”

---

## Why These Principles Matter

`loushang` 不是单点 AI 能力封装，而是面向复杂知识工作的系统化运行框架。

这意味着它需要同时面对：

1. 模型能力快速变化
2. 工具与执行环境持续变化
3. 长时任务对状态、恢复与审计的要求
4. 自主规划带来的安全、验证与职责分离要求
5. 方法层、交互层与产品层之间的持续演化

如果没有稳定的架构准则，系统很容易退化为：

- 把当前模型能力硬编码进 harness
- 把状态混杂在 prompt 与临时上下文里
- 把权限控制退化为提示词约束
- 把规划、执行、评估混成一个不可验证的 agent
- 把产品装配写成对底层内核的侵入式定制

本文档的目标，是为后续架构设计提供一组稳定的高阶判断标准。

---

## How To Use These Principles

这些准则不是形式化教条，而是架构评审中的优先级依据。

推荐在以下场景显式对照本文：

1. 新增子系统或扩展点时
2. 设计新的 runtime / protocol / tool abstraction 时
3. 设计自主规划、长时任务与恢复机制时
4. 设计 capability、安全边界与审批机制时
5. 设计产品化装配层时

当两个方案都“可以工作”时，应优先选择：

- 更符合本文准则的一侧
- 对未来模型与运行环境变化更稳的一侧
- 对恢复、审计与验证更友好的一侧

---

## Documentation And Difference Analysis

`loushang` 的架构文档与实现文档应保持不同口径。

优先约束如下：

1. `architecture` 文档主要表达 should-be 的目标边界、结构约束与已接受设计。
2. `spec / plan` 文档主要表达某次迭代的临时设计与落地步骤。
3. 具体实现状态以代码与测试为准，而不是以架构文档为准。

在分析设计与实现关系时，统一使用：

- `设计-实现差异`

并进一步区分：

- `缺失`：设计有，代码无
- `偏离`：设计有，代码也有，但实现方式与设计不一致
- `部分落地`：设计有，代码有，但只实现了部分边界或能力
- `未建模实现`：代码有，设计无
- `文档过时`：当前接受的设计已变化，但文档仍停留在旧口径
- `漂移`：差异长期累积后，事实架构逐渐脱离目标架构

判断顺序应为：

1. 先确认当前接受的设计口径是什么
2. 再确认代码与测试中的事实行为是什么
3. 最后再判断差异类型

---

## Core Principles

### 1. Stable Interfaces Before Mutable Implementations

`loushang` 应优先冻结稳定接口，而不是过早冻结具体实现。

这意味着：

- 对外暴露的核心对象应保持长期稳定
- 具体 harness、provider、sandbox、transport 可以持续替换
- 不应把当前模型短板写死为长期系统边界

对 `loushang` 而言，优先稳定的通常是：

- `session`
- `event`
- `context`
- `tool`
- `capability`
- `artifact`
- `protocol`

而不应过早冻结的通常是：

- 某一代 prompt 结构
- 某一种 harness 编排方式
- 某个 provider 的特定行为补丁
- 某个场景下的单一 agent workflow

判断标准是：

- 接口是否能容纳未来更强模型
- 接口是否允许实现层替换而不破坏上层
- 接口是否表达领域语义，而不是临时实现技巧

---

### 2. Externalized State Before Context Accumulation

长时任务的核心问题不是“如何塞进更多上下文”，而是“如何维护可恢复、可查询、可审计的外部状态”。

因此：

- 不应把长期工作状态仅保存在模型上下文窗口中
- 不应把关键进度仅保存在一次摘要或单次压缩结果中
- 应把状态外置为可恢复对象

对 `loushang` 的直接含义是：

- `session` 不等于 context window
- 计划、阶段目标、决策、风险、工具执行记录、交付物，应能脱离单次采样存在
- 任何压缩、摘要、trim 都应建立在可恢复状态之上，而不是成为唯一事实来源

可接受的状态对象包括但不限于：

- append-only event log
- 可查询的任务状态
- 明确的 work product / artifact
- 持久化的阶段性摘要

---

### 3. Capability Governance Before Fixed Invocation Paths

能力治理是授权问题，调用路径只是实现问题。

因此：

- `capability` 应作为一等建模对象
- 是否通过 proxy、直连、本地执行、远端执行，是后续实现选择
- 不应把“所有工具都必须走同一条调用链”误当成架构原则

对 `loushang` 而言，优先应回答的是：

- agent 被授予了什么能力
- 能力作用于哪些资源
- 能力在什么时间窗内有效
- 能力是否需要审批、审计与撤销
- 能力是否可组合、可转授或必须显式拒绝转授

而不是先回答：

- 一定要不要 proxy
- 一定只允许某一种工具适配形态

更稳的原则是：

- 高风险外部能力需要更强治理
- 低风险本地能力可以采用更轻路径
- capability 模型应独立于具体执行载体

---

### 4. Structural Security Before Instructional Safety

安全边界应尽量通过系统结构保证，而不是依赖提示词、约定或“模型应该听话”。

这意味着：

- 不可信代码与高权限秘密不应默认共处
- 权限授予应默认最小化
- 高风险操作应支持独立审批、审计与撤销
- secret exposure 不应作为正常工具调用模型的一部分

对 `loushang` 的含义不是“任何 sandbox 永远不可接触任何凭据”，而是：

- 原始秘密不应以默认可读形式暴露给 agent 生成代码
- 必要授权应尽量以受限能力形式提供，而不是以通用长期凭据形式提供
- 风险控制应依赖结构设计，而非纯策略提醒

结构性安全措施通常优先于：

- 额外提示词告诫
- 经验性黑名单
- 基于模型当前能力上限的侥幸假设

---

### 5. Verification And Traceability Are First-Class Capabilities

`loushang` 不应把验证视为“执行之后的补充动作”，而应把它视为系统的一等能力。

这意味着：

- 规划产物应带有可验证目标
- 执行产物应可追溯到目标、约束与输入
- 评估结果应能回连到具体 action、artifact 与 decision

对复杂工作系统来说，真正重要的不是“agent 做了很多事”，而是：

- 为什么做
- 依据什么做
- 是否满足目标
- 哪一步失败
- 哪个结果可信

因此 `loushang` 的关键对象不应只包含 action，还应包含：

- requirement / goal
- acceptance signal
- verification result
- validation note
- provenance / trace

---

### 6. Separate Planning, Execution, And Evaluation Responsibilities

自主系统可以协同，但不应把规划、执行、评估无差别混合成一个黑箱。

这条准则并不强制要求一定采用多个 agent 实例，而是要求职责显式可分。

推荐保持分离的职责包括：

- 规划
- 执行
- 评估
- 审批
- 记忆与状态整理

对 `loushang` 的含义是：

- 方法层不应只生成一个“计划文本”
- 规划结果应成为可执行契约
- 评估不应只是执行后的附带自评
- 运行时应允许引入独立 evaluator / critic / reviewer 角色

当系统无法说明“谁在规划、谁在执行、谁在判定完成”时，通常说明职责边界仍不清楚。

---

### 7. Default For Long-Horizon Recovery And Evolution

`loushang` 应默认把长时任务视为常态，而不是异常情况。

因此架构上应优先支持：

- 中断恢复
- session continuation
- 状态压缩与回放
- 工具失败后的重试与替代
- 多次 handoff 后的连续工作

这条准则背后的判断是：

- 复杂工作天然跨越多个 turn
- 模型、工具、网络、环境都会失败
- 可靠系统不能把“成功完成整段流程”建立在一次连续不出错运行上

所以：

- 恢复语义应被设计进系统
- continuation 应被视为正常能力
- 失败信息应结构化，而不是只作为日志文本存在

---

### 8. Product Assembly Must Preserve Kernel Consistency

`loushang-coding`、`tui`、`methods` 等上层产品装配可以有强场景化选择，但不应破坏内核一致性。

这意味着：

- 产品层可以提供默认策略
- 产品层可以装配特定 workflow
- 产品层可以做更强的体验决策

但不应：

- 重新定义底层核心语义
- 绕开统一协议直接耦合内部细节
- 让场景特例反向污染通用抽象

对 `loushang` 来说，这是防止“为了一个产品场景，侵入性改坏通用运行内核”的关键准则。

---

## Tensions And Trade-Offs

这些准则之间并不总是完全一致，常见张力包括：

### Stable Interface vs Fast Delivery

过早抽象会带来空转，过晚抽象会把临时实现固化为长期负担。

应优先避免两种极端：

- 为了抽象而抽象
- 为了交付而把临时 hack 冒充长期接口

### Externalized State vs Simplicity

把状态外置会增加系统复杂度，但长时任务、不确定恢复与可审计性又要求状态显式存在。

因此应避免：

- 所有状态都落数据库，导致系统过重
- 所有状态都只留在 prompt，导致系统不可恢复

### Capability Governance vs Developer Ergonomics

能力治理越强，往往越复杂；开发体验越轻，往往越容易越权。

应按风险分层，而不是一刀切：

- 本地低风险工具优先轻路径
- 高风险外部资源优先强治理

### Responsibility Separation vs Runtime Cost

规划、执行、评估分离会带来更多运行步骤与协调成本。

但在复杂任务中，缺少职责分离往往会造成更高的返工与验证成本。

---

## Immediate Implications For Loushang

结合当前 `loushang` 的分层设计，近期最应优先落实的方向包括：

1. 明确 `session`、`event`、`artifact`、`capability` 的统一建模
2. 把 `channel` 设计为可承载恢复、审计与查询的边界层，而不只是消息搬运层
3. 在 `methods` 层把计划、阶段、验收条件与 work product 变成可运行对象
4. 在 `agent` 层显式支持规划、执行、评估等职责分离
5. 在工具体系中区分能力模型、执行路径与凭据中介，避免混为一谈
6. 在产品层坚持“场景装配建立在通用内核之上”，而不是反向侵入底层

---

## Non-Goals And Common Misreadings

本文不主张：

- 所有工具都必须通过 proxy
- 所有 sandbox 都完全不可接触任何受控资源
- 任何场景都必须使用多 agent
- 任何状态都必须持久化到复杂基础设施
- 为了追求抽象纯度而牺牲当前实现推进

本文真正主张的是：

- 能力模型应先于调用路径争论
- 结构性边界应先于提示词约束
- 可恢复状态应先于上下文堆积
- 可验证职责应先于黑箱式自主

---

## Conclusion

`loushang` 的长期目标，不只是把模型、工具和交互拼接起来，而是把复杂知识工作组织为一个可运行、可恢复、可验证、可演化的系统。

因此，`loushang` 的架构判断不应围绕“当前模型会什么”来短期优化，而应围绕：

- 哪些语义必须稳定
- 哪些状态必须可恢复
- 哪些能力必须被治理
- 哪些职责必须被分离
- 哪些产品装配不能破坏内核一致性

这些准则构成 `loushang` 后续子系统设计、方法层设计与产品化装配的共同约束。

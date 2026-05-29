# Loushang-AI Component Structure V1 (同步现状)

说明：

- 本文是第一版组件草案。
- 当前 `model` 组件已收敛为 `domain / registry / loader`。

## Scope

本文档给出 `loushang-ai` 第一版较稳定的组件结构草案。  
它建立在候选功能、候选组件、映射分析与 round-1 refinement 之上，目标是先明确：

- 核心组件有哪些
- 每个核心组件的边界是什么
- 主要依赖方向是什么
- supporting domains 归属到哪里

本文档不讨论：

- 最终包结构
- 代码实现顺序
- 字段级接口细节
- v0.1 范围裁剪

---

## Input Documents

- [Loushang-AI Whitebox Candidate Components](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-whitebox-candidate-components.md)
- [Loushang-AI Function To Component Mapping](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-function-component-mapping.md)
- [Loushang-AI Component Refinement Round 1](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-component-refinement-round-1.md)

---

## Structure Goal

这一版结构草案优先满足五个目标：

1. 主功能有明确主承载组件
2. provider 边界变化被局部化
3. streaming / assembly 语义有独立中心
4. 横切支撑能力有明确主归属，不再漂浮
5. protocol family、auth、transport、model family 四类变化有明确吸收位置

---

## Core Components

当前更稳的核心组件先收成 7 个一级组件域。

### 1. Public API (`loushang.ai.api`)

**负责：**

- 对外暴露 `stream`
- 对外暴露 `complete`
- 对外暴露 `stream_simple`
- 对外暴露 `complete_simple`

**不负责：**

- model registry 内部实现
- provider payload 翻译
- raw part 收敛
- carrier 生命周期

### 2. Model Component (`loushang.ai.model`)

**内部组成：**

- `Model Registry`
- `Model Domain`
- `Model Loader`

**负责：**

- 管理模型定义
- 提供 model lookup
- 暴露 endpoint `api` / resolved api 事实与 capability 元数据
- 解释 model family / api family / capability family

**不负责：**

- provider 执行
- registry resolution
- 上下文装配

### 3. ApiProvider Registry (`loushang.ai` 根域注册能力)

**负责：**

- 维护 `api -> ApiProvider` 映射
- 对外提供注册、查询、列举能力

**不负责：**

- model registry 本身
- provider payload adaptation
- lazy client 调用

### 4. Provider Adapter (`loushang.ai.providers.*`)

**负责：**

- 隔离具体 provider / protocol family 的应用协议差异
- 接收统一 `Context + Model + Options`
- 输出统一 raw parts

**不负责：**

- 顶层 public 调用面
- 最终 `AssistantMessage` 生命周期
- tool orchestration
- 稳定边界支撑骨架本身

### 5. Provider Boundary Support (`loushang.ai.provider`)

**内部组成：**

- `ApiProvider Protocol`
- `Transport Strategy`
- `Carrier Invocation`
- `Provider Payload Transformation`
- `Error Mapping`

**负责：**

- 为 `Provider Adapter` 提供稳定边界支撑骨架
- 吸收 protocol family、transport、carrier 变化模式
- 为新增 adapter 提供共享执行骨架

**不负责：**

- provider-specific execution
- auth material resolution
- public event / message 收敛

### 6. Auth Support（预留，纳入边界支撑）

**负责：**

- 统一承接 provider auth material
- 将 API key / OAuth token / provider-specific credential material 解析为 provider adapter 可绑定的 auth view

**不负责：**

- 模型语义解释
- transport 选择
- provider payload 翻译

### 7. Event Stream Component (`loushang.ai.event_stream`)

**内部组成：**

- `Raw Part Types`
- `Raw Assembler`
- `AssistantMessageEventStream`

**负责：**

- 定义 provider stream 到 public event stream 之间的标准中间语义
- 收敛 raw parts
- 维护 partial -> complete 过程
- 生成最终 `AssistantMessage`
- 暴露统一流式消费边界
- 暴露 `.result()`

**不负责：**

- provider resolution
- provider 协议调用
- public 根入口

---

## Supporting And Functional Domain Components（同步补充 CLI / Utils / Record&Replay）

除了核心结构中心，还保留一个 supporting component 和一个功能域组件。

### 8. Context Intake And Normalization (`loushang.ai.context`)

**定位：**

- supporting component

**负责：**

- 统一承接 `Context`
- 规范 system prompt / messages / tools / metadata

**主归属：**

- 核心域内部支撑

### 9. Tool Semantic Component (`loushang.ai.tool`)

### 10. Utils / Overflow (`loushang.ai.utils`)

**负责：**

- 通用工具库与 `is_context_overflow` 等上下文窗口溢出检测

**主归属：**

- 独立 utilities 组件域

### 11. CLI (`loushang.ai.cli`)

**负责：**

- 列举 apis/models/endpoints
- chat/complete 调用（支持 env 与参数消歧、provider:endpoint:modelId）
- 配置与调试（trace/json 输出）

**主归属：**

- 独立入口域，消费 `api` 与 `model`、`provider` 等

### 12. Record & Replay（设计已落地为文档）

**负责：**

- RawPart 与 vendor-raw 的录制与回放（白盒/黑盒）
- Agent 层开关（record/replay/auto）

**主归属：**

- 观测与测试能力域（文档：`loushang-ai-stream-record-replay.md`）

**定位：**

- functional domain component

**负责：**

- tool schema
- tool call 语义
- tool result message 语义

**主归属：**

- 独立功能域

---

## Supporting Domains

以下对象在 V1 中不作为一级核心组件，但要有明确主归属。

### A. Simple Invocation Mapping

**主归属：**

- `Top-Level AI API`

**协作对象：**

- `Provider Adapter`

**说明：**

- simple 语义从入口进入，但不应完全困在入口层内部

### B. Provider Payload Transformation

**主归属：**

- `Provider Boundary Support`

**说明：**

- 这是 adapter 的核心内部子域

### C. Provider Boundary Support

**主归属：**

- 独立边界支撑组件域

**内部组成：**

- `ApiProvider Protocol`
- `Transport Strategy`
- `Carrier Invocation`
- `Provider Payload Transformation`
- `Error Mapping`

**说明：**

- 这是一组稳定吸收变化模式的边界骨架
- 它服务于 `Provider Adapter`，但不等同于具体 adapter 本身

### D. Cancellation And Aborted Bridge

**主归属：**

- `Event Stream Component`

**协作对象：**

- `Provider Adapter`
- 调用方可见的 stream consumption boundary

**说明：**

- 它是跨 adapter/assembler/stream 的 shared technical domain
- 内部终止语义的主收敛应发生在 assembler
- event stream 主要负责对外读侧承载与暴露

### E. Error Mapping

**主归属：**

- `Provider Boundary Support`

**协作对象：**

- `ApiProvider Registry`
- `Event Stream Component`

**说明：**

- 以 adapter 为主拥有者更稳，因为多数错误首先产生在边界处

### F. Thinking / Reasoning Mapping

**主归属：**

- `Provider Adapter`

**协作对象：**

- `Top-Level AI API`

### G. Tool Validation

**主归属：**

- `Tool Semantic Component`

### H. Multimodal Content

**主归属：**

- `Context Intake And Normalization`

**协作对象：**

- `Event Stream Component`
- `Tool Semantic Component`

### I. Provider Bootstrap And Extensibility（`loushang.ai.bootstrap` + `models.json` compat）

**补充：**

- 读取 `models.json` 的 `compat.providerTransport`/`betaFeatures` 决定使用 SDK/HTTPX、是否注入 beta headers
- 按 endpoint compat 注册/切换 Provider（如 OpenAI Responses SDK）

**主归属：**

- `ApiProvider Registry`

**协作对象：**

- `Provider Adapter`

### J. Test / Validation Support

**主归属：**

- `Provider Bootstrap And Extensibility`

### K. Observability Emission（`loushang-ai-trace-events.md` 对应）

**主归属：**

- 暂作为 cross-cutting support domain 保留

**主要挂载点：**

- `Top-Level AI API`
- `Provider Adapter`
- `Event Stream Component`

### L. Model Family Handling

**主归属：**

- `Model Component`

**协作对象：**

- `Provider Adapter`

**说明：**

- 这是从系统环境图显式识别出来的稳定变化面
- 不应继续隐含在 `Model Registry` 查询逻辑或 provider 文件中的局部判断里

---

## Dependency Direction（更新 Bootstrap/Compat 与 CLI/Record&Replay）

第一版结构建议维持以下主依赖方向：

```mermaid
flowchart LR
    API[Public API (loushang.ai.api)]
    MODEL[Model Component]
    APIREG[ApiProvider Registry]
    BOOT[Bootstrap/Compat (models.json)]
    BOUNDARY[Provider Boundary (loushang.ai.provider)]
    CTX[Context Normalize]
    AUTH[Auth (reserved)]
    ADAPTER[Provider Adapter (providers/*)]
    EVENT[Event Stream]
    TOOL[Tool Semantic]
    CLI[CLI]
    RNR[Record & Replay]

    API --> MODEL
    API --> APIREG
    API --> CTX

    BOOT --> APIREG
    APIREG --> ADAPTER
    ADAPTER --> MODEL
    ADAPTER --> BOUNDARY

    ADAPTER --> CTX
    ADAPTER --> AUTH
    ADAPTER --> EVENT

    TOOL -.semantic.-> CTX
    TOOL -.semantic.-> ADAPTER
    TOOL -.semantic.-> EVENT

    CLI --> API
    RNR -.tap.-> ADAPTER
    RNR -.tap.-> EVENT
```

这张图只表达主依赖方向，不表达所有横切支撑关系。

---

## Ownership Summary（同步结论）

当前第一版结构里，最重要的归属判断是：

- Provider 协议/实现差异：主归属 `Provider Adapter`（受 `Provider Boundary` 支撑）
- 流式组装与最终消息：主归属 `Event Stream Component`
- 工具语义：主归属 `Tool Semantic Component`
- Public 入口：主归属 `loushang.ai.api`
- Bootstrap/Compat 开关：主归属 `Bootstrap`（影响 Registry 与 Adapter 选择）
- CLI 与 Record&Replay：独立入口/观测域，消费 `api`/`event_stream` 等

这些主归属如果后面继续漂移，说明边界还没稳住。

---

## Open Questions

V1 之后仍有几个问题要留到下一轮：

1. `Context Intake And Normalization` 是否应和某种 message/context model 组件进一步组合
2. `Tool Semantic Component` 是否过大，是否需要在下一轮分出 tool result conversion 子域
3. `Carrier Invocation` 是否最终值得升格为正式组件
4. `Observability Emission` 是否需要一个更明确的宿主接口边界

---

## Takeaway

这一版结构已经足够支撑后续更细的边界设计。  
相比前面的候选清单阶段，现在更重要的不是继续加对象，而是：

- 保住这版主依赖方向
- 保住主拥有者
- 再做接口与边界细化

下一步更合理的是继续写：

- `loushang-ai-component-interfaces-v1.md`

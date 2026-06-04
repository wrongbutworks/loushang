# Loushang-AI Adaptability NFR

## Scope

本文档基于 `loushang-ai` 当前设计、实现状态与 `reference AI SDK` 参考，总结 `loushang-ai` 在适应性方面应满足的非功能需求（NFR）。

本文档只讨论：

- 协议适应性
- 模型家族适应性
- 认证、传输与 provider 兼容性适应性
- 上下文迁移与变化局部化

本文档不讨论：

- 单个 provider 的具体实现细节
- 当前阶段的完整 roadmap
- 所有性能/安全类 NFR

---

## Inputs

- [Reference AI SDK Adaptability NFR](/home/dev/workspace/loushang/docs/architecture/ai/reference/reference-ai-sdk/reference-ai-sdk-adaptability-NFR.md)
- [Loushang-AI System Context](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-system-context.md)
- [Loushang-AI Physical System Context](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-physical-system-context.md)
- [Loushang-AI Component Structure V1](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-component-structure-v1.md)
- [Loushang-AI Implementation Status Round 1](/home/dev/workspace/loushang/docs/architecture/ai/validation/loushang-ai-implementation-status-round-1.md)

---

## Current Position

`loushang-ai` 当前已经具备三条主协议面：

- `anthropic-messages`
- `openai-completions`
- `openai-responses`

并已经形成第一版组件域：

- `Model Component`
- `Provider Adapter`
- `Provider Boundary Support`
- `Auth Support`
- `Event Stream Component`

因此，`loushang-ai` 的适应性 NFR 不应再停留在“以后再说”，而应开始明确约束：

- 哪些变化由谁吸收
- 哪些变化允许局部化
- 哪些约束应在运行前被解释和暴露

---

## NFR-1 协议族扩展不得改变顶层调用面

新增或替换协议族时，不得改变统一 public API：

- `stream`
- `complete`
- `stream_simple`
- `complete_simple`

也不得改变统一 message / event 主协议，除非形成新的 ARD。

这条要求约束：

- `Provider Adapter`
- `Provider Boundary Support`
- `Event Stream Component`

---

## NFR-2 模型家族约束必须可解释

系统必须能够解释模型家族的协议约束与能力约束，而不是仅依赖调用方手工写死 `api`。

这里的“解释”至少包括：

- `preferred_api`
- `allowed_apis`
- `supports_thinking`
- `supports_tool_use`
- `supports_image_input`
- `supports_image_output`
- 最大 context window / output token 上限

这里的 `contextWindow` 指模型目录中的最大窗口上限，不直接等于运行时实际使用预算；后者更适合放在未来的 `session/runtime` 层，由 `agent` 按预算与压缩阈值消费。

这条要求主要落在：

- `Model Component`
  - `Model Registry`
  - `Model Capability`
  - `Model Capability Resolver`

并且它的职责是：

- 解释服务端已存在的约束
- 暴露 capability view
- 而不是凭空“自由选择协议”

---

## NFR-3 认证差异必须集中收敛

API key、OAuth、provider-specific credential material 等认证差异必须集中收敛到 `Auth Support`，不得散落在：

- top-level API
- examples
- bootstrap
- concrete provider 中的任意位置

这条要求意味着：

- `Auth Support` 是独立组件
- 它拥有统一 auth view
- provider 只消费 auth view，不各自重新发明认证绑定方式

---

## NFR-4 传输差异不得泄漏到 public event 协议

当 provider 在 `sse`、`websocket`、SDK-native stream、plain HTTPS` 之间切换时：

- public event 协议不得随之变化
- final message contract 不得随之变化

这条要求主要落在：

- `Provider Boundary Support`
  - `Transport Strategy`
  - `Carrier Invocation`
- `Event Stream Component`

也就是说：

- transport 变化应在边界支撑链路内被吸收
- 不应进入 `AssistantMessageEvent` 主协议

---

## NFR-5 Provider-Compatible 差异必须局部化

对 OpenAI-compatible、Anthropic-compatible 这类“名义协议相同、行为细节不同”的 provider 变体，系统必须通过 compatibility metadata 或 boundary support 局部化吸收差异，而不是让 top-level API 或调用方承担分支逻辑。

这类差异包括：

- role 支持差异
- usage streaming 差异
- reasoning / developer role / store 支持差异
- tool result / image payload 细节差异

这条要求主要约束：

- `Model Component`
- `Provider Boundary Support`
- `Provider Adapter`

---

## NFR-6 上下文跨协议迁移必须可持续

`Context`、`AssistantMessage`、`ToolResultMessage` 应能够在不同协议族之间继续迁移、继续对话。

必要时允许：

- compatibility-aware normalization
- 局部降级
- 显式报错

但不允许：

- 因 provider-specific internal shape 泄漏而导致调用方重写上下文

这条要求主要约束：

- `Context Intake And Normalization`
- `Tool Semantic Component`
- `Provider Adapter`
- `Event Stream Component`

---

## NFR-7 变化必须局部化到组件域

以下变化面必须有明确宿主：

- model family -> `Model Component`
- auth -> `Auth Support`
- protocol / transport / carrier -> `Provider Boundary Support`
- provider-specific execution -> `Provider Adapter`
- raw-part / event convergence -> `Event Stream Component`

不允许这些变化继续漂移到：

- `Top-Level AI API`
- examples
- tests 中的隐式假设

---

## NFR-8 不兼容必须前置暴露

当模型、协议、provider、auth、transport 之间不兼容时，系统必须尽早 fail fast，并暴露明确错误。

至少包括：

- resolved api mismatch
- unsupported protocol for model family
- unsupported capability for provider family
- missing auth material
- unsupported transport path

这条要求意味着：

- `Model Capability Resolver` 不能只是静态占位
- `Auth Support` 不能只是 header helper
- `Provider Boundary Support` 不能只是目录名

---

## Current Gaps Against These NFRs

结合当前实现，最明显的未完成点是：

1. `Model Capability` / `Model Capability Resolver` 已有骨架，但尚未真正参与运行时决策
2. `Auth Support` 只有最小 `AuthView`，尚未进入真实 provider binding 主链
3. `Provider Boundary Support` 仍偏占位，shared transport / carrier / payload / error strategy 还不够成熟
4. `Tool Semantic Component` 还未正式代码化为独立组件域

---

## Summary

对当前 `loushang-ai` 来说，适应性 NFR 的核心不是“支持更多 provider”本身，而是：

- 协议变化有宿主
- 模型约束可解释
- 认证差异可收敛
- 传输差异不泄漏
- 兼容差异可局部化
- 上下文可迁移
- 不兼容应前置暴露

如果后续实现不能持续满足这几条，`loushang-ai` 即使暂时能接入更多 provider，也会很快失去结构稳定性。

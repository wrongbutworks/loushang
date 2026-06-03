# PI-AI Adaptability NFR

## Scope

本文档提炼 `pi-ai` 在协议、模型、认证、传输、兼容性与上下文迁移方面体现出来的适应性非功能需求（NFR）。

本文档不讨论：

- `pi-ai` 的完整组件结构
- 具体 provider 的逐行实现细节
- `loushang-ai` 的直接实现计划

---

## Sources

- [PI-AI README](/home/dev/workspace/pi-mono/packages/ai/README.md)
- [models.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.ts)
- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)
- [api-registry.ts](/home/dev/workspace/pi-mono/packages/ai/src/api-registry.ts)
- [pi-ai-abstraction-variation-strategy.md](/home/dev/workspace/loushang/docs/architecture/ai/reference/pi-ai/pi-ai-abstraction-variation-strategy.md)

---

## Reading Note

`pi-ai` 并没有把这些适应性要求写成一份单独 NFR 文档。  
下面这些条目，是从它的类型系统、registry、provider family、OAuth 与 changelog 演进中反向提炼出来的。

---

## NFR-1 协议族可增殖

系统应允许新增或替换协议族，而不改变顶层 API 与统一消息/事件协议。

在 `pi-ai` 中，这一点体现在：

- `KnownApi` 明确列出多个 API family
- `ApiProvider` 围绕 `api` 建模，而不是围绕单一 provider 建模
- `registerApiProvider()` / `getApiProvider()` 使协议族通过 registry 接线，而不是写死在 top-level dispatch 里

对应源码：

- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)
- [api-registry.ts](/home/dev/workspace/pi-mono/packages/ai/src/api-registry.ts)

---

## NFR-2 模型家族约束可解释

系统应能解释模型家族与协议族之间的约束，而不是仅依赖调用方手工指定。

这类约束包括：

- 某模型应走哪个 `api`
- 某模型是否支持更高 reasoning level
- 某模型是否适合某条 transport
- 某模型 family 的兼容性开关

在 `pi-ai` 中，这一点主要体现为：

- model metadata 与 registry 分离
- `supportsXhigh()` 这类 capability 判定
- `compat` 字段承载 OpenAI-compatible provider 差异

对应源码：

- [models.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.ts)
- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)

---

## NFR-3 认证方式可收敛

系统应允许 API key、OAuth、ADC、订阅型认证等多种认证方式并存，并将其收敛为 provider 可绑定的统一认证视图。

在 `pi-ai` 中，这一点体现在：

- `getEnvApiKey()` 把环境变量认证集中处理
- `utils/oauth/*` 把 OAuth provider 相关逻辑从具体 provider 中剥离
- 某些 provider 允许“authenticated placeholder”而不是显式 API key

对应源码：

- [env-api-keys.ts](/home/dev/workspace/pi-mono/packages/ai/src/env-api-keys.ts)
- [utils/oauth/](/home/dev/workspace/pi-mono/packages/ai/src/utils/oauth)

---

## NFR-4 传输方式可切换

系统应允许 provider 在 `sse`、`websocket`、SDK-native stream、plain HTTPS 之间切换，而不改变 public message/event contract。

在 `pi-ai` 中，这一点体现在：

- `transport` 进入 `StreamOptions`
- Codex / Responses family 显式处理多 transport
- provider-specific transport 差异通过 provider 内部与 shared support 吸收

对应源码：

- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)
- `openai-codex-responses` / related changelog entries

---

## NFR-5 OpenAI-Compatible 差异可局部化

系统应允许同一协议家族下的 provider 变体通过 compatibility metadata 被局部化，而不是在 top-level 调用链中散落 provider-specific if/else。

在 `pi-ai` 中，这一点体现在：

- `OpenAICompletionsCompat`
- `supportsStore`
- `supportsDeveloperRole`
- `supportsReasoningEffort`
- `supportsUsageInStreaming`

对应源码：

- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)

---

## NFR-6 跨协议上下文应可迁移

系统应支持 context/message/tool result 在不同 provider / protocol family 之间迁移，并在必要时进行规范化、降级或兼容性修复。

这不是“最好有”，而是 agentic workflow 的核心要求。

在 `pi-ai` 中，这一点体现在：

- README 明确强调 context persistence 与 hand-off
- changelog 多次修复跨协议 tool call ID、thinking continuity、tool result orphan、cross-provider handoff

对应来源：

- [README.md](/home/dev/workspace/pi-mono/packages/ai/README.md)
- [CHANGELOG.md](/home/dev/workspace/pi-mono/packages/ai/CHANGELOG.md)

---

## NFR-7 变化应局部化到边界或支撑骨架

新增 provider、auth 方式、transport 或 compat 变化时，变化应优先局部化到：

- provider adapter
- registry
- model metadata / capability
- auth / transport shared support

而不应直接污染：

- 顶层入口
- public event contract
- final message contract

这条要求不是 `pi-ai` 显式写出的原则，但它的代码结构和 shared support 演进都体现了这一点。

---

## NFR-8 不兼容应尽早显式暴露

当模型、协议、auth、transport 或 compat 条件不满足时，系统应尽早 fail fast，而不是在 provider 深处才发生模糊错误。

在 `pi-ai` 中，这一点体现在：

- `api` mismatch 在 registry wrapper 即暴露
- 部分 capability / compat 通过类型或选项约束前置表达
- changelog 中许多修复都属于“把不兼容前置和局部化”

对应源码：

- [api-registry.ts](/home/dev/workspace/pi-mono/packages/ai/src/api-registry.ts)

---

## Summary

如果把 `pi-ai` 的适应性压缩成一句话，可以收成：

- 协议可增殖
- 模型能力可解释
- 认证可收敛
- 传输可切换
- 兼容差异可局部化
- 上下文可迁移
- 不兼容应前置暴露

这组 NFR 不是额外附加物，而是 `pi-ai` 之所以能持续吸收新 provider、新协议与跨模型 handoff 的前提。

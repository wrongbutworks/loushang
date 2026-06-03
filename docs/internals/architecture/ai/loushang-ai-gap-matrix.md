# loushang-ai Gap Matrix vs pi-ai

本文基于以下代码范围对比：

- `pi-mono/packages/ai`
- `loushang/src/loushang/ai`

结论先说：`loushang.ai` 已经具备了 `pi-ai` 的基础语义骨架，但距离“功能面对齐”仍有明显差距。当前最大的 gap 集中在 provider 覆盖、OAuth/login 体系、图像 tool result 闭环、复杂 reasoning continuity、模型目录规模，以及 `pi-ai` 的懒加载与浏览器兼容相关能力。

## 总体判断

- 如果目标是“让 `loushang.ai` 在 Python 后端场景达到 `pi-ai` 80% 实用能力”，当前大概已经有 55%-65%。
- 如果目标是“功能面对齐 `pi-ai` 当前完整能力面”，仍大约差 35%-45%。
- 剩余工作量主要不在基础框架，而在 provider 扩展与高级语义闭环。

## 对齐矩阵

| 能力项 | `pi-ai` 状态 | `loushang.ai` 状态 | 结论 | 证据 |
|---|---|---|---|---|
| 顶层统一 API：`stream/complete/streamSimple/completeSimple` | 完整 | 完整 | 已基本对齐 | [pi stream](/home/dev/workspace/pi-mono/packages/ai/src/stream.ts#L25) [loushang api](/home/dev/workspace/loushang/src/loushang/ai/api/streaming.py#L51) |
| API provider registry | 完整 | 完整 | 已基本对齐 | [pi registry](/home/dev/workspace/pi-mono/packages/ai/src/api-registry.ts#L66) [loushang registry](/home/dev/workspace/loushang/src/loushang/ai/api_registry.py#L27) |
| 模型注册/查询接口 | 完整 | 完整但规模小 | 语义对齐，数据面不足 | [pi models](/home/dev/workspace/pi-mono/packages/ai/src/models.ts#L20) [loushang exports](/home/dev/workspace/loushang/src/loushang/ai/__init__.py#L36) |
| 标准消息类型：`text/thinking/toolCall/image/toolResult` | 完整 | 完整 | 已基本对齐 | [pi types](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L137) [loushang types](/home/dev/workspace/loushang/src/loushang/ai/types.py#L7) |
| StopReason：`stop/length/toolUse/error/aborted` | 完整 | 完整 | 已对齐 | [pi types](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L182) [loushang types](/home/dev/workspace/loushang/src/loushang/ai/types.py#L97) |
| streaming event 语义：`text_* thinking_* toolcall_* done/error` | 完整 | 完整 | 已基本对齐 | [pi README events](/home/dev/workspace/pi-mono/packages/ai/README.md#L374) [loushang assembler](../../../src/loushang/ai/event_stream/assembler.py) |
| abort 语义 | 完整 | 完整 | 已基本对齐 | [pi abort tests](/home/dev/workspace/pi-mono/packages/ai/test/abort.test.ts#L30) [loushang aborted handling](../../../src/loushang/ai/event_stream/assembler.py) |
| overflow 检测 | 完整 | 完整 | 已基本对齐 | [pi overflow](/home/dev/workspace/pi-mono/packages/ai/src/utils/overflow.ts#L12) [loushang overflow](/home/dev/workspace/loushang/src/loushang/ai/utils/overflow.py#L14) |
| `ThinkingLevel/CacheRetention/Transport/xhigh` | 完整 | 基本完整 | 已基本对齐 | [pi options](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L45) [loushang options](/home/dev/workspace/loushang/src/loushang/ai/options.py#L52) |
| `supportsXhigh` 模型级能力 | 有显式 helper | 缺少统一 helper/策略 | 部分缺失 | [pi helper](/home/dev/workspace/pi-mono/packages/ai/src/models.ts#L55) |
| Tool schema 校验 | 完整 | 完整但实现较简 | 基本对齐 | [pi validation](/home/dev/workspace/pi-mono/packages/ai/src/utils/validation.ts#L49) [loushang validation](/home/dev/workspace/loushang/src/loushang/ai/tool/validation.py#L25) |
| Tool call replay / cross-provider transform | 完整 | 完整 | 已基本对齐 | [pi transform](/home/dev/workspace/pi-mono/packages/ai/src/providers/transform-messages.ts#L13) [loushang tool transform](../../../src/loushang/ai/tool/transform.py) |
| Tool call ID normalization | 完整 | 完整 | 已基本对齐 | [pi anthropic note](/home/dev/workspace/pi-mono/packages/ai/src/providers/anthropic.ts#L697) [loushang normalize](/home/dev/workspace/loushang/src/loushang/ai/tool/transform.py#L240) |
| Orphaned tool call repair | 完整 | 完整 | 已基本对齐 | [pi transform](/home/dev/workspace/pi-mono/packages/ai/src/providers/transform-messages.ts#L98) [loushang tool transform](../../../src/loushang/ai/tool/transform.py) |
| Strict pairing / late tool result / duplicate result 检查 | 有较成熟语义 | 有 | 基本对齐 | [loushang strict](/home/dev/workspace/loushang/src/loushang/ai/tool/transform.py#L31) |
| OpenAI compat：`requiresToolResultName` | 完整 | 有 | 基本对齐 | [pi compat](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L268) [loushang openai completions](../../../src/loushang/ai/providers/openai_completions.py) |
| OpenAI compat：`requiresAssistantAfterToolResult` | 完整 | 有 | 基本对齐 | [pi openai](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-completions.ts#L521) [loushang openai responses shared](../../../src/loushang/ai/providers/openai_responses_shared.py) |
| OpenAI compat：`supportsStrictMode` | 有 | 无统一能力暴露 | 缺失 | [pi types compat](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L280) |
| OpenAI compat：`requiresThinkingAsText` | 有 | 只有局部降级，没有完整 compat 层 | 部分缺失 | [pi types compat](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L273) [loushang tool transform](../../../src/loushang/ai/tool/transform.py) |
| OpenAI compat：`thinkingFormat` 多形态 | 有 | 无 | 缺失 | [pi types compat](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L275) [pi openai](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-completions.ts#L407) |
| OpenRouter/Vercel routing 配置 | 有 | 无 | 缺失 | [pi routing](/home/dev/workspace/pi-mono/packages/ai/src/types.ts#L294) |
| 图像输入 | 完整 | 基本完整 | 已基本对齐 | [pi stream image tests](/home/dev/workspace/pi-mono/packages/ai/test/stream.test.ts#L223) [loushang OpenAI completions tests](../../../tests/providers/test_openai_completions_provider.py) |
| 图像输出事件 | 完整 | 完整 | 已基本对齐 | [loushang assembler](../../../src/loushang/ai/event_stream/assembler.py) |
| Tool result 中只有图片 | 多 provider 支持 | OpenAI 路径不支持 | 关键缺失 | [pi image tool result](/home/dev/workspace/pi-mono/packages/ai/test/image-tool-result.test.ts#L26) [loushang text-only limit](/home/dev/workspace/loushang/src/loushang/ai/tool/providers.py#L115) |
| Tool result 中图文混合 | 多 provider 支持 | OpenAI 路径不支持 | 关键缺失 | [pi openai completions images](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-completions.ts#L641) |
| Thinking signature / encrypted continuity | 完整度较高 | 有字段和局部处理，但未闭环 | 关键缺失 | [pi openai responses](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-responses.ts#L222) [loushang gap doc](/home/dev/workspace/loushang/docs/architecture/ai/validation/loushang-ai-gap-vs-pi-ai-round-1.md#L151) |
| Response ID / reasoning replay | 有 | 很弱，只有局部处理 | 缺失 | [pi responseid test](/home/dev/workspace/pi-mono/packages/ai/test/responseid.test.ts#L21) [loushang openai responses shared](../../../src/loushang/ai/providers/openai_responses_shared.py) |
| Built-in providers/API 覆盖 | 9 条内建 API | 3 条内建 API | 最大 gap | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L366) [loushang bootstrap](/home/dev/workspace/loushang/src/loushang/ai/bootstrap.py#L13) |
| Anthropic provider | 有 | 有 | 对齐 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L367) [loushang bootstrap](/home/dev/workspace/loushang/src/loushang/ai/bootstrap.py#L56) |
| OpenAI Completions provider | 有 | 有 | 对齐 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L373) [loushang bootstrap](/home/dev/workspace/loushang/src/loushang/ai/bootstrap.py#L63) |
| OpenAI Responses provider | 有 | 有 | 对齐 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L385) [loushang bootstrap](/home/dev/workspace/loushang/src/loushang/ai/bootstrap.py#L69) |
| OpenAI Codex Responses provider | 有 | 有实现，但当前不在 built-in models 中默认注册 | 部分对齐 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L397) [loushang codex provider](../../../src/loushang/ai/providers/openai_codex_responses.py) |
| Azure OpenAI Responses provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L391) |
| Google Generative AI provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L403) |
| Google Gemini CLI provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L409) |
| Google Vertex provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L415) |
| Mistral provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L379) |
| Bedrock provider | 有 | 无 | 缺失 | [pi builtins](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L421) |
| Faux provider | 有 | 有 | 对齐 | [pi faux](/home/dev/workspace/pi-mono/packages/ai/src/providers/faux.ts) [loushang faux](/home/dev/workspace/loushang/src/loushang/ai/providers/faux.py#L8) |
| OAuth provider registry | 完整 | 有 registry | 部分对齐 | [pi oauth index](/home/dev/workspace/pi-mono/packages/ai/src/utils/oauth/index.ts#L50) [loushang oauth registry](/home/dev/workspace/loushang/src/loushang/ai/auth/registry.py#L8) |
| OAuth providers 默认内建 | 5 个 | 仅 Anthropic 且未看见默认 bootstrap | 缺失 | [pi oauth index](/home/dev/workspace/pi-mono/packages/ai/src/utils/oauth/index.ts#L13) [loushang anthropic oauth](/home/dev/workspace/loushang/src/loushang/ai/auth/providers/anthropic.py#L64) |
| CLI OAuth login | 有 | 无 | 缺失 | [pi cli](/home/dev/workspace/pi-mono/packages/ai/src/cli.ts#L70) |
| CLI 模型/endpoint/binding 管理 | 简单 | 更强 | `loushang` 反而更强 | [loushang cli](/home/dev/workspace/loushang/src/loushang/ai/cli/__main__.py#L338) |
| 懒加载 provider module | 有 | 无 | 缺失 | [pi lazy](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts#L168) |
| 浏览器兼容/Node-safe import | 有 | 无对应目标 | 若追平 SDK 体验则缺失 | [pi browser-safe](/home/dev/workspace/pi-mono/packages/ai/src/env-api-keys.ts#L1) |
| TypeBox 顶层导出 | 有 | 无 Python 对应物 | 非必要差异 | [pi index](/home/dev/workspace/pi-mono/packages/ai/src/index.ts#L1) |
| 自动模型生成/超大模型目录 | 有 `generate-models.ts` + 大型 generated registry | 无自动生成，模型目录很小 | 明显缺失 | [pi generate-models](/home/dev/workspace/pi-mono/packages/ai/scripts/generate-models.ts) [loushang models](/home/dev/workspace/loushang/src/loushang/ai/model/models.json#L3) |
| 测试覆盖深度 | 很深，覆盖跨 provider、OAuth、image/tool result、abort、xhigh、reasoning replay | 中等偏深，但覆盖面更窄 | 仍有 gap | [pi tests](/home/dev/workspace/pi-mono/packages/ai/test) [loushang tests](../../../tests) |

## 剩余 Gap 按优先级整理

### P0

- 补 provider/API：
  - 将 `openai-codex-responses` 纳入 built-in models/bootstrap coverage
  - `azure-openai-responses`
  - `google-generative-ai`
  - `google-gemini-cli`
  - `google-vertex`
  - `mistral-conversations`
  - `bedrock-converse-stream`
- 补 OpenAI/Responses/Google 路径下的 image tool result 闭环

### P1

- 补完整 OAuth/login 体系：
  - `github-copilot`
  - `openai-codex`
  - `google-gemini-cli`
  - `google-antigravity`
  - Anthropic 从最小实现升级到可用闭环
- 补 compat 层剩余能力：
  - `supportsStrictMode`
  - `requiresThinkingAsText`
  - `thinkingFormat`
  - routing 元数据

### P2

- 补 reasoning continuity：
  - `reasoning.encrypted_content`
  - thought signature continuity
  - response id replay
  - aborted turn 后 reasoning history 跳过语义
- 扩模型目录与自动生成机制

### P3

- 如果目标是库分发体验接近 `pi-ai`，再补：
  - provider 懒加载
  - browser-safe runtime import
  - 文档与 CLI login 体验

## 实际判断

- 如果目标是 Python server-side runtime 能力，`loushang.ai` 不必完全照搬 `pi-ai` 的浏览器兼容与 TypeBox 导出层。
- 但如果目标是“功能面对齐 `pi-ai`”，当前最先需要补的仍然是 provider 覆盖、OAuth/login 与 image tool result。
- 在当前阶段，`loushang.ai` 的基础框架已经够用，瓶颈主要在“能力面不够宽”和“复杂语义未闭环”。

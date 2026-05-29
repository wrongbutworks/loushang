# PI-AI Abstraction Variation Strategy

## Scope

本文档总结 `pi-ai` 如何处理三类持续变化：

- model family handling
- auth
- transport

本文档的目的不是复述 `pi-ai` 的全部实现细节，而是提炼它在架构层的变化吸收策略，为 `loushang-ai` 后续更新组件设计提供参考。

本文档只讨论：

- `pi-ai` 如何在架构上安放这三类变化
- 这些变化主要由哪些组件或责任簇吸收
- 哪些点值得 `loushang-ai` 借鉴

本文档不讨论：

- `loushang-ai` 的最终设计结论
- provider 逐行实现 walkthrough
- 每个 provider 的完整选项列表

---

## Reading Rule

这里的“变化策略”不是在说：

- `pi-ai` 已经有一套单独命名的“三大组件”

而是在说：

- 从白盒视角看，`pi-ai` 已经把这三类变化放到了相对稳定的位置
- 它没有把这些变化平均散落到顶层 API、event stream 和 message types 中

---

## 1. Model Family Handling

## 1.1 `pi-ai` 怎么处理

`pi-ai` 没有把 model family handling 做成一个单独显式导出的 capability resolver，而它实际上已经把这类变化放进了两层结构：

1. `Model Registry`
2. provider-specific stream/options logic

直接证据：

- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)
- [models.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.ts)
- [models.generated.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.generated.ts)
- [scripts/generate-models.ts](/home/dev/workspace/pi-mono/packages/ai/scripts/generate-models.ts)

其中：

- `KnownApi` 明确区分：
  - `openai-completions`
  - `openai-responses`
  - `openai-codex-responses`
  - `azure-openai-responses`
  - `anthropic-messages`
  - 等
- `Model` 元数据中已经隐含：
  - provider family
  - api family
  - input/output capability
  - reasoning capability
  - context/pricing metadata

这说明在 `pi-ai` 里：

- model family handling 不是“运行时临时猜”
- 而是“先在 model metadata 层确定，再在 provider 层消费”

## 1.2 关键做法

`pi-ai` 对 model family 的关键做法有三条：

1. 先在模型元数据层区分协议族
- 例如不是简单一个 `openai`
- 而是拆成 `openai-completions` / `openai-responses` / `openai-codex-responses`

2. provider-specific logic 只处理“这个 family 该怎么说话”
- 例如 `openai-responses.ts`
- 例如 `openai-codex-responses.ts`

3. 某些能力判断上提为 model helper
- 例如 `supportsXhigh`
- 而不是让每个 provider 各自猜能力

## 1.3 启示

对 `loushang-ai` 来说，`pi-ai` 的启示不是“必须复制它的所有模型表”，而是：

- model family handling 应首先体现在 model metadata / capability metadata 层
- provider adapter 应消费这种 metadata，而不是定义它
- `openai-completions` / `openai-responses` / `openai-codex-responses` 这种 family distinction 应被视为一级架构事实，而不是实现细节

---

## 2. Auth

## 2.1 `pi-ai` 怎么处理

`pi-ai` 没有把 auth 简化为“每个 provider 自己从环境变量里取 key”。  
它实际分成了至少三层：

1. env api key resolution
2. OAuth provider integration
3. provider-specific client creation

直接证据：

- [env-api-keys.ts](/home/dev/workspace/pi-mono/packages/ai/src/env-api-keys.ts)
- [README.md](/home/dev/workspace/pi-mono/packages/ai/README.md)
- `src/utils/oauth/*`
- 各 provider 的 `createClient(...)`

这说明在 `pi-ai` 里：

- auth 输入不是完全散在 provider 文件里
- provider 文件主要负责“把已解析 auth material 接到 client”
- env / OAuth / refresh 之类的支撑被单独放到了 helper / oauth 侧

## 2.2 关键做法

`pi-ai` 对 auth 的关键做法有三条：

1. 最小 API key resolution 有统一入口
- 例如不同 provider 对应不同 env var

2. OAuth 不直接揉进顶层 API
- 而是作为专门的支撑层存在

3. provider 仍保留最后一公里接线责任
- 例如不同 SDK/client 的 auth header / token 注入不同

所以 `pi-ai` 的取向不是：

- 把 auth 完全统一成一个抽象对象后再传到底

而是：

- 上层统一解析 auth 输入
- provider 保留接入具体 client 的控制权

## 2.3 启示

对 `loushang-ai` 来说，这意味着：

- auth 应被识别为边界支撑能力
- 不应继续长期停留在“provider 自己拿 `api_key` header”阶段
- 但也不必一开始就做成一个巨大的通用 auth framework

更合理的演进方式是：

1. 先有统一 auth input / resolution
2. 再有 provider-specific auth binding
3. OAuth 再作为下一层扩展

---

## 3. Transport

## 3.1 `pi-ai` 怎么处理

`pi-ai` 并没有把 transport 抽成一个单独统一的顶层组件，但它已经明确把 transport 视为一个稳定变化维度。

直接证据：

- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)
  - `transport?: "sse" | "websocket" | "auto"`
- [CHANGELOG.md](/home/dev/workspace/pi-mono/packages/ai/CHANGELOG.md)
  - 多次提到 `openai-codex-responses` 的 websocket support
- [openai-codex-responses.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-codex-responses.ts)
  - transport-specific logic

这说明在 `pi-ai` 里：

- transport 不是 hidden implementation detail
- 至少在 API/options 层，它已被承认为 provider capability / invocation strategy 的一部分

## 3.2 关键做法

`pi-ai` 对 transport 的关键做法有两条：

1. transport 是 provider-specific option
- 不是顶层 message/event 协议的一部分
- 也不是 `Context` 的一部分

2. transport 差异主要被 provider adapter 吸收
- 例如 SSE
- 例如 websocket
- 例如 SDK-native streaming

所以 `pi-ai` 的取向不是：

- 建一个全局 transport orchestrator

而是：

- 将 transport 视为 provider boundary 内的变化维度
- 必要时再在 shared options 上显式暴露

## 3.3 启示

对 `loushang-ai` 来说，这意味着：

- transport 适合先挂在 provider adapter / carrier strategy 侧
- 不是现在就要拉成顶层主组件
- 但从架构上应被明确识别为一个后续会长大的变化面

---

## 4. Combined View

把三类变化放在一起看，`pi-ai` 的整体策略可以收成下面三句：

1. model family handling 主要落在 model metadata / capability metadata
2. auth 主要落在边界支撑能力与 provider client binding
3. transport 主要落在 provider adapter 的 invocation strategy

换句话说：

- `pi-ai` 没有把这三类变化都上提到 top-level AI API
- 也没有把它们完全散到 provider 文件里
- 而是让它们各自停留在最接近变化来源、又不污染主协议的位置

---

## 5. Suggested Borrowing For Loushang-AI

如果只借鉴 `pi-ai` 的变化吸收策略，而不复制其全部实现，最值得借的有三点：

### 5.1 对 model family 的借鉴

- 在 `Model Registry` 旁边引入更明确的 capability / family metadata
- 不把 `openai-completions` / `openai-responses` / `openai-codex-responses` 的差异压扁成一个 `openai`

### 5.2 对 auth 的借鉴

- 先做统一 auth input / resolution
- 再由 provider adapter 负责具体 client binding
- OAuth 作为下一层扩展，而不是混进第一轮 provider 实现

### 5.3 对 transport 的借鉴

- 先把 transport 视为 provider boundary 内部策略
- 必要时再提升为更明确的 public/provider option
- 不要过早把 transport 逻辑揉进 message/content/event 主协议

---

## Conclusion

`pi-ai` 对 `model family / auth / transport` 三类变化的处理，整体上体现了一个很稳定的架构取向：

- 让变化停留在最接近变化来源的层次
- 让主 message/content/event 协议尽量稳定
- 让 provider adapter 成为真正的变化吸收边界

这对 `loushang-ai` 的直接启示不是“复制 `pi-ai`”，而是：

- 继续保持 `Top-Level AI API`、`RawAssembler`、`EventStream` 的稳定
- 把 model family、auth、transport 的扩展主要放到：
  - model capability side
  - auth support side
  - provider adapter / carrier strategy side

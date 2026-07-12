# Loushang-AI Adaptability Design V1

## Purpose

本文档将 [Loushang-AI Adaptability NFR](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-adaptability-NFR.md) 落到可实现的组件职责、接线点与推进顺序上。

本文档不重新定义整体白盒结构，而是回答：

- `Model Capability` 应包含什么
- `Model Capability Resolver` 应在何处参与决策
- `Auth Support` 的边界是什么
- `Provider Boundary Support` 先承接哪些 shared logic
- 下一阶段应如何推进代码实现

---

## Inputs

- [Reference AI SDK Adaptability NFR](/home/dev/workspace/loushang/docs/architecture/ai/reference/reference-ai-sdk/reference-ai-sdk-adaptability-NFR.md)
- [Reference AI SDK Abstraction Variation Strategy](/home/dev/workspace/loushang/docs/architecture/ai/reference/reference-ai-sdk/reference-ai-sdk-abstraction-variation-strategy.md)
- [Loushang-AI Adaptability NFR](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-adaptability-NFR.md)
- [Loushang-AI Component Structure V1](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-component-structure-v1.md)
- [Loushang-AI Component Interfaces V1](/home/dev/workspace/loushang/docs/architecture/ai/loushang-ai-component-interfaces-v1.md)
- [Loushang AI Gap vs Reference AI SDK Round 1](/home/dev/workspace/loushang/docs/architecture/ai/validation/loushang-ai-gap-vs-reference-ai-sdk-round-1.md)

---

## Position

`loushang-ai` 当前已经有三条真实协议面：

- `anthropic-messages`
- `openai-completions`
- `openai-responses`

因此，下一阶段的重点不应再是继续平铺 provider，而应先把适应性骨架做实。

参考 `reference AI SDK`，最值得吸收的不是某个 provider 文件本身，而是三类变化的吸收方式：

- model family handling
- auth variation handling
- transport / carrier variation handling

---

## Design Principles

### 1. 变化解释与变化执行分离

`loushang-ai` 需要区分：

- 变化解释
  - 判断模型支持什么、限制什么、允许什么
- 变化执行
  - 具体 provider 如何发请求、走哪条 transport、映射哪种 payload

前者主要落在：

- `Model Component`

后者主要落在：

- `Provider Adapter`
- `Provider Boundary Support`

---

### 2. 稳定骨架与可增殖单元分离

参考 `reference AI SDK`，不应把具体 provider adapter 吞进稳定骨架。

应保持：

- `Provider Adapter`
  - 独立、可增殖、持续变化

并让稳定骨架承接：

- `Provider Boundary Support`
  - protocol shape
  - transport strategy
  - carrier invocation
  - payload transformation
  - error mapping

---

### 3. 认证变化是独立变化轴

`auth` 不应只是边界支撑链里的一个小细节。

它影响：

- endpoint auth declaration
- API key env fallback
- explicit API key / request-level OAuth bearer resolution
- request header binding

因此它应保持为独立组件：

- `Auth Support`

---

## Model Component Design

`Model Component` 由三部分组成：

- `Model Registry`
- `Model Capability`
- `Model Capability Resolver`

---

### Model Registry

职责保持克制：

- 注册模型定义
- 按 model id 查找
- 暴露原始 model metadata

不负责：

- 动态能力判断
- transport/auth 决策

---

### Model Capability

`Model Capability` 是能力事实模型，而不是决策器。

第一阶段建议收敛这些字段：

- `preferred_api`
- `allowed_apis`
- `supports_thinking`
- `supports_tool_use`
- `supports_image_input`
- `supports_image_output`
- `context_window`
- `max_output_tokens`

第二阶段再考虑：

- `supports_reasoning_levels`
- `supports_transport_modes`
- `requires_auth_kind`
- provider-compatible overrides

这里的重点是：

- `Model Capability` 表达“事实与约束”
- 不表达“执行动作”

---

### Model Capability Resolver

`Model Capability Resolver` 负责把：

- model metadata
- capability metadata
- provider/model family knowledge

解释为可执行判断。

它至少应回答：

- 当前模型允许哪些 `api`
- 当前请求解析出的 `api` 是否允许
- 当前模型是否支持 thinking/tool/image
- 当前模型的最大 context window / output 上限是多少

其中 `contextWindow` 在当前设计里应被解释为模型目录中的最大窗口上限；未来真正的会话预算与压缩阈值应由 `session/runtime` 层决定，而不是由 provider endpoint default 决定。

第一阶段它应参与的运行时位置：

- `api/streaming.py`

具体作用：

- 在 provider lookup 之前进行 capability gate
- 对明显不兼容情况 fail fast

例如：

- model 声明 `openai-responses`，但 capability 只允许 `openai-completions`
- 模型不支持 image input，但 `Context` 中带有 `ImagePart`
- 模型不支持 thinking，但调用方要求 reasoning

---

## Auth Support Design

`Auth Support` 是独立组件，不收进 `Provider Boundary Support`。

职责：

- 接收 `CallOptions` 中调用方显式提供的 API key 或 typed request auth
- 在没有显式 credential 时，按 endpoint 声明解析 API key env fallback
- 将调用期 credential 归一为只包含最终 headers 的 auth view

不负责：

- OAuth provider 注册
- login、browser、callback 或 logout
- token refresh、credential store 或账号切换

关键原则：

- provider adapter 不自己去猜 env
- top-level API 不自己拼 header
- examples 不自己重复 provider auth binding 逻辑

provider adapter 只消费：

- 已解析的 auth view

---

### 账号态 Code Plan 接入约束

ChatGPT Coding Plan 是凭据来源和产品场景，不是 provider、protocol 或 API
family。只要请求仍遵循 OpenAI Responses，就必须复用 `openai-responses` adapter。

这类场景的共同特征是：

- 调用方在进入 `loushang.ai` 之前已经取得凭证
- provider 服务端根据账号身份与订阅套餐决定 entitlement
- 请求时往往需要 provider account binding，而不只是 `Authorization: Bearer <key>`

因此，对 `loushang-ai` 来说，这类接入必须遵守以下约束：

1. provider 仍是 `openai`，endpoint 只标识具体 route，`api` 仍是
   `openai-responses`
2. 它要求调用期 `OAuthBearerAuth`，不是 API key；完整 OAuth credential 留在认证层
- 不应继续用 `OPENAI_API_KEY` 这类命名暗示平台 API key
- 更不应让 example 或 live test 把账号态 token 伪装成普通 API key

3. `Model/Auth` 只表达认证需求，不表达运行时 credential 细节
- 模型目录应只声明：
  - 需要哪种 auth kind
- credential source/provider 与 model provider 是独立身份轴；例如
  `openai-codex` credential 可以服务 `openai` model route
- 具体 credential source 由应用和 `loushang.ai.auth` 选择，不由 AI invocation 猜测
- 不应在 model metadata 中塞入：
  - account id
  - plan
  - subscription entitlement
  - workspace binding

4. 完整 credential 与请求级认证材料分层
- `OAuthCredentials` 的 refresh token、expiry 和 account state 留在 `loushang.ai.auth`
- 有效 `access_token` 转换为 `CallOptions.auth=OAuthBearerAuth(...)`
- 多 header 认证由认证层完整构造为 `CallOptions.auth=HeadersAuth(...)`
- AI 请求链只消费一个 typed `CallOptions.auth`

5. provider 不应自己成为登录产品层
- provider adapter 不负责：
  - 登录网页 UI
  - 套餐购买逻辑
  - 用户中心逻辑
- provider adapter 只负责消费已解析的 auth view，并把它绑定到请求

---

### Resolved Auth View 约束

为避免 provider 各自重新猜 credential 形状，`Auth Support` 应产出统一的 resolved auth view。

该 view 的目标不是成为一个超大抽象对象，而是成为 provider 可直接绑定的最小运行时材料。

当前 view 只覆盖：

- `headers`

输入来源只允许：

- `CallOptions.auth`
- endpoint auth 声明允许的 API key env fallback

OAuth bearer credential 必须由调用方显式传入；AI 包不读取完整 credential、store，
也不刷新 token。

关键约束：

- top-level API 不自己拼认证 header
- provider 不自己读 env
- provider 不自己决定 credential source
- provider 只消费 resolved auth view

---

### `loushang-ai` 的边界约束

对 `loushang-ai` 来说，边界应固定在：

- 统一 AI provider SDK
- 统一模型目录与 provider 选择
- 统一 auth 解析
- 统一 request / stream / message / tool 协议

它拥有的职责包括：

- 解释某个 endpoint 声明的 auth 要求
- 将显式 credential 或 API key env fallback 解析为 resolved auth view
- 将 resolved auth view 绑定到 provider request

模型调用路径不拥有的职责包括：

- OAuth provider 注册
- login、browser、callback、refresh、credential store、账号切换或 logout；这些能力由
  同属 AI 包的 `loushang.ai.auth` 显式 API 承担，不得在模型调用期间隐式触发
- 用户订阅系统主数据
- 套餐售卖与购买逻辑
- 用户中心或工作区产品逻辑
- agent/session/product orchestration

一句话：

- `loushang-ai` 只处理调用期 credential 到请求 headers 的解析与绑定
- 它不处理 OAuth lifecycle 或认证产品能力

---

### 对 ChatGPT route 的直接约束

1. catalog route 使用 `api: openai-responses`
2. `loushang.ai.auth` 读取完整 credentials 并派生完整认证 headers；调用边界通过
   `HeadersAuth` 一次性接收
3. 模型调用路径不解析 `~/.codex/auth.json`，不登录、不 refresh、不持久化
4. `~/.codex/auth.json` 只由应用边缘 example 读取

---

## Provider Boundary Support Design

`Provider Boundary Support` 负责稳定边界骨架，不负责承接具体 provider 变化实例。

其内部组成：

- `ApiProvider Protocol`
- `Transport Strategy`
- `Carrier Invocation`
- `Provider Payload Transformation`
- `Error Mapping`

---

### ApiProvider Protocol

职责：

- 定义 adapter 的最小协议面
- 约束 registry 与 top-level API 如何调用 provider

不负责：

- family-specific capability 判断
- auth resolution

---

### Transport Strategy

第一阶段不追求复杂实现，只负责：

- 声明当前 provider 走什么 transport
- 为 future `sse` / `websocket` / `sdk-native stream` 预留统一位置

当前的关键原则是：

- transport 差异不应泄漏到 public event 协议

---

### Carrier Invocation

职责：

- 将 provider adapter 的语义请求交给具体 carrier
- 如：
  - `httpx-thin`
  - future SDK client

第一阶段它仍可很薄，但要把“carrier 是边界执行细节”这件事正式固定下来。

---

### Provider Payload Transformation

职责：

- 输入消息映射
- tool result 输入映射
- provider-specific payload 细节吸收

第一阶段先继续服务：

- `anthropic-messages`
- `openai-completions`
- `openai-responses`

---

### Error Mapping

职责：

- 把 provider-specific 异常、stop reason、transport failure 收敛为统一 error view

第一阶段重点：

- fail fast
- 明确错误原因

不追求完整 taxonomy。

---

## Provider Adapter Design

`Provider Adapter` 保持独立。

它是：

- 边界变化实例的承接点
- 可增殖的执行单元族

它不是：

- 稳定边界骨架本身

当前这条判断与 `reference AI SDK` 的结构最接近：

- provider 文件独立增长
- shared support 另行沉淀

---

## Runtime Wiring

下一阶段的最小接线顺序应是：

1. `Top-Level AI API`
   - 调用 `Model Registry`
2. `Model Registry`
   - 返回 model definition
3. `Model Capability Resolver`
   - 生成 capability view
   - 对请求做 fail-fast gate
4. `ApiProvider Registry`
   - 取 provider adapter
5. `Auth Support`
   - 解析 auth view
6. `Provider Adapter`
   - 结合 capability view、auth view、transport strategy
   - 生成 raw parts
7. `Event Stream Component`
   - 收敛为 public event/message

这意味着：

- `Model Capability Resolver` 应先于 provider 执行
- `Auth Support` 应先于 payload binding
- `Transport Strategy` 应在 provider boundary 内被消费

---

## Implementation Order

建议按下面顺序推进，而不是三块一起做。

### Phase 1

- 让 `Model Capability` / `Model Capability Resolver` 真正进入 `api/streaming.py`
- 新增 fail-fast tests：
  - unsupported api
  - unsupported image input
  - unsupported thinking

### Phase 2

- 让 `Auth Support` 进入真实 provider binding 主链
- 停止 provider 直接读 env / 直接拼 auth header

### Phase 3

- 让 `Provider Boundary Support` 承接更多 shared logic：
  - payload transformation
  - error mapping
  - transport declaration

### Phase 4

- 再考虑 provider-specific options family

这个顺序的理由是：

- 先解释约束
- 再收敛认证
- 再抽边界共享逻辑
- 最后才抽更细的 provider options

---

## Non-Goals

这版设计不包含：

- OAuth lifecycle 或认证产品设计
- websocket transport 正式实现
- `Tool Semantic Component` 的完整代码化

这些都依赖前述骨架先稳定。

---

## Summary

这版适应性设计的核心判断是：

- `Model Component` 负责解释服务端已存在的模型约束
- `Auth Support` 负责集中收敛调用期 credential 到请求 headers 的差异
- `Provider Boundary Support` 负责稳定边界骨架
- `Provider Adapter` 保持独立、承接变化实例

下一阶段不应再平铺 provider 或 options，而应先把这套适应性骨架接入运行链。

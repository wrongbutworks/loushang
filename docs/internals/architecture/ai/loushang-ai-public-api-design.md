# `loushang.ai` 公共 API 设计清单

> Status: historical pre-freeze design draft.
>
> This file is retained as background design material. It is not the current
> public API contract. The frozen contract is documented in
> [`ARD-003-core-freeze-contract.md`](./ARD-003-core-freeze-contract.md),
> [`loushang-ai-top-level-api-signatures.md`](./loushang-ai-top-level-api-signatures.md),
> [`src/loushang/ai/README.md`](../../../../src/loushang/ai/README.md), and
> [`docs/internals/architecture/ai/core-freeze-verification.md`](./core-freeze-verification.md).
> Names below such as `ResolvedRequest`, `ResolvedEndpoint`, and provider
> registry functions on the root package describe an earlier proposal, not the
> current frozen surface.

## 文档目的

本文用于收敛 `src/loushang/ai` 的对外能力边界。

`loushang.ai` 应被定义为：

- 底层模型接入与协议适配层
- 统一消息/工具/流式事件协议层
- 模型领域对象、registry、Provider 注册、认证解析的基础设施层

`loushang.ai` 不应被定义为：

- Agent 编排层
- 会话状态管理层
- HTTP 路由服务层
- 业务权限、项目配置、插件编排层

本文参考了两个公开项目的相近层设计：

- `../reference-repository/packages/ai`
- `../kilocode/packages/opencode/src/provider/*`


## 设计原则

### 1. 根包导出要少而稳

根包 `loushang.ai` 只导出最常用、最稳定、最适合上层直接依赖的能力。

### 2. 低层能力允许暴露，但要分层

底层扩展能力可以暴露给高级调用方或测试代码，但不应与主入口 API 混在同一层级叙事里。

### 3. 统一协议优先于具体厂商

上层应优先依赖统一的：

- `Context`
- `Message`
- `Tool`
- `AssistantMessageEventStream`
- `Model`

而不是直接依赖 Anthropic/OpenAI 的厂商协议。

### 4. Provider 是实现细节，Model Registry 是路由基础

对外应该以“模型能力”和“统一调用”为中心，而不是以具体厂商 SDK 为中心。

### 5. 兼容 `reference repository` 风格，吸收 `kilocode` 的实用门面

建议整体对齐 `reference repository` 的 SDK 化导出方式，同时保留必要的 provider discovery 与请求级 auth resolution。


## 职责边界

`loushang.ai` 对外应承担以下职责：

- 统一模型推理调用
- 统一流式事件协议
- 模型 registry 装载与查询
- API Provider 注册与路由
- 工具调用协议转换与校验
- 请求级认证材料解析与请求头绑定
- Provider 请求解析、endpoint 解析、运行时兼容性处理
- 上下文规范化与跨 Provider 消息兼容

`loushang.ai` 不对外承担以下职责：

- Agent 生命周期管理
- 多轮工具执行编排
- 会话存储与恢复策略
- 产品级 provider 配置中心
- HTTP / RPC 接口编排
- 权限系统与审核系统
- 插件生命周期管理


## 对外 API 分层

建议把公共 API 分为三层：

- Stable API：默认公开、长期承诺兼容
- Advanced API：面向扩展方和深度集成方
- Internal API：不承诺稳定，不应作为公开门面


## 本轮确认结果

本轮已先确认一件事：

- 重构优先级高于现有中间实现结构
- 但低于 `models.json` 的领域对象事实源

因此本轮先冻结的是 `Stable API Boundary`，而不是当前 `model/`、`provider/`、`auth/` 的实现形态。

当前确认结果如下：

- 根包 `loushang.ai` 只承诺 Stable API
- `models.json` 是底层事实源
- `model/` 包当前实现可以重写
- Advanced API 可保留在子包
- Internal API 不进入根包公共承诺

后续如果实现与 Stable API 冲突，应优先调整实现，而不是回退 Stable API 设计


## Stable API 清单

根包 `loushang.ai` 当前只承诺以下 Stable API：

- Invocation API
  - `stream`
  - `complete`
- Model Access API
  - `Model`
  - `get_model`
  - `list_models`
  - `get_providers`
- Provider Registry API
  - `register_api_provider`
  - `get_api_provider`
  - `list_api_providers`
  - `clear_api_providers`
  - `reset_api_providers`
  - `register_builtin_ai_providers`
- Unified Types
  - `Context`
  - `Message`
  - `UserMessage`
  - `AssistantMessage`
  - `ToolResultMessage`
  - `Tool`
  - `ToolCall`
  - `TextPart`
  - `ImagePart`
  - `ThinkingPart`
  - `Usage`
  - `StopReason`
  - `AssistantMessageEvent`
  - `AssistantMessageEventStream`
- Base Semantics Helpers
  - `normalize_context`
  - `transform_messages`
  - `validate_tool_call`
  - `validate_tool_arguments`
  - `normalize_tool_call_id_for_model`
- Stable Option Types
  - `CallOptions`
  - `ReasoningOptions`
  - `RetryOptions`
  - `TimeoutOptions`
  - `StructuredOutputOptions`
  - `ThinkingLevel`
  - `CacheRetention`

## API 层派生对象

在 `models.json` 原生领域对象之外，API 层允许引入少量派生对象。

判断标准是：

- 上层是否必须理解它
- 没有它时，上层是否会被迫理解内部解析过程
- 它是否适合作为稳定公共语义存在

### 必须有

#### 1. `Model`

作用：

- 作为上层拿到的“可调用模型句柄”
- 作为统一 Invocation API 的输入对象

说明：

- 它不是 `models.json` 原生对象
- 它应由 `Provider + Endpoint + EndpointModel + Auth` 派生得到
- 当前 Stable API 只承诺最小字段集合：
  - `id`
  - `provider`
  - `endpoint`
  - `api`

#### 2. `Context`

作用：

- 作为统一调用输入语义

#### 3. `AssistantMessageEventStream`

作用：

- 作为统一流式输出语义

#### 4. `ResolvedRequest`

作用：

- 作为从 API 层到 provider 实现层之间的请求边界对象

说明：

- 它属于 Advanced API
- 当前从 `loushang.ai.provider` 子包公开

### 已实现的 Advanced API 对象

#### 1. `ResolvedEndpoint`

适用场景：

- 调试
- 可观测性
- provider route 解释

### 当前不应先有

- 旧式全局规格表对象
- 旧式绑定表对象
- 额外的 capability 投影对象
- 独立的 region/compat/defaults 中间对象

原因：

- 它们不是当前 `models.json` 原生对象
- 当前若直接引入，容易把旧实现中的中间抽象重新固化为公共模型


## `Model` 与 `ResolvedRequest` 职责草案

本轮先确认两个关键派生对象的职责边界：

- `Model`
- `ResolvedRequest`

### 1. `Model`

定位：

- 上层可直接持有的“可调用模型句柄”
- Invocation API 的直接输入对象

职责：

- 表达“这次要调用哪个模型”
- 向上层隐藏 `models.json` 的树形查找与归一化过程
- 提供统一、稳定的模型基础视图

不负责：

- 生成最终请求头
- 解析最终 baseUrl
- 合成 provider-specific payload
- 表达完整调用参数

Stable 最小字段集合确认为：

- `id`
- `provider`
- `endpoint`
- `api`

以下字段当前不进入 `Model` 的 Stable API 承诺：

- `name`
- `capability`
- `pricing`

说明：

- `name` 可作为实现附带信息存在，但不作为当前稳定边界承诺
- `capability` 更适合作为 `CapabilityView`
- `pricing` 更适合作为 `PricingView`
- 不应把它们误认成 `models.json` 原生实体

### 2. `ResolvedRequest`

定位：

- API 层到 provider 实现层之间的请求边界对象

职责：

- 收敛 `Model + Context + Runtime Options`
- 明确最终 provider / endpoint / baseUrl / headers
- 明确兼容性参数与默认参数
- 作为 provider adapter 的直接输入

不负责：

- 承担上层业务输入语义
- 作为上层长期持有的模型对象
- 表达 provider 内部 streaming 实现细节

最小字段集合确认为：

- `provider`
- `endpoint`
- `api`
- `base_url`
- `headers`

以下字段当前不进入 `ResolvedRequest` 的稳定边界承诺：

- `region`
- `candidate_base_urls`
- `compat`
- `defaults`
- `max_tokens`
- `temperature`
- `reasoning_effort`

这些字段如有需要，可先作为 Advanced API 扩展字段存在。

### 3. 二者关系

二者的关系应明确区分：

- `Model` 解决“调哪个模型”
- `ResolvedRequest` 解决“怎么把调用真正发出去”

因此：

- `Model` 应进入 Stable API 语义
- `ResolvedRequest` 更适合作为 Advanced API 语义


## 后续边界结论

本轮继续收敛 4 个剩余问题，结论如下。

### 1. `get_model(...)` / `list_models(...)`

建议冻结为：

- `get_model(...)` 返回 API 层 `Model`

原因：

- 上层拿模型的目的，是为了直接参与 `stream / complete`
- 若返回目录内部对象，会迫使上层理解中间实现结构
- 应形成稳定主链：
  - `get_model(...) -> Model -> stream/complete(...)`

### 2. Registration API

旧式注册 API：

- `register_model(...)`
- `register_model_spec(...)`
- `register_model_binding(...)`
- `register_endpoint(...)`

已从根包移除。

在新的 `models.json` 事实源前提下，这些能力不再作为根包 Stable API。
模型主轴已经收敛为 `model/domain.py`、`model/registry.py`、`model/loader.py`。

### 3. `provider/` 与 `providers/`

建议明确边界：

- `provider/`
  - 通用请求解析层
  - 边界对象层
  - request / endpoint / auth / transport / payload 语义层
- `providers/`
  - 厂商实现层
  - Anthropic / OpenAI / 其他具体接入实现

也就是：

- `provider/` 负责统一边界
- `providers/` 负责具体适配

### 4. 根包导出收敛

建议后续按以下原则收敛根包：

- 根包只保留 Stable API
- Advanced API 从子包导入
- Internal API 不进入根包公共承诺

优先收敛对象包括：

- `ModelDefinition`
- `ModelRegistry`
- 旧式全局规格表对象
- 旧式绑定表对象

这些对象不再作为根包主语义，而应逐步被新的 API 层 `Model` 取代。


## Stable API

这部分应作为根包 `loushang.ai` 的主导出面。

### A. 统一推理调用

- `stream(model, context, options=None, *, registry)`
- `complete(model, context, options=None, *, registry)`

说明：

- 这是最核心的对外能力
- 上层运行时、Agent 层、测试代码都应优先依赖它
- 保持统一输入输出协议，不泄漏 Provider 细节

### B. 模型查询

- `Model`
- `get_model(provider, endpoint, model_id)`
- `list_models(provider=None, endpoint=None, model_id=None)`
- `get_providers()`

说明：

- 这部分对应模型访问与路由能力
- 这是根包长期承诺的稳定查询面

### C. API Provider 注册与查询

- `register_api_provider(provider)`
- `get_api_provider(api)`
- `list_api_providers()`
- `clear_api_providers()`
- `reset_api_providers(...)`
- `register_builtin_ai_providers(...)`

说明：

- 这部分负责把统一 API 名称映射到具体 Provider 实现
- 是整个推理入口的运行基础设施

### D. 统一协议类型

- `Context`
- `Message`
- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`
- `Tool`
- `ToolCall`
- `TextPart`
- `ImagePart`
- `ThinkingPart`
- `Usage`
- `StopReason`
- `AssistantMessageEvent`
- `AssistantMessageEventStream`

说明：

- 这部分是所有上层模块和测试的共享协议
- 必须稳定

### E. 基础上下文与工具能力

- `normalize_context(...)`
- `transform_messages(...)`
- `validate_tool_call(...)`
- `validate_tool_arguments(...)`
- `normalize_tool_call_id_for_model(...)`

说明：

- 这些能力本质上属于“统一协议层”的一部分
- 上层如果要做工具编排、跨模型切换或上下文修复，会直接依赖它们

### F. 调用选项类型

- `CallOptions`
- `ReasoningOptions`
- `RetryOptions`
- `TimeoutOptions`
- `StructuredOutputOptions`
- `ThinkingLevel`
- `CacheRetention`

说明：

- 这些类型用于统一表达核心调用参数
- 应稳定暴露给上层，避免上层直接组装任意 dict
- provider 或产品专用选项不进入 core public surface；产品场景通过 catalog 复用协议 adapter


## Advanced API

这部分可以公开，但不建议上层默认依赖。

### A. 模型域与装载

- `ModelRegistry`
- `get_default_model_registry()`
- `Model`
- `Endpoint`
- `Provider`
- `Auth`
- `Capabilities`
- `Defaults`
- `Compat`
- `Pricing`

适用场景：

- 直接访问模型 registry
- 自定义 registry 装载
- 调试场景读取模型域对象

说明：

- 旧模型中间层与旧投影对象已不再是当前模型子包主轴
- `loader.py` 主要承担内部初始化职责，不建议作为根包公开面

### B. Provider 请求解析

- `resolve_endpoint_for_model(...)`
- `resolve_request_for_model(...)`
- `ResolvedEndpoint`
- `ResolvedRequest`

适用场景：

- 调试请求路由
- 做可观测性与审计
- 做 provider request snapshot 测试

说明：

- provider 请求解析只公开解析结果与入口函数
- payload 组装、transport/carrier 与协议默认值适配属于 provider 内部实现，不作为稳定公共 API

### C. 请求级认证

- `loushang.ai.auth.OAuthCredentials`（认证生命周期层，不进入 AI request）
- `CallOptions.auth`

适用场景：

- 将 `CallOptions.auth` 中的 credential 解析成 provider request headers
- 未显式传入 OAuth credential 时，根据 `models.json.auth` 做 API key env fallback 或 OAuth missing-auth 诊断
- 对 provider request auth header 做统一构造与脱敏配合

说明：

- `CallOptions.auth` 是唯一 request-level 认证入口
- `HeadersAuth` 是完整、显式的 header override，不继承 catalog auth headers
- OAuth login、refresh、credential store 和 provider registry 统一归属
  `loushang.ai.auth`，但不进入模型调用的隐式执行路径
- `OAuthCredentials.refresh_token`、expiry 和 provider metadata 只由 `loushang.ai.auth`
  消费；AI request 不持有完整 credential DTO

### D. 事件流组装基础设施

- `EventStream`
- `RawAssembler`
- `RawPart`

适用场景：

- 自定义 Provider 实现
- 单元测试
- 构造假流事件

### E. Provider-specific 工具转换函数

- `to_anthropic_tools(...)`
- `to_openai_completions_tools(...)`
- `to_openai_responses_tools(...)`
- `to_openai_completions_assistant_message(...)`
- `to_openai_completions_tool_result_message(...)`
- `to_openai_responses_assistant_input(...)`
- `to_openai_responses_tool_result_input(...)`

适用场景：

- 自定义 Provider
- 调试消息映射
- 编写协议兼容测试


## Internal API

以下能力应视为内部实现细节，不建议作为公开门面承诺稳定性。

### A. 具体 Provider 实现类

- `AnthropicProvider`
- `OpenAICompletionsProvider`
- `OpenAIResponsesProvider`
- `FauxProvider`

说明：

- 测试和底层接入时可直接使用
- 但不建议项目业务代码直接依赖这些类

### B. Provider 内部共享实现

- `openai_responses_shared`
- `anthropic_base`
- `provider.errors`
- `provider.payloads.apply_*`
- `provider.simple_options`
- `provider.transform_messages`

说明：

- 这些模块更适合作为内部实现复用件
- 不宜承诺公共稳定性

## 建议的根包导出面

建议根包 `loushang.ai` 最终只主推如下内容。

### 一类：主入口

- 推理调用 API
- 模型查询 API
- Provider 注册 API

### 二类：统一协议

- 消息、内容块、事件流、Usage、StopReason
- 选项类型

### 三类：基础辅助

- `normalize_context`
- `transform_messages`
- `validate_tool_call`
- `validate_tool_arguments`
- `normalize_tool_call_id_for_model`

### 四类：受控高级能力

- 可继续从子包导入，但不必在根包主叙事中突出
- 如 `loushang.ai.model.*`
- 如 `loushang.ai.auth.*`
- 如 `loushang.ai.provider.*`
- 如 `loushang.ai.event_stream.*`
- OAuth lifecycle 使用 `loushang.ai.auth.*`


## 建议的命名空间组织

建议保留当前子包结构，并明确推荐下面的使用方式：

- 常规使用：
  - `from loushang.ai import complete, stream, get_model`
- 模型目录扩展：
  - `from loushang.ai.model import ...`
- 自定义 Provider：
  - `from loushang.ai.provider import ...`
- 请求级认证：
  - `from loushang.ai.auth import ...`
- OAuth lifecycle：
  - `from loushang.ai.auth import ...`
- 工具协议转换：
  - `from loushang.ai.tool import ...`

不建议：

- 要求上层直接 import `providers.*`
- 要求上层直接依赖 `openai_responses_shared` 这类内部模块


## 与参考项目的对应关系

### 对齐 `reference-repository/packages/ai`

应保留其核心优点：

- 根包统一导出
- `stream/complete` 作为首要入口
- 统一类型协议
- 工具调用与验证是一级能力
- 模型注册与 provider 注册可扩展

### 吸收 `kilocode/provider`

应吸收其对工程化有价值的能力：

- provider/model discovery
- request-level auth resolution
- transform 层与 compatibility 层分离
- model metadata 比运行时调用更早成为一等对象

但不应把以下内容引入 `loushang.ai` 的公共边界：

- 会话级 LLM 编排
- 路由服务
- 插件钩子系统
- 项目级配置聚合逻辑


## 后续落地建议

### 1. 明确 `__init__.py` 的稳定导出面

将根包导出按以下原则整理：

- Stable API 保留在根包
- Advanced API 优先从子包导入
- Internal API 不从根包导出

### 2. 认证 Registry 边界

OAuth provider 增删查列、内置 provider 注册、登录、刷新和 credential store
属于顶层 `loushang.ai.auth`。`loushang.ai.auth` 不导出这些 lifecycle API，只保留
request-level credential 与 auth resolution。

### 3. 明确 `provider` 与 `providers` 的边界说明

建议在文档和模块注释中明确：

- `provider` 是通用基础设施
- `providers` 是厂商实现

### 4. 给 Advanced API 加稳定性声明

建议在文档中显式声明：

- Stable API：兼容性承诺较强
- Advanced API：可用，但可能调整
- Internal API：不承诺兼容


## 结论

`loushang.ai` 应作为一个底层 AI SDK 风格的接入层存在。

它对外最重要的能力，不是“帮上层完成一整个 Agent 会话”，而是：

- 统一调用模型
- 统一表达消息和事件
- 统一管理模型目录与 Provider 路由
- 统一处理工具调用、请求级认证和兼容性差异

这也是后续整理根包导出面、写稳定性文档和约束上层依赖边界的基础。

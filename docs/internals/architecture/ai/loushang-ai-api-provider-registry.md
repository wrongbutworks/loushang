# Loushang AI ApiProvider Registry

## Scope

本文档讨论 `loushang.ai` 中 `ApiProvider registry` 的职责边界、public 形态与解析规则。

本文档只讨论：

- `ApiProvider` 作为注册单元的职责
- api registry 的 public 能力
- `register_api_provider` / `get_api_provider` / `list_api_providers` 的建议形态
- `stream()` / `complete()` 如何依赖 registry 解析 provider
- api registry 与 model registry 的边界

本文档不讨论：

- provider SDK adapter 的内部实现
- provider-specific option types
- 真实 provider 的接线细节
- `AgentLoop` 调度
- tool orchestration policy
- channel boundary protocol

---

## Design Question

在 `loushang.ai` 已冻结 message / types / streaming / cancellation 方向后，下一步需要回答：

1. `ApiProvider` 在 Python 中应建模为怎样的注册单元
2. public 层是否应该暴露 provider 实现对象
3. `stream()` 与 `complete()` 应如何根据模型绑定 endpoint 的 `api` 事实找到正确 provider
4. `api registry` 与 `model registry` 的边界应如何切分

如果这一层定义不清，后续顶层 API 很容易出现两类问题：

- 一类是把 provider 选择逻辑散落到顶层入口与调用点中
- 另一类是把 provider 实现细节过早暴露进 `loushang.ai` public contract

---

## Why This Matters

`ApiProvider registry` 是 `loushang.ai` 的接线中枢，但它不是 runtime 编排器。

它的价值在于：

1. 让统一入口通过稳定规则解析 provider，而不是硬编码 if/else
2. 让 `model registry` 只负责描述模型，不负责持有调用实现
3. 让 provider adapter 可以在内部演化，而不破坏顶层 public contract
4. 为 `complete()` / `stream()` 提供稳定的 api 语义落点

因此，这一层既不能太薄，也不能膨胀成完整 plugin system。

---

## Registry Layer Position

在 `loushang.ai` 内部，建议维持如下分层：

1. model registry
2. api provider registry
3. top-level invocation entrypoints
4. provider adapter lower-level implementation

其中：

- model registry 回答“这是什么模型，它属于哪个 api / provider”
- api provider registry 回答“这个 api 由谁执行，以及统一入口如何找到它”
- top-level entrypoints 回答“调用者如何发起 stream / complete”
- provider adapter implementation 回答“具体如何把统一协议翻译到上游 SDK / HTTP API”

这意味着：

- `ApiProvider registry` 位于 types 与 top-level API 之间
- 它是 public contract 的一部分
- 但它不等同于 provider implementation surface

---

## Reference Constraint

这一层的设计仍应遵守此前已冻结的参考取舍：

- public contract 对齐 `reference AI SDK`
- Python 实现经验吸收 `kimi-cli`
- lower-level provider adapter shape 可参考 LiteLLM

落到 registry 层的含义是：

- public 应优先表达统一入口与统一注册查询语义
- internal 可以采用 Python 常见 registry / mapping 组织方式
- 不应把 LiteLLM 式底层 provider 参数面直接抬成根入口 contract

---

## Core Decision

建议将 `ApiProvider` 建模为：

**“按 `Api` 维度注册的统一调用适配单元”。**

也就是说：

- 一个 `ApiProvider` 对应一种稳定的上游 API 语义
- 它负责把统一 `Context + Model + CallOptions` 调用翻译到该 API
- 它不是“某个 provider 品牌”的纯别名

例如：

- `openai-responses`
- `openai-completions`
- `anthropic-messages`

都是更合适的 registry 主键维度，而不是：

- `openai`
- `anthropic`
- `google`

原因是：

- 顶层调用的兼容面首先取决于 `api`，而不只是 `provider`
- 同一 provider 未来可能暴露多个 API family
- 当前稳定主轴是 endpoint `api` 事实，而不是 `Model` 上独立持有 `api` 字段

因此，registry 的主解析轴应为 `api`，而不是 `provider`。

---

## ApiProvider Responsibility

`ApiProvider` 的职责建议严格限制为：

1. 声明自己支持哪个 `api`
2. 提供统一 `invoke_raw(request)` 能力
3. 向顶层入口暴露足够稳定的 capability 信息

它不负责：

- model registry 本身
- 工具执行
- session orchestration
- channel event mapping
- host-level retry policy 编排
- observability 总线

这里最重要的边界是：

- registry 管“找到谁来执行”
- provider implementation 管“具体怎么执行”
- top-level API 管“对调用方暴露什么签名”

---

## Current Public Shape

`ApiProvider` 作为 registration unit，当前最小形态只包含：

- `api`
- `invoke_raw`

其中：

- `api` 是该 provider 适配的 `Api`
- `invoke_raw` 接收单一 `ProviderRequest`，并返回统一 raw parts

建议语义上要求：

- `invoke_raw` 为必选
- `ProviderRequest.mode` 表达 `complete` / `stream` 调用模式
- `complete()` / `stream()` 都通过同一 provider boundary 执行

这样设计的原因是：

- raw parts 是当前已冻结的 provider 输出边界
- complete-mode 和 stream-mode 的差异留在 request mode 和 adapter 映射中
- 根 API 不再保留 simple projection path

因此，不建议把 `complete` / `stream` 做成两个 provider 方法。
registry 层应围绕单一 raw-part 原语建模，而不是重复保存收敛包装。

---

## Registry Public API

建议 `loushang.ai` public registry 能力至少包括：

- `register_api_provider(provider)`
- `get_api_provider(api)`
- `list_api_providers()`

### register_api_provider

职责：

- 将一个 `ApiProvider` 注册到全局或默认 registry
- 以 `provider.api` 作为唯一键

建议行为：

- 当 `api` 尚未注册时，成功写入
- 当 `api` 已存在时，默认报错，而不是静默覆盖
- 如需替换，应由显式参数或内部专用入口完成，而不是作为默认 public 行为

这样做是为了避免：

- 库初始化顺序不同导致 provider 被悄悄覆盖
- 调用行为在不同环境下不稳定

### get_api_provider

职责：

- 返回指定 `api` 对应的已注册 provider

建议行为：

- 若存在，返回对应 `ApiProvider`
- 若不存在，抛出稳定的 registry-level error

不建议：

- 返回 `None` 让上层自己继续猜测
- 在这里隐式按 `provider` 或 `model` 做二次兜底

因为 registry 错误应尽可能早暴露为“缺少对应 api provider”，而不是延后成模糊调用错误。

### list_api_providers

职责：

- 提供当前 registry 中已注册 provider 的只读视图

建议返回：

- `list[ApiProvider]` 或等价只读序列

目的主要是：

- 调试
- introspection
- 测试断言
- 上层装配检查

不建议一开始就扩展为复杂管理接口，例如：

- enable / disable
- priority
- conditional matching
- lazy loading

这些都属于后续如有必要再开的扩展点。

---

## Resolution Rule

顶层统一入口的 provider 解析规则，建议固定为：

1. 从调用入参得到 `model`
2. 通过 `resolve_model_api(model)` 读取绑定 endpoint 的 `api`
3. 用解析出的 `api` 调用 `get_api_provider(api)`
4. 将请求转交给返回的 `ApiProvider`

也就是说：

- `Model` 负责携带 provider/endpoint 绑定信息
- registry 负责按 `api` 找 provider
- top-level API 不负责自行推断 provider 实现

这个规则应保持简单且单一，不建议在 v0.1 引入：

- 按 `provider` 回退
- 按模型名前缀猜测
- 多 provider 候选竞争
- 根据 transport / reasoning / tool support 动态路由

这些机制一旦过早加入，会把 registry 从“稳定接线层”推向“调度策略层”，超出当前 `loushang.ai` 边界。

---

## Relation to Model Registry

`model registry` 与 `api provider registry` 的边界建议如下：

### Model Registry

负责：

- 注册与查询 `Model`
- 维护模型元数据
- 告诉系统某模型绑定到哪个 endpoint，并由此解析出 `api`

不负责：

- 保存调用实现
- 决定如何执行 stream
- 管理 provider adapter 生命周期

### Api Provider Registry

负责：

- 注册与查询 `ApiProvider`
- 维护 `api -> provider` 的调用映射
- 为顶层入口提供稳定解析能力

不负责：

- 枚举某 provider 旗下全部模型
- 承载模型元数据主存
- 对模型能力做完整 model registry 判断

因此建议避免把两者混成：

- `Model` 内直接挂 executable provider object
- `model registry` 直接保存 `api -> callable`
- `api provider registry` 反向变成模型主存

正确关系应是：

`Model` 描述调用目标，`ApiProvider` 描述调用执行器，两个 registry 通过 endpoint `api` 事实连接；当前实现通常通过 `resolve_model_api(model)` 完成这一步。

---

## Relation to Top-Level Entrypoints

本设计对两个统一入口的直接约束是：

- `stream()` 依赖 `ApiProvider.invoke_raw(request)`，并设置 `ProviderRequest.mode = "stream"`
- `complete()` 依赖同一 `ApiProvider.invoke_raw(request)`，并设置 `ProviderRequest.mode = "complete"`

因此，registry 层需要保证的是：

- 顶层入口总能通过 `api` 找到明确执行器
- 缺失 provider 时，失败点明确且一致

而不需要在本层定义：

- final message assembly 细节
- simple/full 入口之间的参数映射细节
- provider-specific option merge 细节

这些属于后续顶层签名与 lower-level adapter 文档的范围。

---

## Failure Semantics

registry 层建议只定义有限且清晰的失败语义：

1. duplicate registration
2. missing provider for api
3. invalid provider object

建议把这三类失败视为：

- configuration / integration error

而不是：

- provider runtime error
- model response error
- cancellation error

这能保持错误边界清楚：

- registry error 说明系统没接好
- provider runtime error 说明调用过程中出错
- cancellation error 说明协议执行被中止

---

## Global vs Explicit Registry

v0.1 建议优先采用：

**默认全局 registry + 简单 public 注册查询入口**

原因是：

- 当前 handoff 目标是先稳定根入口 contract
- 全局 registry 最符合 Python 库初始化直觉
- 对文档、测试与上层装配都更简单

但应保留一个设计约束：

- public contract 不要把全局单例写死为唯一可行形态

这意味着可以允许内部保留未来演进空间，例如：

- 显式 registry instance
- testing sandbox registry
- scoped registry override

但这些不必在 v0.1 直接公开成主设计。

---

## Non-Goals

本阶段明确不进入以下设计：

- plugin discovery system
- dependency injection container
- multi-provider fallback chain
- weighted routing / policy routing
- capability negotiation matrix
- provider hot swapping protocol

这些都可能在未来有价值，但不属于当前“把统一入口接稳”的最小目标。

---

## Recommendation

建议冻结如下方向：

1. `ApiProvider registry` 作为 `loushang.ai` public contract 的一部分存在
2. `ApiProvider` 按 `api` 维度注册，而不是按 `provider` 品牌维度注册
3. `ApiProvider` 的最小 shape 保持为 `api + invoke_raw(request)`
4. registry public API 保持为 `register_api_provider` / `get_api_provider` / `list_api_providers`
5. 顶层统一入口按 `resolve_model_api(model) -> api provider` 的单一路径解析
6. `model registry` 与 `api provider registry` 严格分层，不互相吞并职责

---

## Open Questions

在进入顶层 API 签名设计前，仍有几个问题需要后续文档继续细化：

1. `ApiProvider.invoke_raw()` 的 `ProviderRequest` 字段是否仍有可删除项
2. `complete` / `stream` 两种 mode 的 adapter 测试矩阵是否完整
3. registry-level error 的正式类型族如何命名
4. `api registry` 是否需要暴露 `has_api_provider(api)` 这类辅助查询
5. provider/contrib-specific option 扩展如何避免进入根 public surface

---

## Current Conclusion

当前建议将 `ApiProvider registry` 视为 `loushang.ai` 的稳定接线层：

- 它连接模型绑定 endpoint 的 `api` 事实与真实调用执行器
- 它服务于统一入口，但不承担调度策略
- 它属于 public contract，但不暴露 provider 实现细节

在此基础上，下一步可以继续进入：

1. `stream()` / `complete()` 的正式签名设计
2. `ApiProvider` 方法级签名与错误类型设计

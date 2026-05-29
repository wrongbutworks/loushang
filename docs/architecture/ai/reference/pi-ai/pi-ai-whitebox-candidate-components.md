# PI-AI Whitebox Candidate Components

## Scope

本文档从白盒视角列出 `pi-ai` 的候选组件清单。  
目标不是给 `pi-ai` 下最终组件定版，而是识别它在内部已经存在或已经足够稳定的职责单元、边界单元与支撑结构。

本文档只讨论：

- `pi-ai` 内部候选组件
- 每个候选组件的大致对应位置
- 作用与职责
- 内聚 / 耦合的初步判断

本文档不讨论：

- `loushang-ai` 的最终组件划分
- 组件到文件的最终映射
- 最终一对一、多对一或多对多关系结论

---

## Reading Rule

这里的“候选组件”并不意味着：

- `pi-ai` 已经显式将其命名为组件
- 它必须在 `loushang-ai` 中被原样复制

本文档只做两件事：

1. 识别 `pi-ai` 内部已经存在的稳定职责单元
2. 为 `loushang-ai` 的白盒设计提供参考线索与反例

---

## Candidate Components

## 1. Top-Level AI API

**类别：**

- 逻辑功能组件

**对应位置：**

- [stream.ts](/home/dev/workspace/pi-mono/packages/ai/src/stream.ts)
- [index.ts](/home/dev/workspace/pi-mono/packages/ai/src/index.ts)

**作用：**

- 作为 `pi-ai` 的统一顶层调用入口

**主要职责：**

- 暴露 `stream`
- 暴露 `complete`
- 暴露 `streamSimple`
- 暴露 `completeSimple`
- 根据模型解析出的 `api` 分发到 `ApiProvider`

**初步判断：**

- 内聚性高
- 与类型系统、registry 有稳定依赖
- 不直接耦合具体 provider 细节

---

## 2. Model Registry

**类别：**

- 逻辑功能组件

**对应位置：**

- [models.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.ts)
- [models.generated.ts](/home/dev/workspace/pi-mono/packages/ai/src/models.generated.ts)

**作用：**

- 管理模型定义与模型查询

**主要职责：**

- `getModel`
- `getModels`
- `getProviders`
- 基于模型定义计算 cost
- 提供模型能力判断辅助，例如 `supportsXhigh`

**初步判断：**

- 内聚性高
- 与 provider 执行细节耦合较低
- 其内部其实已经包含“模型能力辅助层”职责簇

---

## 3. API Provider Registry

**类别：**

- 逻辑功能组件

**对应位置：**

- [api-registry.ts](/home/dev/workspace/pi-mono/packages/ai/src/api-registry.ts)

**作用：**

- 维护 `api -> provider` 映射

**主要职责：**

- `registerApiProvider`
- `getApiProvider`
- `getApiProviders`
- `unregisterApiProviders`
- `clearApiProviders`
- 对 provider 的 `stream` / `streamSimple` 做 API 一致性包装检查

**初步判断：**

- 内聚性高
- 耦合性低
- 是 `pi-ai` 内部最清晰的白盒逻辑组件之一

---

## 4. Built-In Provider Bootstrap

**类别：**

- 逻辑技术组件
- 扩展点组件

**对应位置：**

- [providers/register-builtins.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts)
- [stream.ts](/home/dev/workspace/pi-mono/packages/ai/src/stream.ts)

**作用：**

- 初始化内建 provider
- 把 provider 模块与 registry 连接起来

**主要职责：**

- 注册 built-in API providers
- 重置 provider registry
- 在模块加载时自动执行 built-in registration

**初步判断：**

- 内聚性较高
- 与 registry、provider modules 耦合较强
- 这是一个黑盒阶段容易忽略、白盒阶段必须识别的扩展点骨架

---

## 5. Lazy Provider Module Loader

**类别：**

- 逻辑技术组件
- 扩展点组件

**对应位置：**

- [providers/register-builtins.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts)

**作用：**

- 延迟加载真实 provider 模块

**主要职责：**

- 懒加载 provider module
- 包装 lazy stream / lazy streamSimple
- 将 lazy load failure 收敛为统一 error message
- 支持 provider module override，例如 Bedrock override

**初步判断：**

- 内聚性高
- 与 provider module shape 耦合较强
- 是一个典型的“没有显式 export 成独立产品概念，但内部已经成型”的白盒候选组件

---

## 6. Provider Adapter Layer

**类别：**

- 边界逻辑组件

**对应位置：**

- `src/providers/*.ts`

重点包括：

- [providers/anthropic.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/anthropic.ts)
- [providers/openai-completions.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-completions.ts)
- [providers/openai-responses.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-responses.ts)
- [providers/mistral.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/mistral.ts)
- [providers/amazon-bedrock.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/amazon-bedrock.ts)

**作用：**

- 隔离 `pi-ai` 与外部 provider API / SDK / transport 的变化

**主要职责：**

- 接收统一 `model + context + options`
- 生成 provider request
- 接入 SDK / HTTP client
- 消费 provider stream
- 输出统一 event / result 语义
- provider-specific options 映射

**初步判断：**

- 单个 adapter 内部通常高内聚
- 整个 layer 天然高耦合于外部协议
- 这种高耦合是边界组件的合理特征，不是坏味道本身

---

## 7. Simple Options Mapping Layer

**类别：**

- 逻辑支撑组件
- 逻辑技术组件

**对应位置：**

- [providers/simple-options.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/simple-options.ts)
- 各 provider 中的 `streamSimple*`

**作用：**

- 将 provider-agnostic simple options 映射为 provider-specific options

**主要职责：**

- reasoning level 映射
- thinking budgets 映射
- simple/full 入口之间的桥接

**初步判断：**

- 这是 `pi-ai` simple API 能成立的重要支撑职责簇
- 当前分布在 provider 层与 shared helper 中
- 值得在 `loushang-ai` 白盒阶段单独识别

---

## 8. Message Transformation Layer

**类别：**

- 边界逻辑组件
- 逻辑支撑组件

**对应位置：**

- [providers/transform-messages.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/transform-messages.ts)
- [providers/openai-responses-shared.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/openai-responses-shared.ts)
- 多个 provider adapter 内部

**作用：**

- 在跨 provider / 跨模型 / 跨协议场景下转换消息

**主要职责：**

- tool call ID normalization
- 跨 provider handoff 消息变换
- 对 thinking / tool call / assistant message 做适配

**初步判断：**

- 白盒阶段应视为明确职责簇
- 与 adapter layer 关系紧密
- 若不识别，后续极易散落到各 provider 实现中

---

## 9. Event Stream Runtime

**类别：**

- 逻辑支撑组件
- 逻辑技术组件

**对应位置：**

- [utils/event-stream.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/event-stream.ts)

**作用：**

- 提供统一事件流对象与结果收敛机制

**主要职责：**

- 队列维护
- 等待消费者协调
- 完成事件识别
- 最终结果 promise 收敛

**初步判断：**

- 内聚性高
- 耦合性低
- 是一个很清楚的内部技术骨架组件

---

## 10. Assistant Message Event Stream

**类别：**

- 逻辑支撑组件

**对应位置：**

- [utils/event-stream.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/event-stream.ts)
- [types.ts](/home/dev/workspace/pi-mono/packages/ai/src/types.ts)

**作用：**

- 为 AI streaming 提供稳定 public event 容器

**主要职责：**

- 异步迭代
- `result()` 收敛最终 `AssistantMessage`
- 以 `done/error` 事件结束

**初步判断：**

- 内聚性高
- 是 public contract 与内部 runtime 之间的关键桥梁

---

## 11. Error Mapping Layer

**类别：**

- 逻辑支撑组件
- 边界逻辑组件

**对应位置：**

- 分布于各 provider adapter
- 例如 shared provider helper、lazy load error builder、provider error conversion

可见线索包括：

- [providers/register-builtins.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/register-builtins.ts)
- 各 provider 文件中的 error conversion

**作用：**

- 将 SDK / HTTP / provider-specific error 收敛为统一 AI error 语义

**主要职责：**

- lazy load failure -> unified assistant error
- provider failure -> unified assistant error
- runtime failure -> protocol-level error result

**初步判断：**

- 目前更像职责簇，而不是单一明确模块
- 但白盒阶段必须识别，否则后面耦合会快速扩散

---

## 12. Validation Layer

**类别：**

- 逻辑技术组件
- 横切支撑组件

**对应位置：**

- [utils/validation.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/validation.ts)
- README 中对 tool argument validation 的显式强调

**作用：**

- 为工具调用与输入输出边界提供校验能力

**主要职责：**

- tool argument validation
- schema-based validation support

**初步判断：**

- 虽然 export surface 看起来像工具函数
- 但白盒阶段更适合视为稳定技术支撑组件或至少稳定职责簇

---

## 13. Environment API Key Resolution

**类别：**

- 边界逻辑组件
- 逻辑支撑组件

**对应位置：**

- [env-api-keys.ts](/home/dev/workspace/pi-mono/packages/ai/src/env-api-keys.ts)

**作用：**

- 统一从环境变量解析 provider API key

**主要职责：**

- provider -> env var mapping
- 对不同 provider 的 env 约定进行统一读取
- 特定 provider 的特殊逻辑，例如 Vertex / Bedrock 等

**初步判断：**

- 这是 auth/config 边界上的支撑组件
- 不应被简单视为零散 helper

---

## 14. OAuth/Auth Integration Layer

**类别：**

- 边界逻辑组件
- 扩展点组件

**对应位置：**

- [oauth.ts](/home/dev/workspace/pi-mono/packages/ai/src/oauth.ts)
- [cli.ts](/home/dev/workspace/pi-mono/packages/ai/src/cli.ts)
- `src/utils/oauth/*`

**作用：**

- 为依赖 OAuth 的 provider 提供认证能力与 provider-specific auth integration

**主要职责：**

- OAuth provider registry
- login flow
- refresh token
- OAuth provider-specific credential normalization
- 认证信息与模型/provider 配置的连接

**初步判断：**

- 这在黑盒阶段容易被暂时排除
- 但在白盒阶段必须明确识别
- 它很可能是一个独立的边界组件族，而不只是零散工具函数

---

## 15. Context Overflow / Boundary Handling

**类别：**

- 横切技术组件
- 逻辑支撑组件

**对应位置：**

- [utils/overflow.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/overflow.ts)

**作用：**

- 处理上下文溢出与边界问题

**主要职责：**

- overflow detection / formatting / boundary support

**初步判断：**

- 虽然当前在 `pi-ai` 中可能更偏 utility 形态
- 但它表达的是稳定问题域
- 值得进入候选组件或候选职责簇清单

---

## 16. JSON / Unicode / Type Helpers

**类别：**

- 候选职责簇
- 技术支撑

**对应位置：**

- [utils/json-parse.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/json-parse.ts)
- [utils/sanitize-unicode.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/sanitize-unicode.ts)
- [utils/typebox-helpers.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/typebox-helpers.ts)
- [utils/hash.ts](/home/dev/workspace/pi-mono/packages/ai/src/utils/hash.ts)

**作用：**

- 为协议边界、schema、内容安全与序列化提供基础支撑

**主要职责：**

- JSON parsing
- Unicode sanitization
- TypeBox helper
- hashing support

**初步判断：**

- 目前更适合作为职责簇，而不是立即升格成一级组件
- 但白盒阶段必须先识别

---

## 17. Faux/Test Provider Support

**类别：**

- 逻辑技术组件
- 扩展点组件

**对应位置：**

- [providers/faux.ts](/home/dev/workspace/pi-mono/packages/ai/src/providers/faux.ts)

**作用：**

- 为测试、实验与可控验证提供 provider support

**主要职责：**

- 注册 faux provider
- 生成 faux model
- 模拟 stream / complete path
- 支持注销与可控测试场景

**初步判断：**

- 虽然不是生产 provider
- 但它已经是稳定测试/实验支撑结构
- 白盒阶段值得单列

---

## Summary

从当前白盒视角看，`pi-ai` 至少已经暴露出以下几类候选组件：

### 逻辑功能组件

- Top-Level AI API
- Model Registry
- API Provider Registry

### 逻辑支撑组件

- Assistant Message Event Stream
- Event Stream Runtime
- Simple Options Mapping Layer
- Validation Layer
- Context Overflow / Boundary Handling

### 逻辑技术 / 扩展点组件

- Built-In Provider Bootstrap
- Lazy Provider Module Loader
- Faux/Test Provider Support

### 边界逻辑组件

- Provider Adapter Layer
- Message Transformation Layer
- Environment API Key Resolution
- OAuth/Auth Integration Layer
- Error Mapping Layer

### 候选职责簇

- JSON / Unicode / Type Helpers

---

## Current Takeaway

`pi-ai` 的 export surface 只覆盖了其中一部分。  
如果只看 public export，很容易漏掉：

- bootstrap / loader
- auth integration
- validation / normalization
- overflow / boundary handling
- faux/test support

因此，在后续 `loushang-ai` 白盒设计中，不应只沿着 export surface 抽象组件，而应同时吸收这些内部稳定职责单元。

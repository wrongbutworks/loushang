## `models.json` 领域模型

说明：

- 本文基于当前 `models.json` 的原生树结构描述领域来源。
- 代码中的运行时领域对象已经统一命名为 `Provider`、`Endpoint`、`Model`、`Auth`、`Capabilities`、`Compat`、`Defaults`、`Pricing`。
- 文中提到的 `EndpointModel` 可以直接理解为当前代码中的 `Model` 领域对象来源。

本文只基于当前 `src/loushang/ai/model/models.json` 描述 `loushang.ai` 的底层接入领域模型。

约束：

- 不参照 `reference repository` 或 `kilocode` 的数据模型
- 不读取离线备份目录 `backup/ai/`
- 只描述当前 `models.json` 原生存在的对象及其直接关系
- API 层可参考外部项目，但领域模型层不参考


## 领域边界

`models.json` 是 `loushang.ai` 的底层接入事实源。

它回答的是：

- 系统有哪些 Provider
- 每个 Provider 暴露哪些 Endpoint
- 每个 Endpoint 通过什么 API 协议提供能力
- 每个 Endpoint 下有哪些可调用模型
- Provider 级和 Endpoint 级的认证信息是什么

它当前不直接回答的是：

- 运行时 registry 应该长什么样
- 统一 ModelView 应该长什么样
- 调用时如何解析为 request
- 上层 API 如何组织

这些都属于后续实现与 API 设计层，而不是 `models.json` 的原生领域模型。


## 原生领域对象

当前 `models.json` 中可以直接确认的原生核心对象可以归纳为 4 类来源：

- `Provider`
- `Endpoint`
- `Model`
- `Auth`


## 1. Provider

顶层对象，位于 `providers.{providerKey}`。

示例字段：

- `displayName`
- `website`
- `auth`
- `endpoints`

语义：

- Provider 表示一个供应方或接入来源
- Provider 是 Endpoint 的归属边界
- Provider 可定义默认认证方式

当前可以明确确认的关系：

- 一个 Provider 包含多个 Endpoint
- 一个 Provider 可以有一个 provider-level `auth`


## 2. Endpoint

Provider 下的接入端点对象，位于 `providers.{providerKey}.endpoints.{endpointKey}`。

示例字段：

- `displayName`
- `baseUrl`
- `baseUrlEnv`
- `api`
- `region`
- `lane`
- `docs`
- `authOverride`
- `models`

语义：

- Endpoint 是实际可接入的协议/地址单元
- Endpoint 决定该通道使用哪种 API 协议
- Endpoint 可以对 Provider 的认证进行覆盖
- Endpoint 是模型清单的直接挂载点

当前可以明确确认的关系：

- 一个 Endpoint 属于一个 Provider
- 一个 Endpoint 包含多个 EndpointModel
- 一个 Endpoint 可选定义一个 endpoint-level `authOverride`

注意：

- `region`、`lane` 目前都只是 Endpoint 的属性
- `providerTransport` 已收进 `compat.providerTransport`
- 当前 `models.json` 中没有独立的 `Region` 对象
- 当前 `models.json` 中也没有独立的 `Compat`、`Defaults`、`Binding` 对象


## 3. Model

Endpoint 下的模型对象，位于 `providers.{providerKey}.endpoints.{endpointKey}.models.{modelId}`。

示例字段：

- `displayName`
- `family`
- `alias`
- `knowledge`
- `releaseDate`
- `lastUpdated`
- `capabilities`
- `pricing`
- `compat`
- `defaults`

语义：

- Model 是当前 `models.json` 中“可被接入调用”的最小模型单元
- 它不是 provider 无关的全局模型定义
- 它天然隶属于某个 Endpoint
- 同一个模型标识可以出现在多个 Endpoint 下，但在 `models.json` 当前结构中，这些仍是多个 endpoint-scoped 模型定义

注意：

- 当前 JSON 中不存在独立的 `Capability` 对象
- 当前 JSON 中的模型能力字段统一收进 `capabilities`
- `capabilities` 当前同时承载：
  - `input` / `output`
  - `reasoning`
  - `contextWindow` / `maxTokens`
  - `stream` / `toolUse` / `structuredOutput` / `attachment` / `temperature`
- 当前 JSON 中的成本字段通过 `pricing` 内嵌在 model 原始定义上


## 4. Auth

认证对象是嵌入式对象，不是顶层实体。

当前明确存在两种位置：

- Provider 级 `auth`
- Endpoint 级 `authOverride`

示例字段：

- `kind`
- `apiKeyEnv`
- `header`
- `prefix`
- `extraHeaders`

语义：

- Auth 用来声明如何从环境或调用上下文中取认证材料
- Provider 级 `auth` 表示默认认证方式
- Endpoint 级 `authOverride` 表示对 Provider 默认认证的覆盖

注意：

- 当前 JSON 中不存在独立的 OAuth 领域对象
- OAuth 相关能力属于运行时认证系统，而不是 `models.json` 的原生领域模型


## 值对象与内嵌结构

除上述 4 个原生对象外，当前 `models.json` 还包含若干内嵌值结构。

### Pricing

位于 `Model.pricing`。

字段示例：

- `currency`
- `input`
- `output`
- `cacheRead`
- `cacheWrite`

语义：

- 描述该 Model 在该接入通道下的价格信息
- 它属于 Model 的内嵌值对象，而不是独立领域实体

### Input / Output Modalities

位于 `Model.input` 与 `Model.output`。

语义：

- 描述输入输出模态
- 当前存储形式是字符串，而不是独立对象


## 当前明确不存在的对象

为了避免后续讨论混淆，这里明确列出当前 `models.json` 中**没有原生定义**的对象：

- 全局规格表对象
- 绑定表对象
- `Capability`
- `CapabilityOverlay`
- `RegionConfig`
- `GatewayConfig`
- `CompatFlags`
- `Defaults`
- `SelectionPolicy`
- `CodingPlan`

这些概念如果后续还需要存在，只能作为：

- API 层对象
- 运行时解析对象
- 内部实现对象

而不能再被表述成“`models.json` 原生领域对象”。


## 对象关系

当前 `models.json` 的原生关系非常简单：

- `Provider` 1..* `Endpoint`
- `Endpoint` 1..* `Model`
- `Provider` 0..1 `auth`
- `Endpoint` 0..1 `authOverride`
- `Model` 0..1 `pricing`

从这套关系可以得出的结论是：

- 当前底层接入目录是一个分层树结构
- 不是全局规格表 + 绑定表的关系模型
- 模型定义当前是 endpoint-scoped 的


## 当前最小领域视图

如果只从 `models.json` 出发，可以把底层领域模型压缩成一句话：

> `Provider` 通过一个或多个 `Endpoint` 暴露模型接入能力；每个 `Endpoint` 使用一种 API 协议、可选覆盖认证方式，并直接持有一组可调用的 `EndpointModel` 定义。


## 对后续重构的约束

后续重构允许围绕 API 设计引入新的运行时对象，但必须遵守下面两点：

### 1. 新对象不能冒充 `models.json` 原生对象

例如如果后续需要：

- `ResolvedModel`
- `ResolvedEndpoint`
- `ResolvedRequest`
- `CapabilityView`
- `Binding`

应明确标注它们是：

- 运行时派生对象
- 或 API 设计对象

而不是 `models.json` 的原生领域模型。

### 2. 运行时对象应可由当前 4 类原生对象推导出来

也就是任何新增抽象，都应能回溯到：

- `Provider`
- `Endpoint`
- `EndpointModel`
- `Auth`

否则说明它不是底层接入事实源的一部分，而是上层策略对象。

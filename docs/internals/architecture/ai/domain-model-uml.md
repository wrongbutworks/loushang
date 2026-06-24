## `models.json` 领域模型 UML

说明：

- 本图表达的是 `models.json` 的领域来源。
- 运行时代码中的对象命名已经收敛为 `Model`，不再单独使用 `EndpointModel` 作为主命名。

本文 UML 只表达当前 `src/loushang/ai/model/models.json` 中原生存在的对象与关系。

约束：

- 不参考 `reference repository`
- 不参考 `kilocode`
- 不读取离线备份目录 `backup/ai/`
- 不把运行时抽象误写成 JSON 原生对象

```plantuml
@startuml
skinparam classAttributeIconSize 0
skinparam shadowing false
skinparam linetype ortho

class Provider as "Provider\n提供方" {
  +providerKey : String
  +displayName : String
  +website : String
}

class Endpoint as "Endpoint\n接入端点" {
  +endpointKey : String
  +displayName : String
  +baseUrl : String
  +baseUrlEnv : String
  +api : String
  +region : String
  +lane : String
  +docs : String
}

class Model as "Model\n端点下的可调用模型" {
  +modelId : String
  +displayName : String
  +family : String
  +alias : String
  +supportsReasoning : Boolean
  +supportsToolCall : Boolean
  +supportsStructuredOutput : Boolean
  +supportsAttachment : Boolean
  +supportsTemperature : Boolean
  +knowledge : String
  +releaseDate : String
  +lastUpdated : String
  +contextWindow : Long
  +maxOutputTokens : Long
  +supportsStream : Boolean
  +input : String
  +output : String
}

class Compat as "Compat\n兼容参数" {
  +supportsUsageInStreaming : Boolean
  +supportsStreamReasoningDelta : Boolean
  +supportsReasoningEffort : Boolean
  +supportsJsonSchemaStructuredOutput : Boolean
  +supportsDeveloperRole : Boolean
  +requiresThinkingAsText : Boolean
  +thinkingFormat : String
  +maxTokensField : String
}

class Auth as "Auth\n认证声明" {
  +kind : String
  +apiKeyEnv : String
  +header : String
  +prefix : String
}

class Pricing as "Pricing\n价格信息" {
  +currency : String
  +input : Decimal
  +output : Decimal
  +cacheRead : Decimal
  +cacheWrite : Decimal
}

Provider "1" *-- "1..*" Endpoint : 包含
Endpoint "1" *-- "1..*" Model : 暴露
Provider "1" *-- "0..1" Auth : 默认认证
Endpoint "1" *-- "0..1" Auth : 覆盖认证
Model "1" *-- "0..1" Pricing : 定价
Endpoint "1" *-- "0..1" Compat : 默认兼容参数
Model "1" *-- "0..1" Compat : 覆盖兼容参数

note right of Provider
当前 JSON 顶层原生对象。
是接入来源边界，不是运行时 registry。
end note

note right of Endpoint
当前 JSON 中的协议与地址单元。
直接持有 models。
不存在独立 Region/Compat/Defaults 对象。
end note

note right of Model
当前 JSON 中最小可接入模型单元。
是 endpoint-scoped 模型定义，
不是 provider 无关的全局规格表对象。
end note

note right of Auth
Auth 是嵌入式对象：
- provider.auth
- endpoint.authOverride
不是独立顶层实体。
end note

note right of Pricing
Pricing 是 Model 的内嵌值对象。
不是独立领域实体。
end note

note right of Compat
Compat 是 Endpoint / Model 的内嵌值对象。
兼容语义统一放在 compat 中，
不再把兼容字段摊在 Model 顶层。
end note

note bottom
当前 models.json 中明确不存在以下原生对象：
全局规格表 / 绑定表 / Capability / RegionConfig / Defaults

如果后续实现需要这些对象，
应把它们定义为运行时派生对象，而不是 JSON 原生领域对象。
end note

@enduml
```

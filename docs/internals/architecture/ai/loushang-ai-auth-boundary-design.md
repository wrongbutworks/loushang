# loushang.ai 认证边界与调用凭证设计

## 1. 背景

`loushang.ai` 是 Loushang 系统中的模型调用包，其核心职责是接收上层应用传入的模型调用请求，并完成模型协议适配、请求拼接、Provider 调用、响应归一化、流式事件处理和错误归一化。

认证能力是模型调用链路中的必要组成部分，但认证本身容易扩展为账号系统、OAuth 框架、凭证存储系统或 Provider control-plane。为了保持 `loushang.ai` 的职责简单、边界清晰，需要明确认证能力在 `loushang.ai` 中的职责范围。

本文定义 `loushang.ai` 中认证能力的设计边界、核心概念、认证解析规则和非目标范围。

---

## 2. 设计目标

`loushang.ai` 的认证设计应满足以下目标：

1. **职责单一**
   只负责将调用凭证解析为 Provider 请求所需的认证信息。

2. **边界清晰**
   不承担 OAuth 登录、OAuth 刷新、凭证存储、账号选择、额度查询等上层职责。

3. **调用友好**
   支持上层显式传入认证凭证；对于 API Key 认证模型，也允许根据模型配置从环境变量读取凭证。

4. **契约明确**
   `models.json` 描述模型所需的认证契约，`CallOptions.auth` 描述本次调用实际提供的运行时凭证。

5. **失败可诊断**
   缺少认证、认证类型不匹配、模型认证配置错误等情况应明确失败，而不是静默降级或隐式修复。

6. **安全可控**
   所有认证信息在日志、错误、trace 中必须脱敏，不得泄露 API key、OAuth token 或其他敏感 header。

---

## 3. 设计非目标

`loushang.ai` 的认证能力不覆盖以下内容：

| 非目标                         | 说明                                                              |
| ------------------------------ | ----------------------------------------------------------------- |
| OAuth 登录流程                 | 不负责 authorization URL、浏览器跳转、callback server、授权码交换 |
| OAuth token refresh            | 不负责 refresh token、access token 自动刷新或重试                 |
| 凭证持久化                     | 不负责本地 credential store、数据库存储、加密存储                 |
| 多账号管理                     | 不负责用户账号、Provider 账号、组织账号选择                       |
| Provider account control-plane | 不负责 quota、billing、subscription、account profile              |
| 产品级认证策略                 | 不负责根据额度、用户状态、套餐决定模型路由                        |
| 工具认证                       | 不负责上层工具调用所需的业务系统认证                              |
| 会话认证状态                   | 不负责 session 内的长期认证状态管理                               |

一句话概括：

> `loushang.ai` 只处理“本次模型调用如何携带认证信息”，不处理“用户如何获得、保存、刷新或管理认证信息”。

---

## 4. 核心概念

认证设计中区分三个概念：

```text
AuthConfig
  ↓
AuthCredential
  ↓
AuthView
```

三者分别对应不同层次的职责。

---

## 4.1 AuthConfig

`AuthConfig` 表示模型或 endpoint 的认证契约，来源于 `models.json`。

它描述的是：

- 该模型是否需要认证；
- 该模型需要哪种认证方式；
- 认证信息应放入哪个请求 header；
- API Key 类型认证可以从哪些环境变量读取；
- 是否需要附加固定 header。

`AuthConfig` 不包含真实凭证。

示例语义：

```text
这个模型使用 API Key 认证。
API Key 默认从 OPENAI_API_KEY 环境变量读取。
请求时放入 Authorization header。
前缀为 Bearer。
```

或：

```text
这个模型使用 OAuth Bearer Token。
调用方必须显式传入 access token。
请求时放入 Authorization header。
前缀为 Bearer。
```

---

## 4.2 AuthCredential

`AuthCredential` 表示本次调用实际使用的运行时凭证，来源于上层应用传入的 `CallOptions.auth`，或者由 `loushang.ai` 在 API Key 场景下根据环境变量自动构造。

它是调用级别的认证输入。

推荐的认证凭证类型包括：

| 类型              | 说明                                         |
| ----------------- | -------------------------------------------- |
| `ApiKeyAuth`      | 上层显式传入 API key                         |
| `OAuthBearerAuth` | 上层显式传入 OAuth access token              |
| `NoAuth`          | 显式声明本次调用不使用认证                   |
| `EnvApiKeyAuth`   | 内部类型，根据模型配置从环境变量读取 API key |

其中，`EnvApiKeyAuth` 是内部机制，不一定需要作为主要公开 API 暴露。

---

## 4.3 AuthView

`AuthView` 是认证解析后的结果，用于 Provider 请求阶段。

它表示：

```text
最终要发送给 Provider 的认证 headers 和相关 metadata。
```

典型结果包括：

```text
Authorization: Bearer <api-key>
```

或：

```text
Authorization: Bearer <oauth-access-token>
```

`AuthView` 是解析结果，不是上层应用主要构造的对象。

---

## 5. 分层关系

认证链路可以表示为：

```text
models.json 中的 AuthConfig
        +
CallOptions.auth 中的 AuthCredential
        ↓
认证解析
        ↓
AuthView
        ↓
Provider HTTP request
```

其中：

| 层         | 数据             | 职责                           |
| ---------- | ---------------- | ------------------------------ |
| 模型目录层 | `AuthConfig`     | 声明模型需要的认证方式         |
| 调用输入层 | `AuthCredential` | 提供本次调用实际凭证           |
| 请求拼接层 | `AuthView`       | 生成 Provider 请求所需 headers |

---

## 6. 认证类型

## 6.1 API Key 认证

API Key 认证用于静态密钥类 Provider 调用。

该类型支持两种凭证来源：

1. 上层通过 `CallOptions.auth` 显式传入 `ApiKeyAuth`；
2. 如果上层未传入认证，则 `loushang.ai` 根据 `models.json` 中配置的环境变量读取 API key。

API Key 可以从环境变量读取，因为它通常是部署环境或开发环境中的静态服务凭证。

例如：

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
MOONSHOT_API_KEY
DASHSCOPE_API_KEY
```

---

## 6.2 OAuth Bearer 认证

OAuth Bearer 认证用于上层已经完成 OAuth 授权后，将 access token 显式传给 `loushang.ai` 的场景。

`loushang.ai` 对 OAuth 的职责仅限于：

```text
把上层传入的 access token 拼接为 Provider 请求 header。
```

例如：

```text
Authorization: Bearer <access-token>
```

`loushang.ai` 不负责 OAuth 登录、刷新、存储或账号管理。

OAuth 类型模型必须显式传入 `OAuthBearerAuth`。

---

## 6.3 无认证

部分本地模型、测试 Provider、mock Provider 或内部服务可能不需要认证。

这类模型应在模型配置中声明为无认证。

对于无认证模型，如果上层额外传入 API Key 或 OAuth Token，应视为认证类型不匹配，而不是静默忽略。

这样可以避免：

- 模型配置错误；
- 调用方误选模型；
- 上层凭证路由错误；
- 敏感凭证被意外传递到不需要认证的 Provider。

---

## 7. 认证解析规则

## 7.1 总体优先级

认证解析遵循以下原则：

```text
显式调用凭证优先；
API Key 模型允许环境变量 fallback；
OAuth 模型必须显式传入凭证；
认证类型必须与模型认证契约匹配；
不匹配或缺失时 fail fast。
```

---

## 7.2 API Key 模型

当模型配置为 API Key 认证时：

```text
model.auth.kind == "api_key"
```

解析规则如下：

| `CallOptions.auth` | 行为                               |
| ------------------ | ---------------------------------- |
| `ApiKeyAuth`       | 使用显式传入的 API key             |
| `None`             | 根据模型配置从环境变量读取 API key |
| `OAuthBearerAuth`  | 报认证类型不匹配                   |
| `NoAuth`           | 报认证类型不匹配                   |

如果环境变量中没有可用 API key，则报缺少认证错误。

API Key 模型的完整规则：

```text
1. 如果上层显式传入 ApiKeyAuth，则使用该凭证。
2. 如果上层没有传入认证，则根据 AuthConfig 中的 env 配置读取 API key。
3. 如果上层传入 OAuthBearerAuth 或 NoAuth，则视为认证类型不匹配。
4. 如果既没有显式凭证，也无法从环境变量读取 API key，则失败。
```

---

## 7.3 OAuth 模型

当模型配置为 OAuth 认证时：

```text
model.auth.kind == "oauth"
```

解析规则如下：

| `CallOptions.auth` | 行为                        |
| ------------------ | --------------------------- |
| `OAuthBearerAuth`  | 使用显式传入的 access token |
| `None`             | 报缺少认证错误              |
| `ApiKeyAuth`       | 报认证类型不匹配            |
| `NoAuth`           | 报认证类型不匹配            |

OAuth 模型的完整规则：

```text
1. OAuth 模型必须显式传入 OAuthBearerAuth。
2. 不从环境变量读取 OAuth token。
3. 不从 credential store 读取 OAuth token。
4. 不执行 OAuth login。
5. 不执行 OAuth refresh。
6. 如果缺少 OAuthBearerAuth，则失败。
7. 如果传入其他认证类型，则失败。
```

OAuth access token 通常具有用户身份、授权范围、过期时间和撤销状态，因此它不应由 `loushang.ai` 隐式读取或管理。

---

## 7.4 无认证模型

当模型配置为无认证时：

```text
model.auth.kind == "none"
```

解析规则如下：

| `CallOptions.auth` | 行为              |
| ------------------ | ----------------- |
| `None`             | 不生成认证 header |
| `NoAuth`           | 不生成认证 header |
| `ApiKeyAuth`       | 报认证类型不匹配  |
| `OAuthBearerAuth`  | 报认证类型不匹配  |

无认证模型不应静默接受额外凭证。

---

## 8. 认证决策矩阵

| 模型认证契约 | 调用凭证          | 结果                                 |
| ------------ | ----------------- | ------------------------------------ |
| `api_key`    | `ApiKeyAuth`      | 使用显式 API key                     |
| `api_key`    | `None`            | 从模型配置声明的环境变量读取 API key |
| `api_key`    | `OAuthBearerAuth` | 认证类型不匹配                       |
| `api_key`    | `NoAuth`          | 认证类型不匹配                       |
| `oauth`      | `OAuthBearerAuth` | 使用显式 OAuth access token          |
| `oauth`      | `None`            | 缺少认证                             |
| `oauth`      | `ApiKeyAuth`      | 认证类型不匹配                       |
| `oauth`      | `NoAuth`          | 认证类型不匹配                       |
| `none`       | `None`            | 无认证                               |
| `none`       | `NoAuth`          | 无认证                               |
| `none`       | `ApiKeyAuth`      | 认证类型不匹配                       |
| `none`       | `OAuthBearerAuth` | 认证类型不匹配                       |

---

## 9. API Key 与 OAuth 的差异

API Key 和 OAuth Token 在认证模型中具有不同性质。

| 项                                    | API Key                | OAuth Access Token   |
| ------------------------------------- | ---------------------- | -------------------- |
| 凭证形态                              | 静态密钥               | 用户授权后的短期令牌 |
| 常见来源                              | 环境变量、密钥管理系统 | 上层 OAuth 授权流程  |
| 是否可由 `loushang.ai` 从环境变量读取 | 可以                   | 不可以               |
| 是否需要 refresh                      | 通常不需要             | 通常需要             |
| 是否绑定用户身份                      | 不一定                 | 通常绑定             |
| 是否涉及 scope                        | 一般较弱               | 通常明确             |
| 是否涉及账号生命周期                  | 较弱                   | 较强                 |
| 是否由 `loushang.ai` 管理             | 否，只读取             | 否，只接收           |

因此：

```text
API Key 可以作为部署环境中的静态输入源。
OAuth Access Token 必须由上层应用显式提供。
```

---

## 10. 错误语义

认证错误应具有明确语义，便于上层应用处理。

推荐区分以下错误类型：

| 错误类型                 | 触发场景                               |
| ------------------------ | -------------------------------------- |
| `MissingAuthError`       | 模型需要认证，但没有可用凭证           |
| `AuthKindMismatchError`  | 调用凭证类型与模型认证契约不匹配       |
| `InvalidAuthConfigError` | 模型认证配置本身不合法                 |
| `AuthHeaderBuildError`   | 无法根据配置和凭证生成合法请求 header  |
| `ProviderAuthError`      | Provider 返回认证失败，例如 401 或 403 |

错误处理原则：

```text
缺少认证要失败。
认证类型不匹配要失败。
模型认证配置错误要失败。
Provider 返回认证失败要原样归一化为认证错误。
不得静默降级。
不得隐式切换认证方式。
不得自动登录或刷新。
```

---

## 11. 安全原则

认证设计必须遵守以下安全原则：

1. **Secret 不可出现在日志中**
   API key、access token、Authorization header、x-api-key 等必须脱敏。

2. **Secret 不可出现在异常消息中**
   错误对象可以包含认证类型、模型 ID、Provider ID、缺失的环境变量名，但不能包含真实凭证值。

3. **Secret 不可出现在 trace 明文中**
   trace 中如需记录认证信息，只允许记录认证类型和脱敏后的 header 名称。

4. **显式凭证优先**
   如果调用方显式传入凭证，应优先使用该凭证，而不是环境变量。

5. **不隐式使用 OAuth 凭证**
   OAuth token 不从环境变量、credential store 或缓存读取。

6. **多余凭证不静默忽略**
   对于无认证模型或认证类型不匹配的模型，传入多余凭证应报错。

---

## 12. `models.json` 中认证配置的定位

`models.json` 中的认证配置是模型调用契约的一部分。

它应描述：

```text
模型需要哪种认证；
认证 header 如何生成；
API Key 认证时从哪些环境变量读取；
是否需要固定附加 header。
```

它不应描述：

```text
OAuth 登录地址；
OAuth token 地址；
client_id；
client_secret；
refresh_token；
credential store；
账号选择策略；
quota 查询接口；
billing 查询接口。
```

`models.json` 中的认证配置应保持稳定、简单、声明式。

---

## 13. `CallOptions.auth` 的定位

`CallOptions.auth` 是本次调用的运行时认证输入。

它用于表达：

```text
上层应用希望本次模型调用使用哪种凭证。
```

它不用于表达：

```text
如何登录；
如何刷新；
如何保存；
如何选择账号；
如何查询额度。
```

推荐的调用凭证类型：

| 类型              | 语义                                |
| ----------------- | ----------------------------------- |
| `ApiKeyAuth`      | 本次调用使用显式 API key            |
| `OAuthBearerAuth` | 本次调用使用显式 OAuth access token |
| `NoAuth`          | 本次调用明确不使用认证              |

内部可根据 API Key 模型配置构造：

| 类型            | 语义                                   |
| --------------- | -------------------------------------- |
| `EnvApiKeyAuth` | 从模型配置声明的环境变量中读取 API key |

---

## 14. 认证解析不变量

认证系统应满足以下不变量：

1. `AuthConfig` 不包含真实 secret。
2. `AuthCredential` 只表示本次调用的凭证输入。
3. `AuthView` 是 Provider 请求前的最终认证视图。
4. API Key 模型可以在未传入 `CallOptions.auth` 时读取环境变量。
5. OAuth 模型必须显式传入 `OAuthBearerAuth`。
6. OAuth 模型不得从环境变量读取 token。
7. OAuth 模型不得从 credential store 读取 token。
8. `loushang.ai` 不执行 OAuth login。
9. `loushang.ai` 不执行 OAuth refresh。
10. 认证类型不匹配必须失败。
11. 缺少认证必须失败。
12. 多余认证不得静默忽略。
13. 所有 secret 必须脱敏。
14. Provider 认证失败必须归一化为认证错误。
15. 认证解析不得产生账号系统或 quota 系统职责。

---

## 15. 与上层应用的职责分工

| 能力                               |    `loushang.ai` | 上层应用 / service |
| ---------------------------------- | ---------------: | -----------------: |
| 读取 API key 环境变量              |               是 |               可选 |
| 接收显式 API key                   |               是 |                 是 |
| 接收显式 OAuth access token        |               是 |                 是 |
| 构造 Provider auth header          |               是 |                 否 |
| OAuth 登录                         |               否 |                 是 |
| OAuth refresh                      |               否 |                 是 |
| 凭证存储                           |               否 |                 是 |
| 多账号选择                         |               否 |                 是 |
| Provider account profile           |               否 |                 是 |
| quota 查询                         |               否 |                 是 |
| billing 查询                       |               否 |                 是 |
| 根据认证状态切换模型               |               否 |                 是 |
| 处理 Provider 401/403 后的重试策略 | 否，只归一化错误 |                 是 |

---

## 16. 设计结论

`loushang.ai` 的认证能力应保持为模型调用链路中的轻量认证解析层。

最终边界如下：

```text
API Key:
  可以显式传入；
  未传入时，可以根据 models.json 中声明的环境变量读取。

OAuth:
  必须显式传入 OAuthBearerAuth；
  不从环境变量读取；
  不从本地 store 读取；
  不自动登录；
  不自动刷新。

NoAuth:
  明确无认证；
  如果传入多余认证，应报错。

loushang.ai:
  只负责把认证凭证解析成 Provider 请求 headers。

上层应用:
  负责 OAuth 登录、刷新、存储、账号选择、quota、billing 和认证策略。
```

该设计保证 `loushang.ai` 的职责保持简单、被动和可验证，同时为 API Key 与 OAuth 两类主流认证方式提供清晰、稳定的调用边界。

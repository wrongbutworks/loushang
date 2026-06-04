# Loushang AI OpenAI-Compatible Compat

## Why Compat Exists

`openai-completions` 不是单一 provider 的协议，而是一整个兼容生态。

同样叫做 OpenAI-compatible，不同 provider 在下列方面仍可能不同：

- request 顶层字段是否支持
- message role 是否支持 `developer`
- tool result message 是否要求额外字段
- thinking / reasoning 参数写到哪里
- thinking / reasoning 的值域是等级还是开关
- gateway / router 是否支持 provider routing 偏好

如果把这些差异直接散落在 provider 主流程里，结果通常会是：

- 主链路被 provider 名字分支淹没
- 新接一个 provider 时只能继续堆 `if/elif`
- 上层统一语义和下层协议编码混在一起

`compat` 的职责就是把这些差异收口到一层 provider-boundary 协议适配语义里。

---

## What Compat Is

在 `loushang.ai` 里，`compat` 不是业务策略，也不是产品层选项。

`compat` 是：

- 同一应用协议族内部的 provider-specific 协议差异描述
- provider adapter 在发送请求前要读取的一组编码规则

`compat` 不是：

- 用户输入
- agent policy
- 模型能力本身
- provider 名字的别名表

更准确地说：

- `thinking_level` / `reasoning` 表达的是上层统一语义
- `compat` 表达的是这些统一语义如何编码到具体 provider 请求里

---

## What Compat Already Covers

在 `reference AI SDK` 的 `openai-completions` 兼容层里，`compat` 目前已经覆盖了多类差异。

### Request Parameter Compat

- `supportsStore`
- `supportsUsageInStreaming`
- `maxTokensField`
- reasoning / thinking 参数格式

### Message Shape Compat

- `supportsDeveloperRole`
- `requiresToolResultName`
- `requiresAssistantAfterToolResult`
- `requiresThinkingAsText`

### Tool Schema Compat

- `supportsStrictMode`

### Router / Gateway Compat

- `openRouterRouting`
- `vercelGatewayRouting`

这些差异说明：

`compat` 从来不只是 reasoning 开关，而是一整层 OpenAI-compatible provider 行为差异的收口点。

---

## Moonshot Scenario

Moonshot Kimi K2.5 这次把 `compat` 的问题暴露得很典型。

场景是：

1. `kimi_agent_openai.py` 走 Moonshot 的 OpenAI-compatible chat completions 接口
2. 首轮对话可以正常返回，并且能发出 tool call
3. tool result 回传后，第二轮请求被 Moonshot 拒绝
4. 服务端返回 400：
   - `thinking is enabled but reasoning_content is missing in assistant tool call message`

这说明服务端把当前会话当成“thinking enabled”的会话校验，但客户端在 tool call message replay 时没有提供对应的 reasoning 内容。

随后查到 Moonshot 官方说明：

- Kimi K2.5 支持 `thinking` 参数
- 只接受：
  - `{"type": "enabled"}`
  - `{"type": "disabled"}`
- OpenAI SDK 没有原生 `thinking` 参数
- 需要通过 `extra_body` 传递

也就是说，Moonshot 的官方协议不是：

- `reasoning_effort`
- `reasoning.effort`
- `enable_thinking`

而是：

- `extra_body.thinking.type = "enabled" | "disabled"`

这就是一个标准的 provider-specific compat 问题。

---

## What The Moonshot Bug Actually Revealed

这次问题不只是“少发了一个字段”。

它暴露了两个层次的问题。

### 1. We Over-Unified Reasoning

之前容易把 reasoning / thinking 想成“只是字段名不同”：

- OpenAI Responses: `reasoning.effort`
- OpenAI Completions: `reasoning_effort`
- Z.ai / Qwen: `enable_thinking`

Moonshot 证明这并不成立。

这些参数不仅名字不同，语义粒度也不同：

- 有的是 effort 型
  - 值域是 `low / medium / high`
- 有的是 toggle 型
  - 值域是 `true / false`
  - 或 `enabled / disabled`

Moonshot 属于 toggle 型，而且是通过 `extra_body` 传的 provider-specific toggle。

### 2. Provider Logic Was Still Too String-Branch Driven

如果 compat 只是：

- `thinkingFormat = "openai" | "zai" | "qwen" | "openrouter"`

那 provider 最终还是会长成：

- `if compat["thinkingFormat"] == "...": ...`

这种写法对少数已知 provider 能工作，但扩展性有限。

Moonshot 一来，就需要继续加新的分支和新的例外。

这说明当前 compat 方向是对的，但表达方式还不够抽象。

---

## The Key Distinction: Semantics vs Encoding

要理解 `compat`，关键是先把“统一语义”和“协议编码”分开。

### Unified Semantics

这是上层 runtime / agent 想表达的意图，例如：

- 模型是否支持 reasoning
- 当前请求是否要关闭 thinking
- 当前请求是否要设置 reasoning effort

这些属于产品语义或 provider-agnostic 语义。

### Protocol Encoding

这是同一个意图在不同 provider 上如何落地，例如：

- `reasoning.effort = "medium"`
- `reasoning_effort = "medium"`
- `enable_thinking = true`
- `extra_body.thinking.type = "enabled"`

这些属于 provider-boundary 编码问题。

`compat` 应该描述的是后者。

---

## A Better Compat Direction

当前 `thinkingFormat` 这种字段已经比“按 provider 名字直接分支”好，但还不够。

更稳的方向是：

- 不让 `compat` 只表达厂商标签
- 让 `compat` 表达协议语义和编码位置

以 reasoning / thinking 为例，至少应该先区分两类语义：

### Effort Mode

适用于：

- `reasoning.effort`
- `reasoning_effort`

特点：

- 表达推理强度
- 值域通常是 `minimal / low / medium / high / xhigh`

### Toggle Mode

适用于：

- `enable_thinking`
- `extra_body.thinking.type`

特点：

- 只表达开关
- `off` 与非 `off` 的映射比等级更重要

Moonshot 明确属于 toggle mode，不该被硬塞成 effort mode 的别名。

---

## Recommended Modeling Rule

如果后续继续演进 `compat`，建议遵守这个原则：

- 模型能力描述“支持什么语义”
- compat 描述“怎么编码这个语义”

也就是：

- capability 层回答：
  - 这个模型是否支持 reasoning
  - 支持 effort 还是只支持 toggle
- compat 层回答：
  - 这个语义写到哪个字段
  - 这个 provider 期待什么值域

这比“provider 叫 moonshot / qwen / zai，所以走哪条分支”更稳。

---

## How Compat Should Be Configured

`compat` 配置不应该直接表达“这是哪家 provider”，而应该表达：

- 这个 provider 在当前协议族下支持哪种 reasoning 语义
- 这个语义应该被编码到哪个请求位置

### Step 1: Describe The Semantic Kind

先区分 reasoning / thinking 是哪一类语义。

- `effort`
  - 表示推理强度
  - 常见值域：`minimal / low / medium / high / xhigh`
- `toggle`
  - 只表示开关
  - 常见映射：`off -> disabled/false`
  - 其余 -> `enabled/true`

### Step 2: Describe The Encoding Location

再描述这个语义写到请求的哪个字段。

例如：

- top-level field
- nested object path
- `extra_body` path
- `chat_template_kwargs` path

### Step 3: Describe The Value Style

最后描述开关或等级的具体编码风格。

对 toggle 型，常见风格包括：

- `bool`
  - `true / false`
- `enabled`
  - `"enabled" / "disabled"`
- `on`
  - `"on" / "off"`

对 effort 型，通常只需要：

- 原样 effort
- 或 effort map

---

## Example Config Shapes

下面这些例子不是最终 frozen schema，而是推荐的建模方向。

### OpenAI Responses

```json
{
  "reasoningMode": "effort",
  "compat": {
    "reasoningPath": "reasoning.effort",
    "reasoningStyle": "effort"
  }
}
```

### OpenAI-Compatible Completions With `reasoning_effort`

```json
{
  "reasoningMode": "effort",
  "compat": {
    "reasoningPath": "reasoning_effort",
    "reasoningStyle": "effort"
  }
}
```

### Z.ai / Qwen Boolean Thinking Toggle

```json
{
  "reasoningMode": "toggle",
  "compat": {
    "reasoningPath": "enable_thinking",
    "reasoningStyle": "bool"
  }
}
```

### Moonshot Kimi K2.5

```json
{
  "reasoningMode": "toggle",
  "compat": {
    "reasoningPath": "extra_body.thinking.type",
    "reasoningStyle": "enabled"
  }
}
```

这个配置表达的是：

- 语义上它不是 effort 型，而是 toggle 型
- 编码上要写到 `extra_body.thinking.type`
- 开态/关态采用 `"enabled" / "disabled"` 这组字面值

---

## Why This Shape Is Better Than Provider Labels

如果 compat 只是：

- `thinkingFormat = "moonshot"`
- `thinkingFormat = "zai"`
- `thinkingFormat = "qwen"`

那么 provider 代码最终仍然需要知道：

- moonshot 要写到 `extra_body.thinking.type`
- zai 要写 `enable_thinking = true/false`
- qwen-chat-template 要写 `chat_template_kwargs.enable_thinking`

这实际上还是厂商标签分支。

而如果 compat 直接描述：

- 语义类型
- 字段路径
- 值风格

那么 provider 可以更像一个通用编码器，而不是厂商分发表。

---

## Practical Takeaway

从 Moonshot 这个场景，团队应该记住三件事。

1. `compat` 是必要的。
   - OpenAI-compatible 不是一个完全统一的协议面。

2. reasoning / thinking 不能只按字段名来理解。
   - 还要区分 effort 语义和 toggle 语义。

3. `compat` 的最终方向应该是结构化协议编码，而不是不断扩充 provider 名字分支。

Moonshot 这次的问题，表面上是一个 400 错误，实际上是在提醒我们：

`compat` 不是可选补丁层，而是 OpenAI-compatible provider 体系里的正式设计对象。

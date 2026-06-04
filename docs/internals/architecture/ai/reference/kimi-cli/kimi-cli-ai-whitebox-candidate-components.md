# Kimi-CLI AI Whitebox Candidate Components

## Scope

本文档从白盒视角列出 `kimi-cli` 中 AI 子系统的候选组件清单。  
这里主要观察的是 `packages/kosong` 里的稳定职责单元，而不是 CLI 外壳或应用层命令编排。

本文档只讨论：

- `kosong` 内部候选组件
- 每个候选组件的大致对应位置
- 作用与职责
- 内聚 / 耦合的初步判断

本文档不讨论：

- `loushang-ai` 的最终组件划分
- 最终文件边界与包边界
- 组件与类的一对一映射

---

## Reading Rule

这里的“候选组件”并不意味着：

- `kimi-cli` 已经显式把它命名为组件
- 它必须在 `loushang-ai` 中被原样复制

本文档只做两件事：

1. 识别 `kimi-cli` AI 子系统内部已经存在的稳定职责单元
2. 为 `loushang-ai` 的白盒设计补充参考线索，尤其是 streaming、tooling、runtime 边界与 carrier 接入方式

---

## Candidate Components

## 1. Message Type System

**类别：**

- 逻辑功能组件
- 逻辑支撑组件

**对应位置：**

- [message.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/message.py)

**作用：**

- 作为 `kosong` 内部统一消息协议与内容部件模型

**主要职责：**

- 定义 `Message`
- 定义 `ContentPart` 及其 registry
- 定义 `TextPart`、`ThinkPart`、`ImageURLPart`、`AudioURLPart`、`VideoURLPart`
- 定义 `ToolCall` 与 `ToolCallPart`
- 提供 `merge_in_place` 语义，用于流式组装
- 处理消息内容的序列化 / 反序列化与文本提取

**初步判断：**

- 内聚性高
- 是 `kosong` 最核心的内部语义骨架之一
- 与 provider、tooling、generate orchestration 都有依赖关系，但边界相对稳定

---

## 2. Chat Provider Protocol

**类别：**

- 逻辑功能组件
- 边界逻辑组件

**对应位置：**

- [chat_provider/__init__.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/__init__.py)

**作用：**

- 定义统一的 provider 抽象面

**主要职责：**

- 定义 `ChatProvider`
- 定义 `RetryableChatProvider`
- 定义 `StreamedMessage`
- 定义 `StreamedMessagePart`
- 定义 `TokenUsage`
- 定义 `ThinkingEffort`
- 定义 provider error family
- 提供 `convert_httpx_error`

**初步判断：**

- 内聚性高
- 是 `kosong` AI 子系统的主边界协议
- 对外部 provider 高耦合被压在 protocol 与 adapter 层之内

---

## 3. Generate Orchestration

**类别：**

- 逻辑功能组件

**对应位置：**

- [_generate.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/_generate.py)

**作用：**

- 承担一次消息生成的统一编排

**主要职责：**

- 调用 `chat_provider.generate`
- 消费 `StreamedMessage`
- 将 streaming part 合并成最终 `Message`
- 在完整 tool call 出现时触发 `on_tool_call`
- 收敛 `id`、`usage` 与最终 `GenerateResult`
- 在空结果时抛出 `APIEmptyResponseError`

**初步判断：**

- 内聚性高
- 是 `kosong` 区别于单纯 provider wrapper 的关键核心组件
- 与 `Message Type System`、`Chat Provider Protocol`、callback 支撑层有直接依赖

---

## 4. Stream Merge / Message Assembly

**类别：**

- 逻辑支撑组件

**对应位置：**

- [_generate.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/_generate.py)
- [message.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/message.py)

**作用：**

- 把 provider 返回的增量 part 收敛成完整消息

**主要职责：**

- 基于 `merge_in_place` 合并连续 text / thinking / tool argument 增量
- 处理 `pending_part`
- 把完整 `ToolCall` 与 `ContentPart` 追加到最终 `Message`
- 忽略 orphaned `ToolCallPart`

**初步判断：**

- 职责稳定
- 当前实现上附着在 `_generate.py` 与 `message.py`
- 在 `loushang-ai` 白盒阶段很值得单独识别为组件或责任簇

---

## 5. Provider Adapter Layer

**类别：**

- 边界逻辑组件

**对应位置：**

- [chat_provider/kimi.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/kimi.py)
- [contrib/chat_provider/anthropic.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/anthropic.py)
- [contrib/chat_provider/openai_responses.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/openai_responses.py)
- [contrib/chat_provider/openai_legacy.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/openai_legacy.py)
- [contrib/chat_provider/google_genai.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/google_genai.py)

**作用：**

- 隔离 `kosong` 与真实模型 provider API / SDK / transport 的变化

**主要职责：**

- 把内部 `Message` / `Tool` 转为 provider 请求
- 管理 SDK client 或 HTTP client
- 处理 streaming / non-streaming 响应
- 将 provider event 转成 `StreamedMessagePart`
- 收敛 provider-specific usage、thinking、tool call 语义

**初步判断：**

- 单个 adapter 内聚性通常较高
- 对外部协议与 SDK 天然高耦合
- 这种耦合被局部化在边界层，是合理的

---

## 6. Provider Payload Transformation

**类别：**

- 逻辑支撑组件
- 边界逻辑组件

**对应位置：**

- [chat_provider/kimi.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/kimi.py)
- [contrib/chat_provider/anthropic.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/anthropic.py)
- [contrib/chat_provider/openai_responses.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/openai_responses.py)

**作用：**

- 承担内部消息模型与外部 wire format 之间的双向转换

**主要职责：**

- message -> provider payload
- tool -> provider tool schema
- tool result message -> provider tool result block
- provider stream event -> `StreamedMessagePart`
- provider usage -> `TokenUsage`
- thinking / reasoning 互转

**初步判断：**

- 这层职责非常稳定
- 当前更多分布在各 provider 文件内部
- 是白盒阶段很容易被低估、但对高内聚低耦合非常关键的责任簇

---

## 7. Provider Client / Carrier Management

**类别：**

- 逻辑技术组件
- 边界逻辑组件

**对应位置：**

- [chat_provider/openai_common.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/openai_common.py)
- [chat_provider/kimi.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/kimi.py)
- [contrib/chat_provider/anthropic.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/anthropic.py)

**作用：**

- 管理 SDK client 生命周期与重建

**主要职责：**

- 创建 OpenAI client
- 关闭被替换 client，避免 shared client 被误关
- retry 后重建 client
- 管理 `base_url`、`api_key`、`client_kwargs`

**初步判断：**

- 对运行时稳定性影响很大
- 这是一个明显的内部技术支撑组件，不应被误看成仅仅是若干 helper function

---

## 8. Provider Error Mapping

**类别：**

- 逻辑技术组件
- 边界逻辑组件

**对应位置：**

- [chat_provider/__init__.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/__init__.py)
- [chat_provider/openai_common.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/openai_common.py)
- [contrib/chat_provider/anthropic.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/anthropic.py)

**作用：**

- 把 transport / SDK error 收敛为统一 provider error family

**主要职责：**

- `httpx` error -> `ChatProviderError` family
- OpenAI SDK error -> `ChatProviderError` family
- Anthropic SDK error -> `ChatProviderError` family
- 区分 timeout / connection / status / empty response 等错误

**初步判断：**

- 内聚性较高
- 是跨 provider 共享的重要横切支撑点
- 如果不单独识别，后面很容易散落到各 adapter 内部

---

## 9. Thinking / Reasoning Mapping

**类别：**

- 逻辑支撑组件
- 逻辑技术组件

**对应位置：**

- [chat_provider/openai_common.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/openai_common.py)
- [chat_provider/kimi.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/kimi.py)
- [contrib/chat_provider/anthropic.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/anthropic.py)
- [contrib/chat_provider/openai_responses.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/chat_provider/openai_responses.py)

**作用：**

- 在统一 `ThinkingEffort` 与各 provider 的 thinking / reasoning 机制之间做映射

**主要职责：**

- `ThinkingEffort` 到 OpenAI `ReasoningEffort` 的映射
- `ThinkingEffort` 到 Anthropic thinking config 的映射
- `ThinkingEffort` 到 Kimi reasoning / extra_body 的映射
- provider 返回 reasoning/thinking block 时的逆向归一

**初步判断：**

- 这不是边角 helper，而是 `kosong` 统一抽象能成立的关键支撑层
- 当前分散在 provider 与 shared helper 中

---

## 10. Tool Type System

**类别：**

- 逻辑功能组件
- 逻辑支撑组件

**对应位置：**

- [tooling/__init__.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/tooling/__init__.py)

**作用：**

- 统一定义模型可见工具、工具结果与用户显示块

**主要职责：**

- 定义 `Tool`
- 定义 `CallableTool` 与 `CallableTool2`
- 定义 `ToolReturnValue`、`ToolOk`、`ToolError`
- 定义 `DisplayBlock` 与其 registry
- 定义 `ToolResult`、`Toolset`
- 进行 JSON Schema 与参数验证

**初步判断：**

- 内聚性高
- 是 `kosong` 将 tool calling 变成稳定能力的核心支撑组件
- 与 message、generate orchestration、provider adapter 均有稳定接口关系

---

## 11. Tool Execution Runtime

**类别：**

- 逻辑功能组件
- 逻辑技术组件

**对应位置：**

- [tooling/simple.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/tooling/simple.py)
- [tooling/error.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/tooling/error.py)

**作用：**

- 承担工具注册、查找、参数解析、并发执行与错误收敛

**主要职责：**

- `SimpleToolset` 注册 / 删除工具
- tool call 参数 JSON 解析
- 工具参数校验
- 并发执行工具调用
- 把找不到工具、JSON 解析失败、校验失败、运行失败统一包装成 `ToolReturnValue`

**初步判断：**

- 内聚性高
- 与 provider 耦合较低，与 tool type system 耦合较高
- 已经具有明显的独立组件形态

---

## 12. MCP Content Conversion

**类别：**

- 边界逻辑组件
- 逻辑支撑组件

**对应位置：**

- [tooling/mcp.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/tooling/mcp.py)

**作用：**

- 把 MCP tool result content 转换为 `kosong.message.ContentPart`

**主要职责：**

- 转换 text/image/audio/video 内容
- 支持 embedded resource / resource link
- 拒绝不支持的 mime type 或内容类型

**初步判断：**

- 是明显的边界吸收组件
- 不是主流程核心组件，但对 MCP 集成是必要稳定边界

---

## 13. Context Storage Abstraction

**类别：**

- 逻辑功能组件
- 逻辑支撑组件

**对应位置：**

- [contrib/context/linear.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/contrib/context/linear.py)

**作用：**

- 提供线性消息历史上下文与持久化存储抽象

**主要职责：**

- 定义 `LinearContext`
- 定义 `LinearStorage` protocol
- 提供 `MemoryLinearStorage`
- 提供 `JsonlLinearStorage`
- 记录 token count
- 恢复消息历史

**初步判断：**

- 内聚性较高
- 属于 AI 子系统外围但稳定的支撑组件
- 对 `loushang-ai` 来说更像参考职责，不一定需要原样复制

---

## 14. Async Callback Bridge

**类别：**

- 逻辑技术组件

**对应位置：**

- [utils/aio.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/utils/aio.py)

**作用：**

- 统一处理 sync/async callback

**主要职责：**

- 判断 callback 返回值是否 awaitable
- 用统一方式调用 `on_message_part` / `on_tool_call`

**初步判断：**

- 规模很小，但职责明确
- 适合作为内部技术支撑点，而不是忽略为纯琐碎 helper

---

## 15. Test / Chaos / Mock Provider Support

**类别：**

- 逻辑技术组件
- 扩展点组件

**对应位置：**

- [chat_provider/mock.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/mock.py)
- [chat_provider/chaos.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/chaos.py)
- [chat_provider/echo/echo.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/echo/echo.py)
- [chat_provider/echo/scripted_echo.py](/home/dev/workspace/kimi-cli/packages/kosong/src/kosong/chat_provider/echo/scripted_echo.py)

**作用：**

- 提供 mock、chaos、scripted echo 等测试/实验 provider 支撑

**主要职责：**

- mock streamed message
- chaos transport 注入与 retry 恢复验证
- scripted / echo provider 用于演示与测试

**初步判断：**

- 这些不是生产主能力
- 但它们构成了 `kosong` 白盒阶段很值得识别的验证与扩展支撑层

---

## 16. Candidate Clusters Not Yet Fully Lifted

以下内容在 `kimi-cli` 中已经形成稳定职责簇，但未必已经被显式提升为更清晰的一级组件：

- provider stream event normalization
- tool result conversion policy，例如 `extract_text`
- usage accounting normalization
- multimodal input/output conversion
- transport retry recovery

这些职责簇在 `loushang-ai` 白盒阶段应继续观察，判断是否需要提升为更明确的逻辑支撑组件或边界组件。

---

## Summary

从白盒视角看，`kimi-cli` 的 AI 子系统和 `reference AI SDK` 的重心不一样：

- `reference AI SDK` 更强调顶层 API、registry、统一 public contract
- `kimi-cli` 更强调消息模型、generate orchestration、provider runtime、tooling、stream merge

对 `loushang-ai` 而言，这意味着：

- 不能只参考 `reference AI SDK`
- 也不能只参考 `kimi-cli`
- 需要把 `reference AI SDK` 的 contract / registry 视角与 `kimi-cli` 的 runtime / assembly / tooling 视角组合起来

---

## Takeaway For Loushang-AI

对后续 `loushang-ai` 白盒设计，`kimi-cli` 提供的最重要线索不是“有哪些 provider”，而是这些内部稳定职责：

- 消息部件与可合并流式部件模型
- 单次生成编排器
- 流式组装责任簇
- tool type system 与 tool execution runtime
- provider payload transformation
- provider carrier management
- error mapping / thinking mapping / MCP content conversion

这些都应作为 `loushang-ai` 白盒候选功能或候选组件的重要输入。

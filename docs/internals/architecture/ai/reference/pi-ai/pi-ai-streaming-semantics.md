## PI-AI 流式事件语义（参考）

本文基于 `pi-mono/packages/ai/src` 的实现与注释，总结 PI-AI 在流式事件上的完整设计细节，作为 Loushang-AI 的对照与参考。

### 1. 概览与目标
- 目标：提供稳定的“事件流”语义，屏蔽不同 Provider 的协议差异，支持思考（thinking）、工具（tool use）、多模态、用量统计和可靠落幕。
- 层次：Provider 原始事件 →（映射/规约）→ 统一的 `AssistantMessageEventStream` 事件序列。
- 关键原则：
  - 判别联合事件（基于 `type` 字段）；
  - 块（content block）级别的 start/delta/end 生命周期；
  - 在完成态前补齐一切未关闭块，保证“流必有终”；
  - 宽容兼容：能在“只有 delta + done”的协议上推断出 start/end。

### 2. 统一事件模型
- 控制流
  - start / done / error
  - stop_reason（stop/length/toolUse/error）
  - usage（input/output/cacheRead/cacheWrite）
- 内容流
  - 文本：text_start / text_delta / text_end
  - 思考：thinking_start / thinking_delta / thinking_end（含 redacted/signature）
  - 工具：toolcall_start / toolcall_delta / toolcall_end（增量 JSON → 完整 arguments）
  - 图片：image（按块）
- 事件输出策略
  - Provider 若原生有块边界：严格对应 start/delta/stop → start/delta/end；
  - 若无块边界：在首次 delta 时补发 start；结束时补发 end。

### 3. Anthropic messages.stream（content_block_*）映射
- 输入与 headers
  - `anthropic-beta`：启用 `fine-grained-tool-streaming-2025-05-14`；对旧模型可叠加 `interleaved-thinking-2025-05-14`
  - 透传 `anthropic-version` 与代理网关要求的动态头
  - `tool_choice`：`auto | any | none | { type: "tool", name }`
  - 思考模式：禁用 / 预算式（`budget_tokens`）/ 适配式（`output_config.effort`）
- 事件到统一语义
  - message_start
    - 记录 `response_id`
    - 初始化 usage 并发出首个 `usage_delta`
  - content_block_start
    - type=text → text_start（为该块建立文本缓冲）
    - type=thinking → thinking_start（建立思考缓冲、可选签名缓冲）
    - type=redacted_thinking → thinking_start（redacted 标志+opaque data）
    - type=tool_use → toolcall_start（携带 id/name，建立 `partial_json` 缓冲）
    - type=image → 记录图片块（可直接输出 image 事件或聚合到最终消息）
  - content_block_delta
    - text_delta → text_delta（累加文本缓冲）
    - thinking_delta → thinking_delta（累加思考缓冲）
    - input_json_delta → toolcall_delta（输出原始片段，同时拼接 `partial_json`）
    - signature_delta → 累加到思考签名缓冲
  - content_block_stop
    - text → text_end（输出聚合文本）
    - thinking → thinking_end（输出聚合思考；缺签名时按策略降级）
    - tool_use → 解析 `partial_json` 为 `arguments`，发 toolcall_end（带完整 `toolCall`）
  - message_delta
    - 若含 `stop_reason`：映射为 stop/length/toolUse/error
    - 若含 `usage`：仅覆盖存在的字段（不抹掉 `message_start` 的初始值）
  - message_stop/response.completed
    - 补齐所有尚未关闭的块
    - 发出完成态（等价 `response_done`）
  - error/response.failed
    - 发 `response_error`（带原始错误描述）
    - finally 中仍需补齐未关闭块并落幕

### 4. OpenAI（Completions / Responses）映射
- Completions（chat.completions.stream）
  - 主要是文本增量，可能含 tool_calls（一次性或增量）
  - 统一为：text_delta 流；出现工具时映射 toolcall_start/args_delta/end（依赖 SDK 事件粒度）
- Responses（responses.create with streaming）
  - 输出项（output_item.*）与文本/函数参数增量（output_text.delta/function_call_arguments.delta）
  - reasoning_summary_text.delta（thinking 增量）
  - 对齐：thinking_delta/text_delta；函数参数增量 → toolcall_delta；item 完成 → toolcall_end 或 text_end
  - 常见兼容点：某些代理不发块结束事件，需要在完成或 finally 时根据缓冲补齐 *_end

### 5. 块并行/交错与索引
- Anthropic 的 `index` 用于区分并行/交错的多个块
- PI-AI 在 provider 适配层维护 `blocks: Map<number, BlockState>`：
  - kind: "text" | "thinking" | "redacted_thinking" | "tool" | "image"
  - 文本/思考缓冲；工具 `partial_json`；思考签名缓冲
- 在 stop 时输出对应 *_end/done，并清理 `BlockState`
- 对外的 `contentIndex`（展示/最终消息位置）按“最终内容顺序”计算回填

### 6. 思考（thinking）与签名（signature）
- thinking_delta：思考文本增量
- signature_delta：思考签名增量（用于安全/完整性）
- redacted_thinking：思考内容不可见，仅保留 opaque data
- 结束策略：
  - 有签名：随 thinking_end 以结构化形式输出/保留
  - 无签名或流被中断：降级为普通文本，防止 API 拒绝并保持可用

### 7. 工具调用的增量 JSON
- input_json_delta：增量字符串片段，逐片段原样输出 `toolcall_delta`
- 内部并行维护 `partial_json`（字符串拼接）
- end 时使用健壮解析获取 `arguments: dict`；失败则 `{}` 并记录
- 根据需要支持“严格/宽松模式”：严格要求工具块必须 start→delta→end 有序；宽松允许缺失并在 finally 补救

### 8. usage / stop_reason / 完成态
- usage
  - `message_start` 报告初始用量（尤其 input/cache）
  - `message_delta` 按存在字段覆盖增量（不覆盖缺失字段）
  - 最终 total 由实现方计算（PI-AI 在 TS 端聚合）
- stop_reason
  - 规范映射：end_turn→stop；max_tokens→length；tool_use→toolUse；refusal/sensitive→error
- 完成态
  - 必须在 finally 确保发出完成（即使之前错误）
  - 在完成前补齐一切未关闭块，保证“事件流总能落幕”

### 9. 特性开关与 Headers 策略
- Beta/Feature headers
  - `anthropic-beta: fine-grained-tool-streaming-2025-05-14` 必开
  - 根据模型是否 4.6 决定是否加 `interleaved-thinking-2025-05-14`
- 代理网关 headers
  - 透传 `anthropic-version` 等必需头
  - OAuth/Claude Code：追加身份与 UA 头、工具名大小写映射（与本地 tools 对齐）
- tool_choice
  - required/auto/any/{tool} 直接影响是否产生工具块

### 10. 兜底与兼容
- 仅出现 `stop_reason=tool_use` 而无细粒度工具流
  - 首选：开启/合并 beta 头，确认代理支持
  - 兜底：发出高层提示事件或走 agent 回路本地执行工具并回灌 tool_result
- 仅文本 delta、无块边界
  - 在首次 delta 推导 start；完成时补 end
- 异常/中断
  - 发 `response_error`，finally 补齐 end 与完成

### 11. 可观测与回放
- Debug/trace：打印上游原始事件与映射后事件（可采样）
- 回放：保存完整事件，离线重放到装配器，便于对照差异与回归
- 指标：块生命周期、工具调用完成率、usage 完整性、stop_reason 分布

### 12. 与 Loushang-AI 的对照
- 事件等价：text/thinking/tool（start/delta/end）、usage、stop_reason、done/error
- 差异与策略
  - PI-AI：在支持块边界的协议上优先使用 start/stop 对齐
  - Loushang-AI：默认允许在 Assembler 侧从 delta 推断 start/end；亦可在 Provider 适配层显式发 start/end 以逐事件对齐
- 建议：在 Anthropic 适配中默认显式发 start/end；在无边界协议中保持推断与补齐

### 13. 测试矩阵与示例
- 基础流：纯文本、长文本、多段文本
- 思考：有签名 / 无签名 / redacted_thinking
- 工具：细粒度工具流（start/delta/end）/ 仅 stop_reason=tool_use
- 多模态：图文混排、仅图片
- 失败路径：provider error / 传输中断 / 超时
- 代理差异：官方 SDK / 兼容代理（如 DashScope、Kimi 等）

### 14. 结语
PI-AI 通过“块级生命周期 + 用量/停因 + 完成收口”的统一设计，在多 Provider/代理场景下保持了稳定的一致性与可观测性。该语义已被 Loushang-AI 采纳并在实现层做了最小偏差的等价对齐，必要时可在 Provider 适配层开启显式 start/end 以满足严格逐事件对齐的需要。

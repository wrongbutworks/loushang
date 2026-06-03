# Loushang-AI Trace Events

本文定义 `loushang-ai` Provider 层的 trace 事件，用于日志与指标接入。事件通过 `StreamOptions.trace(event: dict)` 回调发出。

## 事件类型

- request_start
- attempt
- attempt_error
- response_success
- request_error
- request_end
- fallback（仅 auto 传输发生回退时）
- reconnect（仅 WS 发生自动重连时）

## 通用字段

- api: string（如 `openai-completions` / `openai-responses` / `anthropic-messages`）
- provider: string（如 `openai` / `kimi`）
- endpoint: string（路由路径，如 `/chat/completions`、`/responses`、`/v1/messages`）
- transport: `"sse"` | `"websocket"`
- sessionId: string | null
- timing: { startTs: number, endTs?: number, attempt?: number }
- reason/message: string（错误时）

WS 相关（可选）：

- ws: { reused: boolean, ttlSeconds: number, poolSize: number }

回退事件：

- fallback: { from: "websocket", to: "sse", reason: string }

## 使用示例

```python
from loushang.ai.options import OpenAICompletionsOptions

def trace_logger(evt: dict):
    print("TRACE", evt)

opts = OpenAICompletionsOptions(trace=trace_logger, retries=1, timeout=30)
# 传给 stream/complete
```

## 最佳实践

- 将 trace 事件转为 JSON 行输出或接入 OpenTelemetry
- 在生产环境可按 provider/api/endpoint/transport/sessionId 建立维度聚合
- 对 attempt_error/request_error 分类统计（transport/provider/semantic）

## 详细事件示例

### 1) WebSocket 复用（transport=auto 命中 WS）

```json
{"type":"request_start","api":"openai-responses","provider":"openai","endpoint":"/responses","transport":"sse","sessionId":"sess-1","timing":{"startTs":1711872000.12}}
{"type":"attempt","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-1","ws":{"reused":true,"ttlSeconds":300,"poolSize":1},"timing":{"startTs":1711872000.12,"attempt":1}}
{"type":"response_success","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-1"}
{"type":"request_end","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-1","timing":{"startTs":1711872000.12,"endTs":1711872001.03}}
```

说明：
- request_start 里 transport 初始标记为 sse（默认），实际 attempt 命中 websocket 时，后续事件（含 request_end）以实际传输为准
- ws.reused=true 表示命中连接池；poolSize 为当前池大小

### 2) WebSocket 失败回退到 SSE（transport=auto）

```json
{"type":"request_start","api":"openai-responses","provider":"openai","endpoint":"/responses","transport":"sse","sessionId":"sess-2","timing":{"startTs":1711873000.50}}
{"type":"attempt","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-2","ws":{"reused":false,"ttlSeconds":300,"poolSize":0},"timing":{"startTs":1711873000.50,"attempt":1}}
{"type":"attempt_error","api":"openai-responses","provider":"openai","reason":"transport","message":"dial timeout","transport":"websocket"}
{"type":"fallback","api":"openai-responses","provider":"openai","fallback":{"from":"websocket","to":"sse","reason":"ws_failed"}}
{"type":"attempt","api":"openai-responses","provider":"openai","transport":"sse","sessionId":"sess-2","timing":{"startTs":1711873000.50,"attempt":2}}
{"type":"response_success","api":"openai-responses","provider":"openai","transport":"sse"}
{"type":"request_end","api":"openai-responses","provider":"openai","transport":"sse","timing":{"startTs":1711873000.50,"endTs":1711873001.20}}
```

### 3) SSE 正常流转（Anthropic/OpenAI Completions）

```json
{"type":"request_start","api":"anthropic-messages","provider":"anthropic","endpoint":"/v1/messages","transport":"sse","sessionId":null,"timing":{"startTs":1711874000.00}}
{"type":"attempt","api":"anthropic-messages","provider":"anthropic","transport":"sse","timing":{"startTs":1711874000.00,"attempt":1}}
{"type":"response_success","api":"anthropic-messages","provider":"anthropic","transport":"sse"}
{"type":"request_end","api":"anthropic-messages","provider":"anthropic","transport":"sse","timing":{"startTs":1711874000.00,"endTs":1711874000.70}}
```

### 4) WebSocket 自动重连（半开检测后重建连接）

```json
{"type":"request_start","api":"openai-responses","provider":"openai","endpoint":"/responses","transport":"sse","sessionId":"sess-3","timing":{"startTs":1711875000.10}}
{"type":"attempt","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-3","ws":{"reused":false,"ttlSeconds":300,"poolSize":0},"timing":{"startTs":1711875000.10,"attempt":1}}
{"type":"reconnect","api":"openai-responses","provider":"openai","sessionId":"sess-3","reason":"iter_error","message":"ws half-open detected"}
{"type":"response_success","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-3"}
{"type":"request_end","api":"openai-responses","provider":"openai","transport":"websocket","sessionId":"sess-3","timing":{"startTs":1711875000.10,"endTs":1711875000.95}}
```

说明：
- 在迭代事件过程中检测异常（半开/读失败）后，进行一次自动重连并重发 payload
- 通过 `reconnect` 事件报告原因与 message，便于问题定位与指标统计

## 连接池与 TTL（WebSocket）

- 连接键：`sessionId`
- 复用策略：命中相同 `sessionId` 的连接直接复用
- TTL：默认 300 秒；在每次成功事件后刷新心跳时间戳
- 清理：惰性清理（在发起新连接前或定期操作时剔除过期项）
- 建议：长会话应用可周期刷新 `sessionId` 或保持心跳，避免连接闲置被回收

### 重连策略（WebSocket）

- 最大重连次数：当前默认 1 次（防止无穷重试）
- 触发条件：事件迭代过程中的异常（如半开/读失败），重连后会重发本次请求 payload
- 观测：通过 `reconnect` 事件记录 `reason` 与 `message`，可据此告警或调整上限策略

# Loushang-AI Cost Estimation

## 背景与目标

在实际生产环境中，需要对每次调用的 token 用量进行成本预估，用于计费、配额与可观测。`loushang-ai` 在不影响推理主链与 Provider 行为的前提下，提供一个轻量、可选、容错的成本估算机制。

## 数据来源与单位

- 定价来源：`Model.pricing`
- 字段与单位（每百万 tokens 的美元价格，$/1_000_000 tokens）
  - `input`：提示（prompt/input）侧单价
  - `output`：生成（completion/output）侧单价
  - `cacheRead`：提示缓存读取单价（如 Provider 支持）
  - `cacheWrite`：提示缓存写入单价（如 Provider 支持）

## 聚合规则

事件流装配在结束阶段（`RawAssembler` 接收到 `response_done`）计算并写入最终 `AssistantMessage.usage.cost`：

- 写入字段：`input`、`output`、`cacheRead`、`cacheWrite`、`total`
- 计算公式：`cost = tokens * (rate per 1_000_000) / 1_000_000`
- `total = input + output + cacheRead + cacheWrite`

示例（以 2,000 input、500 output、100 cacheRead，费率分别为 1.5、6.0、0.3、3.0 为例）：

```
input   = 2000 * 1.5 / 1_000_000 = 0.003
output  =  500 * 6.0 / 1_000_000 = 0.003
cacheRead  = 100 * 0.3 / 1_000_000 = 0.00003
total  ≈ 0.00603
```

## 触发时机

- 由 `loushang.ai.event_stream.assembler.RawAssembler` 在 `response_done` 事件时基于传入的 `pricing` 做聚合
- `assembler` 本身不再反查 model registry

## 容错与不变式

- 若缺少定价、解析异常或 Provider 不支持相关用量字段，估算将被跳过
- 任何估算错误都不会阻断事件流结束或改变最终消息内容

## 最小示例

```python
from loushang.ai import complete, get_model

# 正常调用；如果模型 pricing 存在，结束后可在 AssistantMessage.usage.cost 中查看成本估算
# model = get_model("kimi-k2.5")
# message = await complete(model, {"messages": [...]})
# print(message.usage.cost)
```

## 与可观测/计费系统的关系

- 本估算为“本地近似”，目的是在不依赖 Provider 账单的前提下快速获得成本感知
- 真正的结算与审计应以 Provider 或网关账单为准（如 OpenAI/Azure/Vercel Gateway/OpenRouter 等）
- 建议结合统一的 trace/metrics，将 `usage` 与 `usage.cost` 作为事件属性输出

## 未来扩展

- 分层定价（按 Provider/Endpoint/Model 覆盖）
- 货币与汇率扩展
- 批量作业成本分摊策略
- 与实时账单 API 集成校验偏差

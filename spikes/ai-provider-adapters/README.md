# AI Provider Adapters Spike

## Goal

这个 spike 用于技术验证 `loushang.ai` 当前关于 provider adapter strategy 的关键设计是否可行。

本 spike 只验证：

- `ApiProvider registry -> top-level API -> provider adapter -> raw parts -> event stream` 这条主链路是否能跑通
- `anthropic-messages` adapter 是否能通过真实兼容端点跑通
- official SDK 与 `httpx-thin` 两类实现载体在同一真实端点上的可行性
- `complete()` / `complete_simple()` 是否能继续自然建立在 stream 语义之上
- cancellation 是否能在真实端点路径中稳定收敛为 `aborted`

本 spike 不验证：

- 全量 provider family
- `openai-compatible` adapter
- 完整 tool / thinking / image 事件矩阵
- oauth / token refresh 正式设计
- 正式包结构与发布形态

## Current Validation Constraint

当前环境下没有 OpenAI / Anthropic 官方 API key。  
但已经提供：

- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_API_KEY`
- `KIMI_API_KEY`

这些变量当前实际都指向同一个 Kimi API key。

因此，本次 spike 的真实端点验证前提冻结为：

- 使用 Kimi 提供的 Anthropic-compatible endpoint
- 通过 `anthropic-messages` 应用协议验证 adapter 设计

当前建议配置形态如下：

```json
{
  "providers": {
    "anthropic": {
      "baseUrl": "https://api.moonshot.cn/anthropic",
      "api": "anthropic-messages",
      "apiKey": "ANTHROPIC_AUTH_TOKEN",
      "models": [
        {
          "id": "kimi-k2.5",
          "name": "kimi-k2.5",
          "reasoning": false,
          "input": ["text"],
          "contextWindow": 200000,
          "maxTokens": 8192,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```

## Design Hypothesis

当前要验证的设计假设是：

1. `loushang.ai` 的主调用链应保持为：
   - top-level API
   - api provider registry
   - provider adapter
   - raw parts
   - assistant event stream
2. `anthropic-messages` 是可以优先落地的真实协议验证入口
3. official SDK 与 `httpx-thin` 都可以作为 adapter implementation carrier
4. `httpx-thin` 不只是 fallback，而是长期一等实现路径
5. `complete()` 可以继续建立在 `stream().result()` 之上
6. 真实端点路径中的 cancellation 仍应映射为：
   - `aborted`

## Spike Structure

建议在本目录中使用以下最小文件结构：

```text
spikes/ai-provider-adapters/
  README.md
  RESULTS.md
  config.py
  demo.py
  spike_ai_provider_adapters/
    __init__.py
    config.py
    types.py
    registry.py
    stream.py
    raw_parts.py
    assembler.py
    event_stream.py
    adapters/
      __init__.py
      faux.py
      anthropic_sdk.py
      anthropic_httpx.py
```

## File Responsibilities

### `config.py`

负责：

- 读取环境变量
- 生成最小模型与 provider 配置
- 固定 Kimi Anthropic-compatible endpoint

### `types.py`

定义这次 spike 需要的最小协议对象：

- `Model`
- `Context`
- `StreamOptions`
- `SimpleStreamOptions`
- `AssistantMessage`
- `AssistantMessageEvent`

### `registry.py`

定义最小 `ApiProvider registry`：

- `register_api_provider`
- `get_api_provider`

### `stream.py`

定义最小顶层入口：

- `stream`
- `complete`
- `stream_simple`
- `complete_simple`

### `raw_parts.py`

定义内部 raw part 形态，只覆盖本次最小验证所需路径。

### `assembler.py`

负责：

- raw parts -> `AssistantMessageEvent`
- partial / final `AssistantMessage` 收敛

### `adapters/anthropic_sdk.py`

验证路径 A：

- official `anthropic` SDK
- `base_url=https://api.moonshot.cn/anthropic`

### `adapters/anthropic_httpx.py`

验证路径 B：

- `httpx-thin`
- 直连同一兼容端点

### `demo.py`

提供最小运行入口，包含不同验证场景。

## Validation Scenarios

### Scenario 1: Faux/Mock Path Still Works

目标：

- 先用 mock / faux 路径验证顶层链路本身没有结构性错误
- 隔离真实网络与认证问题

### Scenario 2: Anthropic SDK Carrier Against Kimi Endpoint

目标：

- 使用官方 `anthropic` SDK
- 指向 `https://api.moonshot.cn/anthropic`
- 验证基础 `stream()` / `complete()` 路径可行

### Scenario 3: HTTPX-Thin Carrier Against Same Endpoint

目标：

- 使用 `httpx-thin`
- 指向同一端点
- 验证同一协议语义可以不依赖 official SDK 落地

### Scenario 4: Compare Carrier Behavior

目标：

- 对比两条路径在同一真实端点上的行为差异
- 至少比较：
  - 基础 completion
  - streaming
  - stop reason
  - 错误形态
  - cancellation

### Scenario 5: Aborted On Real Endpoint

目标：

- 在真实端点路径中触发取消
- 确认最终仍然映射到：
  - `aborted`

## Acceptance Criteria

如果以下判断都成立，就说明当前 adapter 设计方向基本可行：

1. top-level API -> registry -> adapter -> raw parts -> event stream 主链路可行
2. `anthropic-messages` 可通过真实 Kimi 兼容端点跑通
3. official SDK 路径可作为可选 carrier
4. `httpx-thin` 路径可作为独立可行 carrier
5. `complete()` / `complete_simple()` 不需要脱离 stream 根语义
6. cancellation 在真实端点路径中仍可稳定收敛为 `aborted`

## Decision After Spike

如果 spike 验证通过，下一步再继续：

1. 正式落 `anthropic-messages` 最小实现
2. 进入 `openai-compatible` 路径验证
3. 继续设计 raw part 内部类型体系
4. 继续设计 tool / thinking / image 事件矩阵

如果 spike 验证不通过，再回退并调整：

- adapter strategy
- carrier selection rule
- raw parts 边界
- cancellation 映射策略

## Run

建议至少执行：

```bash
python3 demo.py
python3 -m py_compile demo.py spike_ai_provider_adapters/*.py spike_ai_provider_adapters/adapters/*.py
```

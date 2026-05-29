# AI Provider Adapters Spike Results

## Scope

本文档记录 `spikes/ai-provider-adapters` 的实际验证结果。  
它只记录实验事实、观察和结论，不替代正式架构文档。

## Files

本次 spike 涉及的原型文件：

- `config.py`
- `types.py`
- `registry.py`
- `stream.py`
- `raw_parts.py`
- `assembler.py`
- `adapters/anthropic_sdk.py`
- `adapters/anthropic_httpx.py`
- `demo.py`

## Run Commands

执行过的命令：

```bash
python3 demo.py
python3 -m py_compile config.py types.py registry.py stream.py raw_parts.py assembler.py adapters/anthropic_sdk.py adapters/anthropic_httpx.py demo.py
./.venv/bin/python demo.py --mode mock
bash -ic '
cd /home/dev/workspace/loushang/spikes/ai-provider-adapters
export ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN:-$KIMI_API_KEY}
export ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-$KIMI_API_KEY}
./.venv/bin/python tsthttpx.py
'
bash -ic '
cd /home/dev/workspace/loushang/spikes/ai-provider-adapters
export ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN:-$KIMI_API_KEY}
export ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-$KIMI_API_KEY}
./.venv/bin/python tstsdk.py
'
```

## Scenario Results

### Scenario 1: Faux/Mock Path Still Works

结果：通过

观察：

- `stream()` 路径输出：
  - `start`
  - 多个 `text_delta`
  - `done`
- `complete()` 正常收敛最终 `AssistantMessage`
- `stream_simple()` 与 `complete_simple()` 同样通过
- 最终文本：
  - `mock hello from faux provider `
- 最终 `stop_reason`：
  - `stop`

结论：

- top-level API -> registry -> adapter -> event stream 主链路可行
- `complete()` / `complete_simple()` 建立在 stream 语义之上的方向可行

### Scenario 2: Anthropic SDK Carrier Against Kimi Endpoint

结果：通过

观察：

- endpoint：`https://api.moonshot.cn/anthropic`
- carrier：official `anthropic` SDK
- 事件序列：
  - `start`
  - 多个 `text_delta`
  - `done`
- 最终文本：
  - `Hello! I'm Kimi, developed by Moonshot AI.`
- 最终 `stop_reason`：
  - `stop`
- `error_message`：
  - `None`

结论：

- official `anthropic` SDK 可以作为 `anthropic-messages` 的可行 implementation carrier
- Kimi 的 Anthropic-compatible 端点可通过官方 SDK 路径真实跑通

### Scenario 3: HTTPX-Thin Carrier Against Same Endpoint

结果：通过

观察：

- endpoint：`https://api.moonshot.cn/anthropic`
- carrier：`httpx-thin`
- 事件序列：
  - `start`
  - 多个 `text_delta`
  - `done`
- 最终文本：
  - `Hello! This is Claude, made by Anthropic.`
- 最终 `stop_reason`：
  - `stop`
- `error_message`：
  - `None`

结论：

- `httpx-thin` 是真实可行的 carrier，而不只是理论 fallback
- Kimi 的 Anthropic-compatible 端点可通过薄 HTTP 路径真实跑通

### Scenario 4: Compare Carrier Behavior

结果：通过

观察：

- 两条 carrier 路径都能在同一真实端点上完成：
  - streaming
  - final message 收敛
- 两条路径的最终文本不同：
  - `httpx-thin` 返回 `Hello! This is Claude, made by Anthropic.`
  - official SDK 返回 `Hello! I'm Kimi, developed by Moonshot AI.`
- 两条路径都没有报错
- 两条路径最终 `stop_reason` 都为：
  - `stop`
- cancellation 尚未在真实端点路径中完成验证

结论：

- adapter strategy 中“同一协议族可由不同 implementation carrier 承载”的方向成立
- 当前差异主要体现在上游响应内容，不构成 carrier 不可行的证据

### Scenario 5: Aborted On Real Endpoint

结果：通过

观察：

- carrier：`httpx-thin`
- 事件序列：
  - `start`
  - 多个 `text_delta`
  - `error`
- 最终 `stop_reason`：
  - `aborted`
- 最终文本：
  - `Hello! This is Claude, made by Anth`
- `error_message`：
  - `aborted`

结论：

- 真实端点路径中的取消可以稳定映射到：
  - event stream `error(reason="aborted")`
  - final `AssistantMessage(stop_reason="aborted")`

## Issues Found

### Carrier Selection Issues

问题：

- 当前 shell 环境中的 key 放在 `.bashrc`
- `.bashrc` 开头对非交互 shell 直接 `return`
- 导致普通非交互命令默认读不到：
  - `ANTHROPIC_AUTH_TOKEN`
  - `ANTHROPIC_API_KEY`
  - `KIMI_API_KEY`

影响：

- 真实端点验证必须通过交互 shell 或显式导出环境变量执行
- 这属于实验环境问题，不是 adapter 设计本身的问题

### Protocol Compatibility Issues

问题：

- 当前只验证了最小 text path
- 尚未覆盖：
  - tool call
  - thinking
  - image
  - real-endpoint aborted path

影响：

- 目前只能确认最小 text streaming / completion 兼容成立
- 不能据此冻结完整事件矩阵结论

## Summary

本次 spike 支持以下判断：

1. top-level API -> registry -> adapter -> raw parts -> event stream 主链路可行
2. `anthropic-messages` 可以作为第一个真实协议验证入口
3. official `anthropic` SDK 与 `httpx-thin` 都是可行 carrier
4. `httpx-thin` 具备真实端点可行性，不只是设计兜底
5. 真实端点上的最小 text streaming / completion 路径已经跑通
6. 真实端点上的 cancellation -> `aborted` 协议映射已经跑通

## Limits

本次 spike 尚未验证：

- `openai-compatible`
- 多 provider family
- 完整 tool / thinking / image 事件矩阵
- 正式 oauth 设计
- 长时间运行下的严格性能与内存行为

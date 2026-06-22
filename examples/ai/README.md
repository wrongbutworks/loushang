`examples/ai` 面向上层开发者，展示 `loushang.ai` 根包公开 API 的常见调用路径。

推荐阅读顺序：

- [model_lookup.py](model_lookup.py)
  查看 provider、模型列表，并拿到正式模型句柄
- [provider_matrix.py](provider_matrix.py)
  查看新增 provider、endpoint、环境变量和上游模型 ID 映射
- [complete.py](complete.py)
  最常见的完整返回调用
- [stream.py](stream.py)
  流式消费事件并读取最终结果
- [06_reasoning.py](06_reasoning.py)
  离线演示 `stream_simple` 如何把 `SimpleCallOptions.reasoning` 映射到统一 reasoning 请求
- [09_errors_retry.py](09_errors_retry.py)
  离线演示稳定错误信息的序列化、脱敏，以及可见输出前的安全 retry
- [usage_online.py](usage_online.py)
  在线检查 usage；当 catalog 缺少价格事实时，cost 输出为 `{"known": false}`
- [tools.py](tools.py)
  工具调用和 `ToolResultMessage` 往返
- [03_typed_context.py](03_typed_context.py)
  显式 `Context` / `Tool` / `UserMessage` 类型构造

`examples/ai/advanced/` 放协议观察、faux provider、本地 registry 注入这类高级样例，不作为第一次接入的推荐入口。

- [advanced/inspect_endpoint_contract.py](advanced/inspect_endpoint_contract.py)
  查看 endpoint 默认 facts 和模型最终 resolved request 的 typed contract
- [advanced/custom_catalog.py](advanced/custom_catalog.py)
  从自定义 schema v2 catalog 读取 `upstreamId`，并查看最终 provider 请求绑定
- [advanced/normalization_diagnostics.py](advanced/normalization_diagnostics.py)
  离线查看 context/message 归一化产生的 repair、downgrade 和 signature-removal diagnostics；
  该示例显式启用 `pairing_mode="repair"` 以演示历史兼容修复
- [advanced/capability_failure.py](advanced/capability_failure.py)
  离线查看 stream/tools 等能力请求在 provider 调用前被统一校验和拒绝
- [advanced/cancel_stream.py](advanced/cancel_stream.py)
  离线演示 `asyncio.Event` 取消流式调用，并关闭上游 provider source
- [advanced/trace_events.py](advanced/trace_events.py)
  离线查看版本化 trace event、runtime retry 事件和敏感字段脱敏

## Provider 配置速查

模型调用使用三元组定位：`provider:endpoint:model`。如果上游模型 ID 自身包含冒号，内置 catalog 的公开 `model` ID 会把冒号替换为下划线，并在 `model.upstream_id` 保存真实上游 ID。自定义 schema v2 catalog 可直接写模型字段 `upstreamId`。

例如 OpenRouter 的上游模型 `openai/gpt-oss-120b:free` 在本地查询时写作：

```python
model = get_model("openrouter", "openai-completions", "openai/gpt-oss-120b_free")
```

常用新增 provider 的最小环境变量：

- `openrouter`: `OPENROUTER_API_KEY`
- `azure-openai-responses`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_BASE_URL`
- `cloudflare-ai-gateway`: `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID`
- `cloudflare-workers-ai`: `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`
- `mistral`: `MISTRAL_API_KEY`
- `google`: `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`
- `google-vertex`: `GOOGLE_VERTEX_ACCESS_TOKEN`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- `amazon-bedrock`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, 可选 `AWS_SESSION_TOKEN`

补充：

- [advanced/openai_codex_login.py](advanced/openai_codex_login.py)
  用于手工登录 `openai-codex` 并保存本地 credentials

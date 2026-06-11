`examples/ai` 面向上层开发者，展示 `loushang.ai` 根包公开 API 的常见调用路径。

推荐阅读顺序：

- [model_lookup.py](/home/chester/Workspace/ai/loushang/examples/ai/model_lookup.py)
  查看 provider、模型列表，并拿到正式模型句柄
- [provider_matrix.py](/home/chester/Workspace/ai/loushang/examples/ai/provider_matrix.py)
  查看新增 provider、endpoint、环境变量和上游模型 ID 映射
- [complete.py](/home/chester/Workspace/ai/loushang/examples/ai/complete.py)
  最常见的完整返回调用
- [stream.py](/home/chester/Workspace/ai/loushang/examples/ai/stream.py)
  流式消费事件并读取最终结果
- [tools.py](/home/chester/Workspace/ai/loushang/examples/ai/tools.py)
  工具调用和 `ToolResultMessage` 往返
- [typed_context.py](/home/chester/Workspace/ai/loushang/examples/ai/typed_context.py)
  显式 `Context` / `Tool` / `UserMessage` 类型构造

`examples/ai/advanced/` 放协议观察、faux provider、本地 registry 注入这类高级样例，不作为第一次接入的推荐入口。

## Provider 配置速查

模型调用使用三元组定位：`provider:endpoint:model`。如果上游模型 ID 自身包含冒号，内置 catalog 的公开 `model` ID 会把冒号替换为下划线，并在 `model.compat["upstreamModelId"]` 保存真实上游 ID。

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

- [advanced/openai_codex_login.py](/home/chester/Workspace/ai/loushang/examples/ai/advanced/openai_codex_login.py)
  用于手工登录 `openai-codex` 并保存本地 credentials

`examples/ai` 面向上层开发者，展示 `loushang.ai` 根包公开 API、公开 tool
校验辅助，以及自定义模型文件加载的常见调用路径。

顶层编号示例默认离线可运行，不需要真实厂商凭证：

- [01_complete.py](01_complete.py)
  完整返回调用，并读取最终 `AssistantMessage`
- [02_stream.py](02_stream.py)
  流式消费事件并读取最终结果
- [03_typed_context.py](03_typed_context.py)
  显式 `Context` / `Tool` / `UserMessage` 类型构造
- [04_tools.py](04_tools.py)
  工具调用、默认 strict 参数校验、显式 coerce diagnostics，以及 `ToolResultMessage` 往返
- [05_parallel_tools.py](05_parallel_tools.py)
  多个并行 tool call 的交错增量按 id/index 正确组装
- [06_reasoning.py](06_reasoning.py)
  `CallOptions.reasoning` 如何映射到统一 reasoning 请求
- [07_structured_output.py](07_structured_output.py)
  `StructuredOutputOptions`、provider payload 映射和 `complete_structured` 解析结果
- [08_image_input.py](08_image_input.py)
  用户图片输入和图片 tool result 回流到 provider context
- [09_errors_retry.py](09_errors_retry.py)
  稳定错误信息的序列化、脱敏，以及可见输出前的安全 retry
- [10_usage.py](10_usage.py)
  响应级 `Usage`，与账号级平台额度分开
- [11_provider_matrix.py](11_provider_matrix.py)
  查看内置 curated provider、endpoint、环境变量和模型入口
- [12_provider_smoke.py](12_provider_smoke.py)
  离线验证内置 curated provider 的默认模型句柄可解析
- [custom_model_file.py](custom_model_file.py)
  写入当前 `models.json` 形状的自定义模型文件，加载独立 registry，并查询自定义模型

需要真实凭据的调用单独放在未编号示例中，不进入离线 smoke：

- [chatgpt_coding_plan.py](chatgpt_coding_plan.py)
  通过 `loushang.ai.auth` 读取调用方已有的完整 `~/.codex/auth.json` 凭据，检查 access-token
  expiry，并将 bearer、account 和协议认证 header 完整转换为 `HeadersAuth`。该文件归
  Codex CLI 所有，示例不会刷新或写回；过期时先运行 `codex login`。

`examples/ai/advanced/` 放协议观察、faux provider、本地 registry 注入这类高级样例，不作为第一次接入的推荐入口。

- [advanced/inspect_endpoint_contract.py](advanced/inspect_endpoint_contract.py)
  查看 endpoint 默认 facts 和模型最终 resolved request 的 typed contract
- [advanced/custom_catalog.py](advanced/custom_catalog.py)
  从自定义模型文件读取 `upstreamId`，并查看最终 provider 请求绑定
- [advanced/normalization_diagnostics.py](advanced/normalization_diagnostics.py)
  离线查看 context/message 归一化产生的 repair、downgrade 和 signature-removal diagnostics；
  该示例显式启用 `pairing_mode="repair"` 以演示历史兼容修复
- [advanced/capability_failure.py](advanced/capability_failure.py)
  离线查看 stream/tools 等能力请求在 provider 调用前被统一校验和拒绝
- [advanced/cancel_stream.py](advanced/cancel_stream.py)
  离线演示 `asyncio.Event` 取消流式调用，并关闭上游 provider source
- [advanced/trace_events.py](advanced/trace_events.py)
  离线查看版本化 trace event、runtime retry 事件和敏感字段脱敏
- [advanced/platform_quota.py](advanced/platform_quota.py)
  离线查看现有 Moonshot/Kimi legacy contrib 的平台额度查询与输出
- [advanced/usage_online.py](advanced/usage_online.py)
  在线检查 usage；当 catalog 缺少价格事实时，cost 输出为 `{"known": false}`

## Provider 配置速查

模型调用使用三元组定位：`provider:endpoint:model`。内置 catalog 现在是小型 curated provider 集；更长尾的 provider/model 应通过当前 `models.json` 形状的自定义模型文件添加。

例如 Moonshot 默认 OpenAI-compatible route：

```python
model = get_model("moonshot", "openai-completions", "kimi-k2.6")
```

内置 curated provider 的最小环境变量：

- `anthropic`: `ANTHROPIC_API_KEY`
- `baidu-qianfan`: `QIANFAN_API_KEY` 或 `BAIDU_QIANFAN_API_KEY`
- `dashscope`: `DASHSCOPE_API_KEY`
- `deepseek`: `DEEPSEEK_API_KEY`
- `minimax`: `MINIMAX_API_KEY`
- `moonshot`: `MOONSHOT_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `stepfun`: `STEP_API_KEY` 或 `STEPFUN_API_KEY`
- `tencent-hunyuan`: `HUNYUAN_API_KEY`
- `volcano-ark`: `ARK_API_KEY`
- `zai`: `ZAI_API_KEY`

已有 ChatGPT Coding Plan 登录的真实调用：

```bash
uv run python examples/ai/chatgpt_coding_plan.py
```

该示例使用 `openai:openai-responses-chatgpt:gpt-5.5-chatgpt`，其上游模型 ID 是
`gpt-5.5`。ChatGPT 是凭据来源和
产品场景；请求仍由通用 `openai-responses` 协议 adapter 发送。

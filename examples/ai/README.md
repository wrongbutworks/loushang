`examples/ai` 面向上层开发者，展示 `loushang.ai` 根包公开 API 的常见调用路径。

推荐阅读顺序：

- [model_lookup.py](/home/chester/Workspace/ai/loushang/examples/ai/model_lookup.py)
  查看 provider、模型列表，并拿到正式模型句柄
- [complete.py](/home/chester/Workspace/ai/loushang/examples/ai/complete.py)
  最常见的完整返回调用
- [stream.py](/home/chester/Workspace/ai/loushang/examples/ai/stream.py)
  流式消费事件并读取最终结果
- [tools.py](/home/chester/Workspace/ai/loushang/examples/ai/tools.py)
  工具调用和 `ToolResultMessage` 往返
- [typed_context.py](/home/chester/Workspace/ai/loushang/examples/ai/typed_context.py)
  显式 `Context` / `Tool` / `UserMessage` 类型构造

`examples/ai/advanced/` 放协议观察、faux provider、本地 registry 注入这类高级样例，不作为第一次接入的推荐入口。

补充：

- [advanced/openai_codex_login.py](/home/chester/Workspace/ai/loushang/examples/ai/advanced/openai_codex_login.py)
  用于手工登录 `openai-codex` 并保存本地 credentials

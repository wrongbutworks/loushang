# AI SDK

[English](../../en/sdk/) | 中文

`loushang.ai` 是底层 AI SDK，不是 agent 编排层。

## 它提供什么

- 模型 registry 与模型查询。
- Provider 请求解析与兼容性处理。
- 统一的消息、工具和流式事件语义。
- Auth 解析。
- 具体 provider 实现。
- Usage 与成本估算 helper。

## 常见导入

```python
from loushang.ai import complete, stream, get_model, list_models
```

## 常见路径

建议按以下顺序阅读 [examples/ai](../../../examples/ai/) 中的可运行示例：

1. `model_lookup.py`
2. `complete.py`
3. `stream.py`
4. `tools.py`
5. `typed_context.py`

## 高级主题

当你需要 provider 注册、自定义 catalog、OAuth 支持、provider adapters 或 stream protocol 观察时，再使用高级 API。包内 README [src/loushang/ai/README.md](../../../src/loushang/ai/README.md) 包含更详细的内部 API 地图。

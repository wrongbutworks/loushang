# AI SDK

English | [中文](../../zh-CN/sdk/)

`loushang.ai` is the lower-level AI SDK. It is not the agent orchestration layer.

## What It Provides

- Model registry and model lookup.
- Provider request resolution and compatibility handling.
- Unified messages, tools, and streaming event semantics.
- Auth resolution.
- Concrete provider implementations.
- Usage and cost helpers.

## Common Imports

```python
from loushang.ai import complete, stream, get_model, list_models
```

## Common Paths

Read the runnable examples in [examples/ai](../../../examples/ai/) in this order:

1. `model_lookup.py`
2. `complete.py`
3. `stream.py`
4. `tools.py`
5. `03_typed_context.py`

## Advanced Topics

Use the advanced APIs when you need provider registration, custom catalogs, OAuth support, provider adapters, or stream protocol inspection. The package-level README at [src/loushang/ai/README.md](../../../src/loushang/ai/README.md) contains the detailed internal API map.

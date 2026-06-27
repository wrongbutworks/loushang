# AI SDK

English | [中文](../../zh-CN/sdk/)

`loushang.ai` is the low-level Python SDK for model calls. It owns model
lookup, provider request normalization, messages, tool-call payloads, streaming
events, auth material resolution, errors, usage, and provider adapters. It does
not own agent orchestration, session persistence, UI behavior, or coding-tool
policy.

## Public Surface

Use the root package for normal application code:

```python
from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    StructuredOutputOptions,
    TextPart,
    ImagePart,
    Tool,
    ToolResultMessage,
    complete,
    complete_structured,
    get_model,
    list_models,
    stream,
)
```

Use subpackages only when you need an advanced boundary:

- `loushang.ai.model` for custom model catalogs and registry inspection.
- `loushang.ai.auth` for OAuth credential storage and provider login helpers.
- `loushang.ai.advanced.registry` for provider registry wiring.
- `loushang.ai.contrib.openai_codex` for the optional OpenAI Codex integration.

### Session Hints And Prompt Caching

`CallOptions.session_id` is a best-effort session hint. Adapters that support
prompt cache keys or session/affinity headers may map it to provider-specific
request fields. Adapters that do not support those mechanisms ignore it instead
of failing the request.

Use `cache_retention="long"` only with endpoints that advertise long cache
retention support. Long retention remains a hard capability request and may fail
fast when the selected adapter does not support it.

## Models And Catalog

The built-in catalog is `models.json`. It intentionally contains a small
provider set instead of the archived full legacy catalog.

List and choose models by the local `provider:endpoint:model` tuple:

```python
from loushang.ai import get_model, list_models

for model in list_models(provider="moonshot", endpoint="openai-completions"):
    print(model.provider_id, model.endpoint_id, model.id)

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
```

Run [examples/ai/11_provider_matrix.py](../../../examples/ai/11_provider_matrix.py)
or [examples/ai/12_provider_smoke.py](../../../examples/ai/12_provider_smoke.py)
to inspect the current built-in provider set offline.

For local or long-tail providers, load a custom model file with the same shape
as `models.json` instead of expanding the built-in catalog. See
[examples/ai/custom_model_file.py](../../../examples/ai/custom_model_file.py) for
the common path and
[examples/ai/advanced/custom_catalog.py](../../../examples/ai/advanced/custom_catalog.py)
for request-binding inspection. Custom model files can set `upstreamId` when the
provider-facing model name differs from the local model id.

### Model File Format

Runtime model files use one shape and do not include `schemaVersion`:

```json
{
  "providers": {
    "company": {
      "displayName": "Company AI",
      "auth": {"apiKeyEnv": "COMPANY_AI_API_KEY"},
      "endpoints": {
        "openai-completions": {
          "api": "openai-completions",
          "baseUrl": "https://models.company.example/v1",
          "adapter": {
            "developerRole": false,
            "maxOutputTokensField": "max_completion_tokens",
            "reasoningFormat": "openai"
          },
          "models": {
            "company-chat": {
              "upstreamId": "vendor/company-chat-2026-06",
              "capabilities": {
                "input": ["text"],
                "output": ["text"],
                "stream": true,
                "toolUse": true
              }
            }
          }
        }
      }
    }
  }
}
```

Use `adapter` for protocol-specific request mapping. Do not use removed
`compat`, `protocol`, or `dialect` fields.

## Auth

The common path is API-key auth. Pass an explicit key through `CallOptions` or
set the provider environment variable declared by the catalog.

```python
from loushang.ai import CallOptions, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
options = CallOptions(api_key="...", max_output_tokens=512)
```

If `api_key` is omitted, `loushang.ai` resolves provider auth from the catalog
and environment. Curated provider examples:

| Provider | Main env vars |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `baidu-qianfan` | `QIANFAN_API_KEY`, `BAIDU_QIANFAN_API_KEY` |
| `dashscope` | `DASHSCOPE_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `minimax` | `MINIMAX_API_KEY` |
| `moonshot` | `MOONSHOT_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `stepfun` | `STEP_API_KEY`, `STEPFUN_API_KEY` |
| `tencent-hunyuan` | `HUNYUAN_API_KEY` |
| `volcano-ark` | `ARK_API_KEY` |
| `zai` | `ZAI_API_KEY` |

OAuth support is available through `loushang.ai.auth` and explicit contrib
integrations such as `openai-codex`. It is not required for the curated
API-key provider path.

## Complete Calls

The shortest path is `get_model(...)` followed by the root `complete(...)`
helper.

```python
from loushang.ai import CallOptions, complete, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
message = await complete(
    model,
    {"messages": [{"role": "user", "content": "Say hello in one sentence."}]},
    CallOptions(api_key="...", max_output_tokens=128),
)

print(message.stop_reason)
print("".join(part.text for part in message.content if part.type == "text"))
```

Runnable reference: [examples/ai/01_complete.py](../../../examples/ai/01_complete.py).

## Streaming

`stream(...)` returns an `AssistantMessageEventStream`. Iterate events first,
then call `result()` for the final `AssistantMessage`.

```python
from loushang.ai import CallOptions, get_model, stream

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
events = await stream(
    model,
    {"messages": [{"role": "user", "content": "Count to three."}]},
    CallOptions(api_key="..."),
)

async for event in events:
    if event["type"] == "text_delta":
        print(event["delta"], end="")

message = await events.result()
```

Runnable reference: [examples/ai/02_stream.py](../../../examples/ai/02_stream.py).

## Tools

`loushang.ai` defines tool schemas, validates tool arguments, carries tool-call
parts, and maps tool payloads to provider protocols. It does not execute tools
for you; the caller or agent layer executes `ToolCall` values and sends back
`ToolResultMessage` values.

```python
from loushang.ai import Tool

tools = [
    Tool(
        name="add",
        description="Return the sum of two numbers.",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )
]
```

Use strict validation by default; use the coercing validation helper only when
you want diagnostics for repaired user/tool input. Runnable references:
[examples/ai/04_tools.py](../../../examples/ai/04_tools.py) and
[examples/ai/05_parallel_tools.py](../../../examples/ai/05_parallel_tools.py).

## Reasoning

Use `ReasoningOptions` on `CallOptions` when the selected model supports
reasoning. The resolver checks model capabilities before the provider call.

```python
from loushang.ai import CallOptions, ReasoningOptions

options = CallOptions(
    api_key="...",
    reasoning=ReasoningOptions(enabled=True, effort="medium", expose_summary=True),
)
```

Runnable reasoning reference:
[examples/ai/06_reasoning.py](../../../examples/ai/06_reasoning.py).

## Structured Output

Use `StructuredOutputOptions` with `complete_structured(...)`. The SDK asks the
provider for structured output when the provider has a stable mapping, then
parses the final assistant text into `StructuredOutputResult`.

```python
from loushang.ai import (
    CallOptions,
    StructuredOutputOptions,
    complete_structured,
    get_model,
)

model = get_model("openai", "openai-responses", "gpt-5.4-mini")
result = await complete_structured(
    model,
    {"messages": [{"role": "user", "content": "Return a city and score."}]},
    StructuredOutputOptions(
        mode="json_schema",
        schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["city", "score"],
            "additionalProperties": False,
        },
    ),
    options=CallOptions(api_key="..."),
)

print(result.parsed)
```

Runnable reference:
[examples/ai/07_structured_output.py](../../../examples/ai/07_structured_output.py).

## Images

Use `ImagePart` in user messages or tool-result messages. The model must
declare image input support; unsupported image requests fail before the provider
call.

```python
from loushang.ai import ImagePart, TextPart, UserMessage

context = {
    "messages": [
        UserMessage(
            role="user",
            content=[
                TextPart(type="text", text="Describe this image."),
                ImagePart(type="image", data=image_base64, mime_type="image/png"),
            ],
            timestamp=0.0,
        )
    ]
}
```

Runnable reference:
[examples/ai/08_image_input.py](../../../examples/ai/08_image_input.py).

## Errors And Retry

Provider, validation, capability, timeout, cancellation, and stream failures are
normalized as `AIError` subclasses. The stable JSON-safe payload is available
through `error.to_dict()`, with credentials and tokens redacted.

```python
from loushang.ai import AIError, CallOptions, RetryOptions, complete

try:
    message = await complete(
        model,
        {"messages": [{"role": "user", "content": "hello"}]},
        CallOptions(api_key="...", retry=RetryOptions(max_attempts=2)),
    )
except AIError as error:
    print(error.to_dict())
```

Retries are only safe before visible output is emitted. Runnable reference:
[examples/ai/09_errors_retry.py](../../../examples/ai/09_errors_retry.py).

## Usage And Cost

Final `AssistantMessage.usage` is response-level `Usage`. Cost is
`None` when the catalog does not have trusted pricing facts.

```python
usage = message.usage
print(usage.input, usage.output, usage.total_tokens, usage.cost)
```

Account or platform quota is separate from response usage. Moonshot/Kimi quota
helpers live in `loushang.ai.contrib.moonshot`. Runnable references:
[examples/ai/10_usage.py](../../../examples/ai/10_usage.py),
[examples/ai/advanced/usage_online.py](../../../examples/ai/advanced/usage_online.py), and
[examples/ai/advanced/platform_quota.py](../../../examples/ai/advanced/platform_quota.py).

## Example Index

Recommended reading order:

1. [01_complete.py](../../../examples/ai/01_complete.py)
2. [02_stream.py](../../../examples/ai/02_stream.py)
3. [03_typed_context.py](../../../examples/ai/03_typed_context.py)
4. [04_tools.py](../../../examples/ai/04_tools.py)
5. [05_parallel_tools.py](../../../examples/ai/05_parallel_tools.py)
6. [06_reasoning.py](../../../examples/ai/06_reasoning.py)
7. [07_structured_output.py](../../../examples/ai/07_structured_output.py)
8. [08_image_input.py](../../../examples/ai/08_image_input.py)
9. [09_errors_retry.py](../../../examples/ai/09_errors_retry.py)
10. [10_usage.py](../../../examples/ai/10_usage.py)
11. [11_provider_matrix.py](../../../examples/ai/11_provider_matrix.py)
12. [12_provider_smoke.py](../../../examples/ai/12_provider_smoke.py)
13. [custom_model_file.py](../../../examples/ai/custom_model_file.py)

Advanced examples live under
[examples/ai/advanced](../../../examples/ai/advanced/).

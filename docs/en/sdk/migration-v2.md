# AI SDK v2 Migration Guide

[中文](../../zh-CN/sdk/migration-v2.md) | English

This guide covers the migration from the legacy AI package shape to the curated
v2 SDK surface. It focuses on the supported public path, catalog migration,
error semantics, and provider-boundary changes.

## What Changed

The v2 SDK keeps `loushang.ai` as a low-level model-call package. It does not
own agent loops, sessions, UI behavior, RAG, MCP orchestration, or product
configuration.

The main changes are:

- The built-in catalog is now `models.json`.
- The legacy full catalog is archived for audit only.
- Normal application code should import from the root `loushang.ai` package.
- Provider-specific options and provider registry wiring moved behind advanced
  or contrib boundaries.
- Errors are normalized into `AIError` subclasses and stable JSON-safe payloads.
- Core builtin adapters are protocol adapters, not one adapter per vendor.
- OpenAI Codex moved to explicit `loushang.ai.contrib.openai_codex` registration.

## Catalog Migration

### Legacy Built-In Catalog

Before v2, code could depend on the broad built-in `models.json` catalog and on
provider facts that were not equally verified.

In v2, the runtime package data uses the curated catalog:

```text
src/loushang/ai/model/models.json
```

The previous full catalog remains available only as a compressed audit archive:

```text
backup/ai/models-legacy-full.json.gz
```

Use the archive for inspection or manual recovery. Do not restore it into the
runtime package path.

### Choosing Models

Use the local `provider:endpoint:model` tuple:

```python
from loushang.ai import get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
```

When the provider-facing model name differs from the local model id, express
that in a custom catalog through `upstreamId`. Providers send
`ResolvedRequest.upstream_model_id` when present and fall back to `model.id`
otherwise.

### Long-Tail Providers

Do not expand the built-in catalog for local deployments, private endpoints, or
long-tail providers. Load a custom schema v2 catalog instead:

```python
from loushang.ai.model import load_model_registry_from_file

registry = load_model_registry_from_file("local-models.json")
model = registry.get_model("local", "openai-completions", "my-model")
```

Runnable reference:
[examples/ai/advanced/custom_catalog.py](../../../examples/ai/advanced/custom_catalog.py).

## Root API Migration

Normal application code should use root exports:

```python
from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    StructuredOutputOptions,
    complete,
    complete_structured,
    get_model,
    list_models,
    stream,
)
```

The old broad root surface has been narrowed. These names are intentionally not
root exports:

| Old access pattern | v2 path |
|---|---|
| `loushang.ai.ModelCallOptions` | `loushang.ai.options.ModelCallOptions`, compatibility alias for `CallOptions` |
| `loushang.ai.StreamOptions` | `loushang.ai.options.StreamOptions`, compatibility alias for `CallOptions` |
| `loushang.ai.AnthropicOptions` | `loushang.ai.advanced.AnthropicOptions` |
| `loushang.ai.OpenAICompletionsOptions` | `loushang.ai.advanced.OpenAICompletionsOptions` |
| `loushang.ai.OpenAIResponsesOptions` | `loushang.ai.advanced.OpenAIResponsesOptions` |
| `loushang.ai.ApiProviderRegistry` | `loushang.ai.advanced.registry.ApiProviderRegistry` |
| `loushang.ai.OpenAICodexResponsesOptions` | `loushang.ai.contrib.openai_codex.OpenAICodexResponsesOptions` |

Use `CallOptions` for provider-neutral calls:

```python
from loushang.ai import CallOptions, get_model

model = get_model("openai", "openai-responses", "gpt-5.4-mini")
message = await model.complete(
    {"messages": [{"role": "user", "content": "Say hello."}]},
    CallOptions(api_key="...", max_output_tokens=128),
)
```

Provider-specific option classes remain available for compatibility and advanced
protocol controls. They are no longer the recommended first import for normal
application code.

## Error Migration

Do not catch provider SDK exceptions as the public contract. Catch `AIError` or
one of its subclasses:

```python
from loushang.ai import AIError, CallOptions

try:
    message = await model.complete(
        {"messages": [{"role": "user", "content": "hello"}]},
        CallOptions(api_key="..."),
    )
except AIError as error:
    payload = error.to_dict()
    print(payload["code"], payload["retryable"], payload["statusCode"])
```

The stable error payload contains:

| Field | Meaning |
|---|---|
| `code` | Stable SDK error code such as `authentication`, `rate_limit`, `timeout`, or `unsupported_capability` |
| `message` | User-facing error message |
| `source` | `loushang.ai`, `provider`, or the protocol source that produced the error |
| `retryable` | Whether the SDK considers retry safe for this failure |
| `provider` / `endpoint` / `model` | Resolved model identity when available |
| `statusCode` | HTTP status code when the provider reported one |
| `requestId` | Provider request id when available |
| `details` | JSON-safe details with secrets and tokens redacted |

`complete()` and `event_stream.result()` raise typed errors for terminal error
events. Retry is only attempted before visible output is emitted.

## Provider Boundary Migration

Core builtin adapters are now protocol-level adapters:

| Protocol API | Core adapter |
|---|---|
| `anthropic-messages` | `loushang.ai.providers.anthropic.AnthropicProvider` |
| `openai-completions` | `loushang.ai.providers.openai_completions.OpenAICompletionsProvider` |
| `openai-responses` | `loushang.ai.providers.openai_responses.OpenAIResponsesProvider` |

Azure OpenAI and Amazon Bedrock are not core adapters in v2. Use a custom
catalog with an existing compatible protocol when that is enough, or register an
external/contrib adapter explicitly.

OpenAI Codex is an explicit contrib integration:

```python
from loushang.ai import get_model
from loushang.ai.contrib.openai_codex import register_openai_codex_contrib

register_openai_codex_contrib()
model = get_model("openai-codex", "openai-codex-responses", "gpt-5.3-codex")
```

Runnable reference:
[examples/ai/advanced/openai_codex_contrib.py](../../../examples/ai/advanced/openai_codex_contrib.py).

## Validation After Migration

Run the same gates used by the AI package:

```bash
make check-ai
uv run pytest tests/examples/test_ai_examples.py -q
uv run python scripts/ai/check_catalog.py
uv run python scripts/ai/check_examples.py
uv run python scripts/ai/check_import_boundaries.py
```

Live provider smoke tests require valid provider credentials and should be
recorded in the matching provider evidence file. Offline gates must not be used
to claim live provider compatibility.

Internal release readiness is tracked in
[Final Scorecard](../../internals/architecture/ai/final-scorecard.md).

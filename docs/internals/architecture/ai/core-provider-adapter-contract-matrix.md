# Core Provider Adapter Contract Matrix

`loushang.ai` ships only protocol-level production adapters. Product and account
scenarios reuse them through model catalog routes; product-specific adapters do
not belong in the package.

## Production Adapters

| API | Module | Adapter | Protocol Boundary |
|---|---|---|---|
| `anthropic-messages` | `loushang.ai.providers.anthropic` | `AnthropicProvider` | Anthropic Messages |
| `openai-completions` | `loushang.ai.providers.openai_completions` | `OpenAICompletionsProvider` | OpenAI-compatible Chat Completions |
| `openai-responses` | `loushang.ai.providers.openai_responses` | `OpenAIResponsesProvider` | OpenAI Responses |

These are the only adapters registered by `register_builtin_ai_providers`.
All providers must implement `ApiProvider` (`api` plus `invoke_raw(request)`).
Providers that own non-core adapter config may additionally implement
`ProviderRequestValidator.validate_request(request)`, which is checked at
registration and runs before `invoke_raw(request)`.

## Core Support Modules

| Module | Role |
|---|---|
| `loushang.ai.providers.anthropic_base` | Shared Anthropic request helpers |
| `loushang.ai.providers.anthropic_oauth_compat` | Anthropic OAuth compatibility payload helpers |
| `loushang.ai.providers.openai_responses_shared` | Shared OpenAI Responses conversion and stream parsing |
| `loushang.ai.providers.provider_helpers` | Shared provider runtime helpers |

## Test-Only

| Module | Boundary |
|---|---|
| `loushang.ai.providers.faux` | Test/example-only adapter; not builtin |

Core does not ship Azure OpenAI or Amazon Bedrock adapters in this version.

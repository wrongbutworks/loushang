# Core Provider Adapter Contract Matrix

`loushang.ai` core ships only protocol-level production adapters. Provider-specific
or account-specific integrations must live in `contrib` or an external package.

## Production Adapters

| API | Module | Adapter | Protocol Boundary |
|---|---|---|---|
| `anthropic-messages` | `loushang.ai.providers.anthropic` | `AnthropicProvider` | Anthropic Messages |
| `openai-completions` | `loushang.ai.providers.openai_completions` | `OpenAICompletionsProvider` | OpenAI-compatible Chat Completions |
| `openai-responses` | `loushang.ai.providers.openai_responses` | `OpenAIResponsesProvider` | OpenAI Responses |

These are the only adapters registered by `register_builtin_ai_providers`.

## Core Support Modules

| Module | Role |
|---|---|
| `loushang.ai.providers.anthropic_base` | Shared Anthropic request helpers |
| `loushang.ai.providers.anthropic_oauth_compat` | Anthropic OAuth compatibility payload helpers |
| `loushang.ai.providers.openai_responses_shared` | Shared OpenAI Responses conversion and stream parsing |
| `loushang.ai.providers.provider_helpers` | Shared provider runtime helpers |

## Test-Only And Contrib

| Module | Boundary |
|---|---|
| `loushang.ai.providers.faux` | Test/example-only adapter; not builtin |
| `loushang.ai.contrib.openai_codex` | Explicit contrib registration; not builtin |

Core does not ship Azure OpenAI or Amazon Bedrock adapters in this version.

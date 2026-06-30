# Loushang AI Top-Level API Signatures

## Status

Current AIF-009 contract.

This document supersedes the earlier four-entrypoint design that mirrored the reference AI SDK `streamSimple` / `completeSimple` APIs. The current Python root API intentionally keeps only the two invocation entrypoints and one canonical options object.

## Scope

This document records the current public signature boundary for:

- `stream()`
- `complete()`
- cancellation
- provider registry handoff
- provider/contrib-specific options boundaries

It does not define provider payload mapping, raw parts, tool orchestration, or provider-specific option types.

## Current Public Entrypoints

```python
async def stream(
    model: Model,
    context: Context | Mapping[str, object],
    options: CallOptions | None = None,
    *,
    provider_registry: ApiProviderRegistry | None = None,
) -> AssistantMessageEventStream: ...


async def complete(
    model: Model,
    context: Context | Mapping[str, object],
    options: CallOptions | None = None,
    *,
    provider_registry: ApiProviderRegistry | None = None,
) -> AssistantMessage: ...
```

The stable public facts are:

1. The root invocation shape is `model + context + options`.
2. `options` is `CallOptions | None`; arbitrary legacy option-shaped objects are rejected.
3. `provider_registry` names the provider adapter registry explicitly and avoids confusion with `ModelRegistry`.
4. `stream()` returns `AssistantMessageEventStream`.
5. `complete()` returns `AssistantMessage`.

## Removed Simple Entrypoints

The root package no longer exposes:

- `stream_simple()`
- `complete_simple()`
- `SimpleCallOptions`
- `SimpleStreamOptions`
- `simple_options_to_call_options()`

Reasoning and thinking controls are expressed by `CallOptions.reasoning: ReasoningOptions | None`. There is no separate simple-call projection layer.

## Options Boundary

The root API consumes a single core options type:

```python
CallOptions(
    cancellation=None,
    auth=None,
    cache_retention=None,
    session_id=None,
    max_output_tokens=None,
    temperature=None,
    timeout=None,
    retry=None,
    trace=None,
    region=None,
    pairing_mode="strict",
    reasoning=None,
    tool_choice=None,
    output=None,
)
```

`auth` is the only request-level credential input. It accepts
`ApiKeyAuth`, `OAuthBearerAuth`, `NoAuth`, or `HeadersAuth`. OAuth login,
refresh, credential storage, provider registries, and env-oauth helpers live
outside `loushang.ai` in the top-level `loushang.auth` package.

Provider/contrib-specific options do not enter the root `loushang.ai` public surface. For example, Codex transport options belong to `loushang.ai.contrib.openai_codex.OpenAICodexResponsesOptions` and are consumed only by that contrib provider.

## Cancellation

Cancellation enters through `CallOptions.cancellation`.

The public contract is a minimal cancellation signal object, not a JavaScript `AbortSignal` clone and not a legacy `signal` alias. The API and runtime may check cancellation before provider invocation, during streaming iteration, and before final result convergence.

Detected cancellation should converge to the protocol-level `aborted` stop reason or a typed AI error; raw runtime cancellation details should not leak as the public AI contract.

## Provider Handoff

The top-level API resolves the provider once from the model API and invokes the selected adapter through the provider boundary:

```text
complete() / stream()
    -> normalize_context_result()
    -> validate model capabilities
    -> resolve auth
    -> build ProviderRequest
    -> provider_registry.get(model.api)
    -> provider.invoke_raw(request)
```

`complete()` and `stream()` share this path. The difference is the `ProviderRequest.mode` value and the model capability gate: `stream()` requires stream capability, while `complete()` does not.

## Design Consequences

- There is no root provider-specific options family.
- There is no root simple-options family.
- There is no model instance invocation facade.
- Unsupported explicit parameters fail before provider invocation instead of being silently ignored.
- Contrib providers may define their own option types, but core adapters should consume only `CallOptions` and `ProviderRequest`.

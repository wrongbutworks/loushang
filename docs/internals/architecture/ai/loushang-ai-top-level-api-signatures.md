# Loushang AI Top-Level API Signatures

## Status

Current AIF-009 contract.

This document supersedes the earlier four-entrypoint design that mirrored the reference AI SDK `streamSimple` / `completeSimple` APIs. The current Python root API intentionally keeps three invocation entrypoints and one canonical options object.

## Scope

This document records the current public signature boundary for:

- `stream()`
- `complete()`
- `complete_structured()`
- cancellation
- provider registry handoff
- provider-specific options boundaries

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


async def complete_structured(
    model: Model,
    context: Context | Mapping[str, object],
    output: StructuredOutputOptions | None = None,
    *,
    options: CallOptions | None = None,
    provider_registry: ApiProviderRegistry | None = None,
) -> StructuredOutputResult: ...
```

The stable public facts are:

1. The root invocation shape is `model + context + options`.
2. `options` is `CallOptions | None`; arbitrary legacy option-shaped objects are rejected.
3. `provider_registry` names the provider adapter registry explicitly and avoids confusion with `ModelRegistry`.
4. `stream()` returns `AssistantMessageEventStream`.
5. `complete()` returns `AssistantMessage`.
6. `complete_structured()` returns `StructuredOutputResult` after parsing the `complete()` result against explicit structured-output options.

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
    api_key=None,
    oauth_credentials=None,
    headers={},
    cache_retention=None,
    cache_key=None,
    max_output_tokens=None,
    temperature=None,
    timeout=None,
    retry=None,
    trace=None,
    pairing_mode="strict",
    reasoning=None,
    tool_choice=None,
    output=None,
)
```

`auth` 仅为现有调用方保留 request-level 兼容；新的调用不再构造通用 auth
union，而是使用明确的 `api_key`、`oauth_credentials` 或 `headers` 字段。

`oauth_credentials` is a single explicit `loushang.auth.OAuthCredentials` value
for this request. Request-specific supplemental headers use `CallOptions.headers`
instead of expanding the credential DTO. API-key defaults still come from
`models.json.auth`. OAuth login, refresh, credential storage, and account selection
are outside `loushang.ai`.
Provider-specific option classes do not enter the root public surface.

`cache_key` is an opaque caller-provided cache/affinity key. Protocol adapters
may map it to provider-specific request fields or headers, but it is not a
Loushang session identifier. `CallOptions` contains no endpoint-selection or
region-routing input.

## Cancellation

Cancellation enters through `CallOptions.cancellation`.

The public contract is a minimal cancellation signal object, not a JavaScript `AbortSignal` clone and not a legacy `signal` alias. The API and runtime may check cancellation before provider invocation, during streaming iteration, and before final result convergence.

Detected cancellation should converge to the protocol-level `aborted` stop reason or a typed AI error; raw runtime cancellation details should not leak as the public AI contract.

## Provider Handoff

The top-level API accepts one already selected concrete model and invokes the
adapter named by that model's API:

```text
complete() / stream()
    -> resolve auth and per-call defaults from the selected model
    -> build ProviderRequest(model=the selected model)
    -> normalize_context_result(request.model)
    -> validate request.model capabilities
    -> provider_registry.get(request.model.api)
    -> provider.invoke_raw(request)
```

Invocation does not consult a model registry, select a preferred endpoint,
switch regions, or replace `ProviderRequest.model`.

`complete()` and `stream()` share this path. The difference is the `ProviderRequest.mode` value and the model capability gate: `stream()` requires stream capability, while `complete()` does not.

`complete_structured()` reuses `complete()` with `StructuredOutputOptions`, then parses the returned message into `StructuredOutputResult`; it does not add another provider invocation path.

## Design Consequences

- There is no root provider-specific options family.
- There is no root simple-options family.
- There is no model instance invocation facade.
- Unsupported explicit parameters fail before provider invocation instead of being silently ignored.
- Custom providers may define their own option types, but core adapters should consume only `CallOptions` and `ProviderRequest`.

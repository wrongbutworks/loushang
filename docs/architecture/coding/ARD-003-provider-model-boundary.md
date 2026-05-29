# ARD-003: Provider And Model Boundary

## Status

Accepted

## Context

`loushang-coding` needs to support extension-side provider registration while reusing
`loushang-ai` as the authoritative AI substrate.

`loushang-ai` already has a structured provider/model configuration system:

- `Provider`
- `Endpoint`
- `Model`
- endpoint-level `auth`, `compat`, and `defaults`
- model-level `compat` and `defaults`
- `models.json` as the structured provider/endpoint/model registry source

`pi-coding-agent` exposes a convenient `registerProvider(name, config)` API with a
flatter provider config shape. That shape is not the right internal model for
`loushang`. Blindly flattening provider configuration into the `pi` shape would
weaken `loushang-ai` and make multi-endpoint or endpoint-specific behavior harder
to preserve.

At the same time, a dict-based API can still be useful for extensions because it is
easy to serialize, load, and construct dynamically.

## Decision

### 1. `loushang-ai` owns the canonical provider/model model

`loushang-coding` treats the `loushang-ai` `Provider -> Endpoint -> Model` graph as
the canonical internal representation.

The canonical configuration source remains `loushang-ai` model configuration,
including `models.json` and any registry loaders that produce `Provider`,
`Endpoint`, and `Model` objects.

### 2. Dict input is allowed, but it is loushang-native

`ExtensionAPI.register_provider(name, config)` may accept a dict, but that dict is
a loushang-native provider config shape, not a pi-style flat provider config.

The dict schema should be aligned with `loushang-ai.models.json` and the
`Provider -> Endpoint -> Model` graph:

- provider-level display metadata maps to `Provider`
- `endpoints` maps to one or more `Endpoint` objects
- endpoint-level `api`, `baseUrl`, `auth`, `authOverride`, `compat`, and
  `defaults` remain endpoint concerns
- endpoint `models` map to `Model` objects
- model-level `displayName`, capabilities, pricing, `compat`, and `defaults`
  remain model concerns

A dict is a convenient serialization/configuration entry point. It is not a
promise to support pi's flat `registerProvider` config.

### 3. Native `Provider` input is the preferred typed path

If an extension can construct native objects, it should pass a `Provider` object.

Native `Provider` input bypasses dict parsing and is registered as loushang-native
configuration.

### 4. Provider/model registration is separate from API stream and OAuth registration

Provider/model config should not become a mixed bag for model registry, streaming
transport, and login behavior.

These concerns should remain separate:

- model registry: `Provider -> Endpoint -> Model`
- API stream provider: explicit API provider registration
- OAuth provider: explicit OAuth provider registration

If a future convenience API groups these concerns, it should still preserve these
separate internal registrations and should not define provider/model config as a
pi-style flat dict.

### 5. Align provider lifecycle semantics, not pi's provider config shape

`loushang-coding` may align high-level extension lifecycle behavior:

- load-time pending registration
- bound-runtime immediate registration
- unregister cleanup by extension source
- replacement/override behavior where it is meaningful for loushang-native
  provider data

This alignment is limited to externally observable lifecycle semantics.

It must not require changing `loushang-ai` `models.json`, `Provider`, `Endpoint`,
`Model`, model registry loaders, or request-resolution semantics into pi's flatter
shape.

### 6. Pi compatibility, if needed, belongs in a separate adapter

If direct pi extension migration becomes a requirement, pi-style flat provider
config should be parsed by an explicit compatibility adapter, not by the core
`ExtensionAPI.register_provider()` path.

That adapter may translate pi-style config into loushang-native provider, API
provider, and OAuth provider registrations.

## Consequences

- `loushang-ai` remains independently useful and more expressive than pi's
  provider config.
- Extension provider dicts remain possible, but their schema follows loushang,
  not pi.
- Provider/model, API stream provider, and OAuth provider responsibilities stay
  separated.
- Future provider work should be evaluated against this boundary before adding
  more pi-style fields to core extension APIs.

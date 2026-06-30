# loushang.ai Auth Boundary: Defaults and Explicit Overrides

## Purpose

This document defines the target auth boundary for `loushang.ai`.

The design is architectural guidance, not an implementation plan. It keeps
`loushang.ai` auth simple, passive, and explainable:

```text
loushang.ai only decides which auth material this provider request carries.
```

It must not grow into an OAuth framework, account system, credential store,
Provider control-plane, or quota/billing layer.

## Core Position

Auth is split into two layers:

```text
models.json.auth
  default auth declaration / default auth behavior / diagnostic metadata

CallOptions.auth
  explicit request-level auth input / per-call override
```

The relationship is:

```text
If CallOptions.auth is provided:
  use CallOptions.auth.

If CallOptions.auth is not provided:
  use models.json.auth default behavior.
```

Therefore:

```text
models.json.auth is not the strong validator for call-time auth.
CallOptions.auth is the explicit auth intent for this request and has
highest priority.
```

## Goals

1. Keep auth responsibility narrow: resolve request credentials into provider
   request headers and metadata.
2. Prefer explicit request intent over static catalog declarations.
3. Let API key models use environment variable fallback when no explicit auth is
   supplied.
4. Require OAuth access tokens to come from the caller, never from implicit
   local state.
5. Keep secrets out of catalog model objects, logs, errors, and traces.
6. Preserve room for strict catalog validation without making strict validation
   the default runtime behavior.

## Non-Goals

`loushang.ai` auth does not cover:

| Non-goal | Boundary |
|---|---|
| OAuth login | No authorization URL flow, browser redirect, callback server, or code exchange |
| OAuth refresh | No refresh token handling, automatic access token refresh, or retry-after-refresh |
| Credential persistence | No credential store, local file database, encrypted store, or keychain ownership |
| Multi-account management | No user account, Provider account, organization, or profile selection |
| Provider account control-plane | No quota, billing, subscription, account profile, or entitlement lookup |
| Product-level auth policy | No model routing based on quota, user state, plan, or account policy |
| Tool auth | No business-system auth for upper-layer tool calls |
| Session auth state | No long-lived auth state inside `loushang.ai` sessions |
| contrib/provider exceptions | `contrib` must not become the place where account, quota, or OAuth lifecycle semantics leak into core auth |

In short:

```text
loushang.ai handles how this model request carries auth.
Upper layers handle how users obtain, store, refresh, select, and manage auth.
```

## Design Principles

### Explicit Auth Wins

`CallOptions.auth` is closer to the real request than `models.json`. It may
represent:

- a caller-selected credential;
- a private deployment or gateway override;
- a test environment credential;
- a new Provider auth shape not yet represented in the catalog;
- an intentional no-auth call.

For that reason, ordinary runtime behavior must honor explicit auth even if it
does not match the catalog's declared `auth.kind`.

### Defaults Apply Only When Auth Is Omitted

`models.json.auth` participates in auth resolution only when:

```python
CallOptions.auth is None
```

Default behavior by declaration kind:

| `models.json.auth.kind` | Default behavior |
|---|---|
| `api_key` | Read an API key or static request credential from configured environment variables |
| `oauth` | Fail with missing auth and ask the caller to provide explicit OAuth auth |
| `none` | Send no auth |
| not configured | Treat as missing default auth configuration unless the model is explicitly classified as no-auth elsewhere |

### Runtime Does Not Strongly Block Type Mismatches

Ordinary runtime should not fail only because `models.json.auth.kind` differs
from the explicit auth type.

Example:

```text
models.json.auth.kind = oauth
CallOptions.auth = ApiKeyAuth(...)
```

Ordinary runtime meaning:

```text
The caller explicitly overrode auth for this request. Use CallOptions.auth.
```

This can produce a diagnostic, but it should not be a default runtime blocker.
Strict checks belong in tests, CI, catalog validation, or debug/diagnose modes.

### `auth=None` and `NoAuth` Are Different

| Input | Meaning |
|---|---|
| `auth=None` | Caller did not specify auth; use model default auth logic |
| `auth=NoAuth()` | Caller explicitly says this request sends no auth |

Example:

```python
await complete(model, context)
```

means:

```text
No explicit auth. Resolve auth from models.json.auth defaults.
```

This is different from:

```python
await complete(
    model,
    context,
    options=CallOptions(auth=NoAuth()),
)
```

which means:

```text
Explicit request-level no-auth override.
```

## Core Concepts

The auth model has four concepts:

```text
AuthDeclaration / AuthConfig
  ↓
AuthCredential
  ↓
AuthResolver
  ↓
AuthView
```

### AuthDeclaration / AuthConfig

Source: `models.json.auth`.

This is a default auth declaration, not a real credential. It describes:

- default auth kind;
- environment variables for API key fallback;
- header name;
- header prefix;
- fixed supplemental headers if needed;
- diagnostics and developer-facing auth requirements;
- redaction hints.

Example:

```json
{
  "auth": {
    "kind": "api_key",
    "apiKeyEnvs": ["MOONSHOT_API_KEY"],
    "header": "Authorization",
    "prefix": "Bearer "
  }
}
```

Meaning:

```text
If no explicit auth is supplied, read MOONSHOT_API_KEY and send
Authorization: Bearer <value>.
```

OAuth declaration example:

```json
{
  "auth": {
    "kind": "oauth",
    "header": "Authorization",
    "prefix": "Bearer "
  }
}
```

Meaning:

```text
This model defaults to OAuth bearer auth, but loushang.ai will not obtain the
token. The caller must supply explicit CallOptions.auth.
```

No-auth declaration:

```json
{
  "auth": {
    "kind": "none"
  }
}
```

### AuthCredential

Source: `CallOptions.auth`.

This is the explicit auth input for this request. Recommended credential types:

| Type | Purpose |
|---|---|
| `ApiKeyAuth` | Explicit API key or static request credential |
| `OAuthBearerAuth` | Explicit OAuth access token |
| `NoAuth` | Explicitly send no auth |
| `HeadersAuth` | Explicit complete auth headers as a low-level escape hatch |

### AuthResolver

Internal concept.

When no explicit auth is supplied and the model declares API key default auth,
an environment resolver can read the first available configured environment
variable:

```text
EnvApiKeyResolver
```

Important invariant:

```text
get_model does not read real secrets.
complete / stream read secrets immediately before building the provider request.
```

This prevents secrets from being attached to long-lived `Model` objects.

### AuthView

The resolved result consumed by provider request construction:

```python
AuthView(
    headers={
        "Authorization": "Bearer <redacted>"
    }
)
```

`AuthView` is a resolution result, not a primary public construction API.

## `models.json.auth` Positioning

`models.json.auth` answers:

```text
If the caller did not provide explicit auth, how should this model authenticate?
```

It is useful for:

| Use | Description |
|---|---|
| API key default construction | Build API key auth from env when no explicit auth is passed |
| OAuth default failure | Explain that OAuth must be provided explicitly |
| No-auth default | Declare that the model normally sends no auth |
| Header/prefix defaults | Provide header construction hints for compatible explicit auth |
| Diagnostics | Produce clear missing-auth messages |
| Documentation/introspection | Let upper layers show default auth requirements |
| Redaction hints | Help identify sensitive headers and fields |

It must not:

```text
strongly validate or block call-time auth in ordinary runtime;
save real secrets;
perform OAuth login;
perform OAuth refresh;
read a credential store;
manage Provider accounts;
query quota or billing.
```

## `CallOptions.auth` Positioning

`CallOptions.auth` answers:

```text
What auth should this request actually carry?
```

It has highest priority. When present, ordinary runtime uses it. At that point
`models.json.auth` can still provide:

- header and prefix hints;
- diagnostics;
- redaction hints;
- documentation context.

It should not silently override the caller's explicit intent.

## Auth Kinds

### `api_key`

`api_key` means a broad static request credential, not only a literal API key.
It can cover:

```text
OpenAI API key
Anthropic API key
Moonshot API key
DashScope API key
static bearer token
x-api-key token
private service static access token
long-lived provider token
```

The defining traits are:

```text
relatively static;
does not require OAuth login;
does not require refresh by loushang.ai;
usually comes from env or an upper-layer secret system;
not tied to a single interactive user authorization flow.
```

This can express common shapes with `api_key + header + prefix + env`:

```json
{
  "auth": {
    "kind": "api_key",
    "apiKeyEnvs": ["PRIVATE_MODEL_TOKEN"],
    "header": "Authorization",
    "prefix": "Bearer "
  }
}
```

```json
{
  "auth": {
    "kind": "api_key",
    "apiKeyEnvs": ["PRIVATE_MODEL_API_KEY"],
    "header": "x-api-key",
    "prefix": ""
  }
}
```

The current design does not need separate `static_token`, `bearer_token`, or
`custom_static_token` kinds.

### `oauth`

`oauth` means:

```text
This model defaults to requiring an OAuth access token.
```

`loushang.ai` does not obtain that token. OAuth declaration value:

1. declares that default auth cannot be automatic;
2. fails early when no explicit `CallOptions.auth` is supplied;
3. provides default header/prefix hints;
4. gives upper layers, docs, CLIs, and management UI the right auth prompt;
5. prevents accidental API key env fallback.

OAuth tokens must not be read from:

```text
environment variables;
credential stores;
caches;
local files;
provider registries.
```

The access token must come from the caller, for example:

```python
CallOptions(auth=OAuthBearerAuth(access_token))
```

### `none`

`none` means:

```text
This model defaults to no auth.
```

Typical uses:

```text
local models;
mock providers;
internal test services;
private endpoints that do not require auth.
```

If `CallOptions.auth is None` and `models.json.auth.kind == "none"`, no auth is
sent. If the caller explicitly passes auth, ordinary runtime still honors the
explicit override. Strict mode may diagnose that the model declared no auth but
the call supplied auth.

## Recommended `CallOptions.auth` Types

### ApiKeyAuth

Explicit API key or static token:

```python
ApiKeyAuth(
    value: str,
    header: str | None = None,
    prefix: str | None = None,
)
```

Resolution:

```text
If ApiKeyAuth specifies header/prefix:
  use those values.
Else if models.json.auth can provide compatible header/prefix hints:
  use those values.
Else:
  use safe defaults such as Authorization + Bearer.
```

### OAuthBearerAuth

Explicit OAuth access token:

```python
OAuthBearerAuth(
    access_token: str,
    header: str | None = None,
    prefix: str | None = None,
)
```

It must not contain:

```text
refresh_token
expires_at
client_id
client_secret
token_url
scope
credential store id
provider account id
```

Those fields belong to upper layers.

### NoAuth

Explicit no-auth request:

```python
CallOptions(auth=NoAuth())
```

This is a request-level override and is not equivalent to `auth=None`.

### HeadersAuth

Low-level escape hatch:

```python
CallOptions(
    auth=HeadersAuth({
        "Authorization": "Custom xxx",
        "X-Provider-Token": "yyy",
    })
)
```

Constraints:

```text
HeadersAuth is only explicit CallOptions.auth.
It is not auto-constructed from models.json.
It does not participate in env fallback.
It must be covered by secret redaction.
Ordinary runtime should not block it.
Strict mode may emit diagnostics.
```

This is not a general auth framework. It is a request-level escape hatch for
catalog lag or Provider-specific auth forms.

## Resolution Priority

Final priority:

```text
1. CallOptions.auth
2. models.json.auth default behavior
3. no-auth result or missing-auth error
```

Expanded:

```text
If CallOptions.auth is present:
  resolve explicit auth.

If CallOptions.auth is absent:
  resolve from models.json.auth.kind.
```

## Resolution Rules

### Explicit `CallOptions.auth`

When `CallOptions.auth is not None`:

| Explicit auth | Ordinary runtime behavior |
|---|---|
| `ApiKeyAuth` | Use explicit API key/static token |
| `OAuthBearerAuth` | Use explicit OAuth access token |
| `NoAuth` | Send no auth |
| `HeadersAuth` | Use explicit headers |

`models.json.auth` does not strongly block the call. It may supply header/prefix
hints, diagnostics, redaction hints, and documentation context.

### No Explicit `CallOptions.auth`

When `CallOptions.auth is None`:

| `models.json.auth.kind` | Behavior |
|---|---|
| `api_key` | Read API key/static credential from configured env vars |
| `oauth` | Raise missing auth; caller must pass explicit OAuth auth |
| `none` | Send no auth |
| not configured | Raise missing auth config unless explicitly classified as no-auth elsewhere |

## Decision Matrix

### Explicit Auth Present

| Model declaration | Explicit auth | Ordinary runtime behavior |
|---|---|---|
| `api_key` | `ApiKeyAuth` | Use explicit API key |
| `api_key` | `OAuthBearerAuth` | Use explicit OAuth token; diagnostic allowed |
| `api_key` | `NoAuth` | Send no auth; diagnostic allowed |
| `api_key` | `HeadersAuth` | Use explicit headers |
| `oauth` | `OAuthBearerAuth` | Use explicit OAuth token |
| `oauth` | `ApiKeyAuth` | Use explicit API key; diagnostic allowed |
| `oauth` | `NoAuth` | Send no auth; diagnostic allowed |
| `oauth` | `HeadersAuth` | Use explicit headers |
| `none` | `NoAuth` | Send no auth |
| `none` | `ApiKeyAuth` | Use explicit API key; diagnostic allowed |
| `none` | `OAuthBearerAuth` | Use explicit OAuth token; diagnostic allowed |
| `none` | `HeadersAuth` | Use explicit headers |

Ordinary runtime rule:

```text
Explicit auth wins. Catalog kind mismatch is diagnostic, not a default blocker.
```

### Explicit Auth Absent

| Model declaration | Default behavior |
|---|---|
| `api_key` | Read API key/static credential from env |
| `oauth` | MissingAuth |
| `none` | No auth |
| not configured | MissingAuthConfig or explicit no-auth policy |

## Ordinary Mode and Strict Mode

### Ordinary Runtime Mode

Ordinary runtime follows:

```text
explicit first;
default fallback;
no strong type blocking;
fail only when no usable auth exists.
```

This is the mode for real service calls.

### Strict / Diagnose Mode

Strict mode is for:

```text
tests;
CI;
catalog validation;
internal debugging;
configuration quality checks.
```

It may check:

- whether `models.json.auth.kind` matches `CallOptions.auth`;
- whether a no-auth model received auth;
- whether an API key model lacks env configuration;
- whether OAuth auth declarations contain API-key fallback fields;
- whether header or prefix configuration is invalid.

Strict mode should not be the default ordinary call path.

## `get_model`

Current position:

```text
get_model does not accept auth.
```

Reasons:

1. `get_model` retrieves model definitions.
2. Real credentials should not enter catalog model objects.
3. API key default auth can be resolved by an env resolver at request time.
4. OAuth is not suitable as a model-handle default.
5. `CallOptions.auth` already provides request-level override.
6. The current phase favors a simple architecture.

A returned model can know:

```text
default auth declaration;
API key env names;
OAuth must be explicit;
default no-auth behavior.
```

It must not hold real secrets.

## Future: BoundModel / with_auth

Future work may introduce:

```python
finance_model = model.with_auth(ApiKeyAuth.from_env("FINANCE_API_KEY"))
coding_model = model.with_auth(ApiKeyAuth.from_env("CODING_API_KEY"))
```

This would help with:

```text
one model with multiple long-lived API keys;
different business domains using different credentials;
callers avoiding repeated CallOptions.auth.
```

This is not part of the current design.

If introduced later, keep:

```text
Catalog Model does not store secrets.
BoundModel is a runtime-bound object.
CallOptions.auth remains highest priority.
OAuth should still not be implicitly bound by default.
```

Possible future priority:

```text
1. CallOptions.auth
2. BoundModel.default_auth
3. models.json.auth default behavior
4. no-auth result or missing-auth error
```

## Error Semantics

Recommended error categories:

| Error | Scenario |
|---|---|
| `MissingAuthError` | Default auth is required, but no usable credential exists |
| `MissingAuthConfigError` | No explicit auth and no default auth declaration |
| `InvalidAuthConfigError` | `models.json.auth` is malformed |
| `AuthResolutionError` | Auth input cannot be resolved into request headers |
| `ProviderAuthError` | Provider returned 401 or 403 |
| `AuthDiagnostic` | Explicit auth differs from model declaration, but ordinary runtime continues |

`AuthDiagnostic` is not an error.

Example diagnostic:

```text
model declares oauth, but call provided api_key; using explicit call auth.
```

## Security Principles

1. `models.json` and `Model` objects do not store real secrets.
2. API key env values are resolved lazily before provider request construction.
3. API keys, access tokens, authorization headers, and custom auth headers are
   always redacted in logs, errors, diagnostics, and traces.
4. Redaction must cover explicit `HeadersAuth`; escape hatches do not bypass
   secret handling.
5. OAuth is never implicitly read from env, credential stores, caches, local
   files, or provider registries.
6. `loushang.ai` does not automatically refresh auth, log in, switch accounts,
   switch models, or perform quota fallback after Provider 401/403.
7. Provider auth failures are normalized and returned to the upper layer.

Redaction must not rely only on model declarations. Global sensitive name
matching should cover at least:

```text
Authorization
x-api-key
api-key
token
access_token
api_key
secret
credential
```

## Reference Pseudocode

### Overall Resolution

```python
def resolve_auth_for_request(
    model: Model,
    options: CallOptions | None,
    env: Mapping[str, str],
) -> AuthView:
    declaration = model.auth
    explicit_auth = options.auth if options else None

    if explicit_auth is not None:
        return resolve_explicit_auth(
            explicit_auth,
            declaration_hint=declaration,
        )

    if declaration is None:
        raise MissingAuthConfigError(
            model=model.id,
            message="No explicit auth and no default auth declaration.",
        )

    if declaration.kind == "api_key":
        api_key = read_first_non_empty_env(
            declaration.api_key_envs,
            env,
        )
        if not api_key:
            raise MissingAuthError(
                model=model.id,
                expected="api_key",
                env_names=declaration.api_key_envs,
            )

        return build_api_key_auth_view(
            value=api_key,
            header=declaration.header,
            prefix=declaration.prefix,
        )

    if declaration.kind == "oauth":
        raise MissingAuthError(
            model=model.id,
            expected="oauth",
            message="OAuth auth must be provided explicitly through CallOptions.auth.",
        )

    if declaration.kind == "none":
        return AuthView(headers={})

    raise InvalidAuthConfigError(...)
```

### Explicit Auth Resolution

```python
def resolve_explicit_auth(
    auth: AuthCredential,
    declaration_hint: AuthDeclaration | None,
) -> AuthView:
    if isinstance(auth, NoAuth):
        return AuthView(headers={})

    if isinstance(auth, HeadersAuth):
        return AuthView(headers=auth.headers)

    if isinstance(auth, ApiKeyAuth):
        header, prefix = resolve_header_prefix(
            auth=auth,
            declaration_hint=declaration_hint,
            preferred_kind="api_key",
            fallback_header="Authorization",
            fallback_prefix="Bearer ",
        )
        return AuthView(headers={header: f"{prefix}{auth.value}"})

    if isinstance(auth, OAuthBearerAuth):
        header, prefix = resolve_header_prefix(
            auth=auth,
            declaration_hint=declaration_hint,
            preferred_kind="oauth",
            fallback_header="Authorization",
            fallback_prefix="Bearer ",
        )
        return AuthView(headers={header: f"{prefix}{auth.access_token}"})

    raise AuthResolutionError(...)
```

## Examples

### API Key Default Auth

`models.json`:

```json
{
  "auth": {
    "kind": "api_key",
    "apiKeyEnvs": ["MOONSHOT_API_KEY"],
    "header": "Authorization",
    "prefix": "Bearer "
  }
}
```

Call:

```python
model = get_model("moonshot:openai-completions:kimi-k2")
await complete(model, context)
```

Behavior:

```text
No explicit CallOptions.auth.
Read MOONSHOT_API_KEY.
Send Authorization: Bearer <key>.
```

### API Key Explicit Override

```python
await complete(
    model,
    context,
    options=CallOptions(auth=ApiKeyAuth("sk-temp")),
)
```

Behavior:

```text
Use explicit ApiKeyAuth.
Do not read default env vars.
```

### OAuth Explicit Auth

`models.json`:

```json
{
  "auth": {
    "kind": "oauth",
    "header": "Authorization",
    "prefix": "Bearer "
  }
}
```

Call:

```python
await complete(
    model,
    context,
    options=CallOptions(auth=OAuthBearerAuth(access_token)),
)
```

Behavior:

```text
Use explicit OAuth access token.
Send Authorization: Bearer <access_token>.
```

If auth is omitted, raise `MissingAuthError`.

### Explicit NoAuth

```python
await complete(
    model,
    context,
    options=CallOptions(auth=NoAuth()),
)
```

Behavior:

```text
Send no auth.
Do not run models.json.auth default logic.
```

### HeadersAuth Escape Hatch

```python
await complete(
    model,
    context,
    options=CallOptions(
        auth=HeadersAuth({
            "Authorization": "Custom xxx",
            "X-Provider-Token": "yyy",
        })
    ),
)
```

Behavior:

```text
Use explicit headers.
Do not let models.json.auth block the call.
Redact all sensitive headers.
```

## Ownership Split

| Capability | `loushang.ai` | Upper application/service |
|---|---:|---:|
| Read API key env vars | Yes | Provides env vars |
| Accept explicit API key | Yes | Yes |
| Accept explicit OAuth access token | Yes | Yes |
| Build Provider auth headers | Yes | No |
| OAuth login | No | Yes |
| OAuth refresh | No | Yes |
| Credential storage | No | Yes |
| Multi-account selection | No | Yes |
| Provider account profile | No | Yes |
| Quota lookup | No | Yes |
| Billing lookup | No | Yes |
| Route models based on auth/account state | No | Yes |
| Retry strategy after Provider 401/403 | No, only normalize errors | Yes |
| Request-level explicit auth override | Yes | Decides when to use |

## Invariants

1. `models.json.auth` is a default declaration, not a strong call-time
   validator.
2. `CallOptions.auth` is the explicit auth input for this request and has
   highest priority.
3. When `CallOptions.auth` exists, ordinary runtime does not block only because
   `models.json.auth.kind` differs.
4. When `CallOptions.auth` is absent, `models.json.auth` default logic applies.
5. `api_key` means a broad static request credential and may use env fallback.
6. `oauth` means the access token must be explicitly supplied by the upper
   layer.
7. `none` means default no-auth.
8. `NoAuth` and `auth=None` are semantically different.
9. `HeadersAuth` is explicit-only and does not participate in default auth
   construction.
10. OAuth login, refresh, storage, account selection, quota, and billing are
    outside `loushang.ai`.
11. `get_model` does not accept auth.
12. `BoundModel / with_auth` is future work, not current scope.
13. Secrets are lazily resolved and never stored on catalog models.
14. Secrets never appear in logs, errors, diagnostics, or traces.
15. Provider auth failure is normalized as an error; `loushang.ai` does not
    automatically refresh or retry auth.

## Conclusion

The design can be summarized as:

```text
models.json.auth:
  declares what to do when no explicit auth is supplied.

CallOptions.auth:
  decides how this request actually authenticates.
```

API key and static token auth may be defaulted from environment variables or
explicitly overridden per request.

OAuth auth must be supplied explicitly by the caller and is never implicitly
loaded, refreshed, or stored by `loushang.ai`.

`NoAuth` is an explicit request-level override, distinct from omitted auth.

`HeadersAuth` is a low-level request-level escape hatch for catalog lag or
special Provider auth forms.

In one sentence:

```text
models.json.auth is the default declaration; CallOptions.auth is the explicit
request fact. loushang.ai resolves the final auth input into Provider request
headers and owns no auth lifecycle, account system, or Provider control-plane.
```

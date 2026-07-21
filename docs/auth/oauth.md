# `loushang.ai` authentication

Authentication lifecycle ownership lives in `loushang.ai.auth`. Agent, coding,
TUI, and CLI layers may display login interaction and call the public auth API,
but they do not parse token files, refresh OAuth tokens, or select OAuth
providers.

## API keys

The shortest path is model-configured environment lookup:

```python
from loushang.ai import complete, get_model

model = get_model("moonshot", "openai-completions", "kimi-k2.6")
message = await complete(
    model,
    {"messages": [{"role": "user", "content": "Hello"}]},
)
```

The model catalog's `auth.apiKeyEnv` / `auth.apiKeyEnvs` declarations determine
which environment variables are checked. A call can override that lookup with
request-level auth:

```python
from loushang.ai import ApiKeyAuth, CallOptions

options = CallOptions(auth=ApiKeyAuth("explicit-key"))
```

## OAuth credentials

`OAuthCredential` is lifecycle state. It can be saved, loaded, checked for
expiry, and refreshed. `OAuthBearerAuth` is request state and exists only after
resolution. They are intentionally different types.

```python
from loushang.ai import CallOptions, OAuthCredential, complete

credential = OAuthCredential(
    provider="company-oauth",
    access_token="...",
    refresh_token="...",
    expires_at=1893456000,
    extra_headers={"x-account": "account-id"},
)
message = await complete(model, context, CallOptions(credential=credential))
```

A credential file can be passed without parsing it in the caller:

```python
options = CallOptions(credential_file="/secure/path/company-oauth-auth.json")
```

When neither is supplied, the resolver uses
`~/.loushang/auth/{provider}-auth.json`. Within the model's declared auth kind,
resolution order is:

1. `CallOptions.auth` request auth.
2. An explicitly supplied `OAuthCredential`.
3. `CallOptions.credential_file`.
4. The default `FileCredentialStore`.
5. A registered external `CredentialSource`, when one exists.
6. Model-configured API-key environment variables.

An OAuth token within the refresh window is refreshed before `ProviderRequest`
is created. The updated token is atomically written back when its source is a
Loushang credential file or the default store. OAuth provider adapters receive
the lifecycle credential; model protocol adapters receive only request-level
auth and resolved headers, never the lifecycle credential or its source.

## External credential import vs OAuth login

OAuth providers and credential sources are separate extension points:

| Capability | `OAuthProvider` | `CredentialSource` |
|---|---|---|
| Starts a new OAuth login | Yes | No |
| Requires an authorized client ID and OAuth endpoints | Yes | No |
| Exchanges authorization codes or refreshes tokens | Yes | No |
| Imports an existing external login | No | Yes |
| Implements `login` / `refresh` / `revoke` | Yes | No |

An OAuth provider means Loushang owns the authorization-code lifecycle for a
configured client. A credential source only converts credential state created
and managed by another application. Registering a source never makes
`auth.login(source_id)` available.

The OAuth provider registry is empty by default. Applications explicitly
register only providers with complete, authorized client configuration. The
credential-source registry is independent and includes the experimental Codex
file importer described below.

## Login, status, and logout

OAuth interaction stays simple: a provider adapter owns protocol details, and
the upper layer supplies a callback that displays the authorization URL and
returns the final redirect URL.

```python
import loushang.ai.auth as auth
from loushang.ai.auth.oauth import AuthlibOAuthProvider, OAuthClientConfig

provider = AuthlibOAuthProvider(
    "company-oauth",
    OAuthClientConfig(
        client_id="authorized-client-id",
        authorization_endpoint="https://login.example/authorize",
        token_endpoint="https://login.example/token",
        redirect_uri="http://127.0.0.1/callback",
    ),
)
auth.register_oauth_provider(provider)

async def authorize(url: str) -> str:
    print(f"Open this URL: {url}")
    return input("Paste the final redirect URL: ").strip()

credential = await auth.login(provider.id, authorize=authorize)
status = auth.credential_status("company-oauth")
await auth.logout("company-oauth")
```

`AuthlibOAuthProvider` uses Authlib for authorization URL/state handling, PKCE,
token exchange, refresh, and revocation. Loushang does not implement those
protocol operations itself.

## Credential file format

`FileCredentialStore` writes UTF-8 JSON using an atomic replace. Directories are
created with mode `0700` and credential files use mode `0600` where the platform
supports POSIX permissions. Tokens are excluded from normal object reprs and
must never be logged.

```json
{
  "version": 1,
  "provider": "company-oauth",
  "credential_type": "oauth",
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1893456000,
  "token_type": "Bearer",
  "extra_headers": {
    "x-account": "account-id"
  }
}
```

## Provider adapters

A provider implements the small `OAuthProvider` protocol:

```python
class CompanyOAuthProvider:
    id = "company-oauth"

    async def login(self, *, authorize=None) -> OAuthCredential: ...
    async def refresh(self, credential: OAuthCredential) -> OAuthCredential: ...
    async def revoke(self, credential: OAuthCredential) -> None: ...
```

For a standard authorization-code provider, construct `AuthlibOAuthProvider`
with `OAuthClientConfig`, then register it with `register_oauth_provider()`.
Do not put model selection, agent state, UI behavior, or external file parsing
in an OAuth adapter.

Kimi Code is reserved for a future authorized OAuth client. It cannot be
constructed or registered without complete application-supplied configuration:

```python
from loushang.ai.auth import register_oauth_provider
from loushang.ai.auth.oauth.providers import (
    KimiCodeOAuthProvider,
    KimiOAuthConfig,
)

config = KimiOAuthConfig(
    client_id="authorized-client-id",
    authorization_endpoint="https://authorized.example/authorize",
    token_endpoint="https://authorized.example/token",
    redirect_uri="http://127.0.0.1/callback",
)
register_oauth_provider(KimiCodeOAuthProvider(config))
```

No Kimi client ID or endpoint is fabricated, and no empty Kimi provider is
registered during import.

## Credential sources

`OpenAICodexCredentialSource` is an experimental credential importer, not an
OAuth provider. It may read a file-backed Codex ChatGPT login from
`~/.codex/auth.json` and convert it into an `OAuthCredential`. It has no
`login`, `refresh`, or `revoke` methods and never appears in the OAuth provider
registry.

Loushang does not own an OpenAI OAuth client and does not overwrite the Codex
credential. Codex owns its browser login and token refresh lifecycle; run
`codex login` to establish or repair that external login. Codex may store its
credential in an OS credential store instead of the file, in which case this
experimental file import is unavailable. Treat the file as a password. See the
[Codex authentication documentation](https://learn.chatgpt.com/docs/auth.md).

A custom importer implements `CredentialSource.load()` and `load_file()`, then
registers with `register_credential_source()`. It converts external state into
`OAuthCredential` only; it must not implement provider login, refresh, or
revocation.

## Errors

Lifecycle failures are structured authentication errors:

- `MissingCredentialError`: follow `recovery`; a provider uses `login`, while
  the Codex source uses `codex_login`.
- `CredentialExpiredError`: log in again when no refresh path exists.
- `RefreshFailedError`: refresh failed or no provider owns refresh; the
  `recovery` detail identifies the external or provider login path.
- `InvalidCredentialError`: repair or replace malformed/incompatible data.
- `OAuthProviderNotConfiguredError`: configure an authorized OAuth client.

These errors occur before the provider request, so upper layers do not need to
infer login state from a generic HTTP 401.

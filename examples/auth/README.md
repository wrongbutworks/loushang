# Authentication examples

These examples run offline while exercising the real `loushang.ai` request path:

```bash
uv run python examples/auth/api_key_example.py
uv run python examples/auth/oauth_credential_file_example.py
uv run python examples/auth/oauth_status_login_example.py
```

The first example proves both model-configured environment lookup and explicit
`ApiKeyAuth`. The second proves the complete persisted OAuth credential path
through `ProviderRequest`. The third uses a local demonstration provider so
`login`, status, persistence, and logout can run without an external OAuth
client registration. Real authorization-code providers use
`AuthlibOAuthProvider` and supply an authorization callback that shows the URL
and returns the final redirect URL.

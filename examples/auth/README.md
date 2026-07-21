# Authentication examples

These examples run offline while exercising the real `loushang.ai` request path:

```bash
uv run python examples/auth/api_key_example.py
uv run python examples/auth/oauth_status_login_example.py
uv run python examples/auth/external_credential_source_example.py
```

The API-key example follows `get_auth(model) -> request`. The OAuth example is
a complete offline authorization-code flow: model configuration creates a
login session, the example (standing in for a CLI) handles the authorization
URL, `session.wait()` stores the credential, and `get_auth()` prepares the
request. The auth package never opens a browser.

The external-source example imports an existing Codex CLI login through the
extension registry and calls a model with the resulting `OAuthBearerAuth`.
This path is experimental credential import, not Loushang OAuth login; Codex
owns the source credential and its refresh lifecycle.

After `codex login`, run the live upper-application path with:

```bash
uv run python examples/auth/openai_codex_live_example.py
```

The live example only uses `get_model()`, `auth.get_auth(model)`, and `stream()`.
It does not parse `~/.codex/auth.json` or invoke a credential source directly.
OpenAI Codex support currently imports existing Codex CLI credentials. It does
not perform ChatGPT OAuth login.

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from loushang.ai.auth import (
    AuthError,
    FileCredentialStore,
    InvalidCredentialError,
    OAuthCredential,
    OAuthProviderNotConfiguredError,
    RefreshFailedError,
    credential_status,
    get_oauth_provider,
    login,
    logout,
    register_oauth_provider,
)
from loushang.ai.auth.oauth.client import AuthlibOAuthProvider, OAuthClientConfig
from loushang.ai.auth.oauth.providers import (
    KimiCodeOAuthProvider,
    OpenAICodexOAuthProvider,
    load_codex_credential,
)


@dataclass
class _FakeProvider:
    id: str = "fake-oauth"
    revoked: list[OAuthCredential] = field(default_factory=list)

    async def login(self, *, authorize=None) -> OAuthCredential:
        del authorize
        return OAuthCredential(
            provider=self.id,
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=2000,
        )

    async def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        return credential

    async def revoke(self, credential: OAuthCredential) -> None:
        self.revoked.append(credential)


def test_login_status_logout_use_provider_and_store(tmp_path: Path) -> None:
    provider = _FakeProvider()
    store = FileCredentialStore(tmp_path)

    async def scenario():
        missing = credential_status(provider, store=store, now=1000)
        credential = await login(provider, store=store)
        current = credential_status(provider, store=store, now=1000)
        deleted = await logout(provider, store=store)
        final = credential_status(provider, store=store, now=1000)
        return missing, credential, current, deleted, final

    missing, credential, current, deleted, final = asyncio.run(scenario())

    assert missing.state == "missing"
    assert credential.access_token == "access-token"
    assert current.state == "valid"
    assert current.authenticated is True
    assert current.source == "default_store"
    assert deleted is True
    assert provider.revoked == [credential]
    assert final.state == "missing"


def test_kimi_code_adapter_does_not_fabricate_client_id() -> None:
    provider = KimiCodeOAuthProvider()

    with pytest.raises(OAuthProviderNotConfiguredError) as exc_info:
        asyncio.run(provider.login())

    assert exc_info.value.info.details == {
        "recovery": "configure_client",
    }


def test_openai_codex_adapter_imports_existing_file_experimentally(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": "codex-access",
                    "refresh_token": "codex-refresh",
                    "account_id": "account-id",
                },
            }
        ),
        encoding="utf-8",
    )

    credential = load_codex_credential(path)

    assert credential.provider == "openai-codex"
    assert credential.access_token == "codex-access"
    assert credential.refresh_token == "codex-refresh"
    assert credential.extra_headers == {"ChatGPT-Account-ID": "account-id"}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"auth_mode": "apikey"},
        {"auth_mode": "chatgpt"},
        {"auth_mode": "chatgpt", "tokens": {"account_id": "account-id"}},
    ],
)
def test_openai_codex_adapter_rejects_invalid_file(
    tmp_path: Path,
    payload: object,
) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidCredentialError):
        load_codex_credential(path)


class _FakeAuthlibClient:
    def __init__(self) -> None:
        self.authorization_code_verifier: str | None = None
        self.fetch_code_verifier: str | None = None
        self.authorization_response: str | None = None
        self.closed = False
        self.refresh_calls: list[tuple[object, object]] = []
        self.revoke_calls: list[tuple[object, object, object]] = []
        self.fail_fetch = False
        self.fail_refresh = False

    def create_authorization_url(self, endpoint, *, code_verifier):
        assert endpoint == "https://provider.test/authorize"
        self.authorization_code_verifier = code_verifier
        return "https://provider.test/authorize?state=authlib", "authlib-state"

    async def fetch_token(
        self,
        endpoint,
        *,
        authorization_response,
        code_verifier,
    ):
        assert endpoint == "https://provider.test/token"
        self.authorization_response = authorization_response
        self.fetch_code_verifier = code_verifier
        if self.fail_fetch:
            raise RuntimeError("fetch failed")
        return {
            "access_token": "authlib-access",
            "refresh_token": "authlib-refresh",
            "expires_at": 2000,
            "token_type": "Bearer",
        }

    async def refresh_token(self, endpoint, *, refresh_token):
        self.refresh_calls.append((endpoint, refresh_token))
        if self.fail_refresh:
            raise RuntimeError("refresh failed")
        return {
            "access_token": "refreshed-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    async def revoke_token(self, endpoint, *, token, token_type_hint):
        self.revoke_calls.append((endpoint, token, token_type_hint))

    async def aclose(self) -> None:
        self.closed = True


class _TestAuthlibProvider(AuthlibOAuthProvider):
    def __init__(self, client: _FakeAuthlibClient) -> None:
        super().__init__(
            "authlib-test",
            OAuthClientConfig(
                client_id="authorized-client",
                authorization_endpoint="https://provider.test/authorize",
                token_endpoint="https://provider.test/token",
                redirect_uri="http://127.0.0.1/callback",
                revocation_endpoint="https://provider.test/revoke",
            ),
        )
        self.client = client

    def _new_client(self, *, token=None):
        del token
        return self.client


def test_authlib_provider_owns_authorization_url_pkce_and_token_exchange() -> None:
    client = _FakeAuthlibClient()
    provider = _TestAuthlibProvider(client)
    shown_urls: list[str] = []

    async def authorize(url: str) -> str:
        shown_urls.append(url)
        return "http://127.0.0.1/callback?code=code&state=authlib-state"

    credential = asyncio.run(provider.login(authorize=authorize))

    assert shown_urls == ["https://provider.test/authorize?state=authlib"]
    assert client.authorization_code_verifier
    assert client.fetch_code_verifier == client.authorization_code_verifier
    assert client.authorization_response == (
        "http://127.0.0.1/callback?code=code&state=authlib-state"
    )
    assert client.closed is True
    assert credential.provider == "authlib-test"
    assert credential.access_token == "authlib-access"


def test_authlib_provider_refreshes_and_revokes_with_authlib_client() -> None:
    client = _FakeAuthlibClient()
    provider = _TestAuthlibProvider(client)
    current = OAuthCredential(
        provider=provider.id,
        access_token="current-access",
        refresh_token="current-refresh",
        expires_at=1000,
        extra_headers={"x-account": "account-id"},
    )

    refreshed = asyncio.run(provider.refresh(current))
    asyncio.run(provider.revoke(refreshed))

    assert client.refresh_calls == [
        ("https://provider.test/token", "current-refresh")
    ]
    assert refreshed.access_token == "refreshed-access"
    assert refreshed.refresh_token == "current-refresh"
    assert refreshed.expires_at is not None and refreshed.expires_at > 1000
    assert refreshed.extra_headers == {"x-account": "account-id"}
    assert client.revoke_calls == [
        (
            "https://provider.test/revoke",
            "current-refresh",
            "refresh_token",
        )
    ]


def test_authlib_provider_wraps_protocol_failures() -> None:
    client = _FakeAuthlibClient()
    provider = _TestAuthlibProvider(client)
    client.fail_fetch = True

    async def authorize(url: str) -> str:
        return url.replace("authorize?state=authlib", "callback?code=x")

    with pytest.raises(AuthError, match="login failed"):
        asyncio.run(provider.login(authorize=authorize))

    client.fail_fetch = False
    client.fail_refresh = True
    credential = OAuthCredential(
        provider=provider.id,
        access_token="access",
        refresh_token="refresh",
    )
    with pytest.raises(RefreshFailedError, match="refresh failed"):
        asyncio.run(provider.refresh(credential))


def test_authlib_provider_validates_configuration_and_token_shapes() -> None:
    client = _FakeAuthlibClient()
    provider = _TestAuthlibProvider(client)
    with pytest.raises(OAuthProviderNotConfiguredError, match="authorization callback"):
        asyncio.run(provider.login())
    with pytest.raises(InvalidCredentialError, match="does not match"):
        asyncio.run(
            provider.refresh(
                OAuthCredential(provider="other", access_token="access")
            )
        )
    with pytest.raises(InvalidCredentialError, match="no refresh token"):
        asyncio.run(
            provider.refresh(
                OAuthCredential(provider=provider.id, access_token="access")
            )
        )
    with pytest.raises(InvalidCredentialError, match="must be a mapping"):
        provider.credential_from_token([])  # type: ignore[arg-type]
    with pytest.raises(InvalidCredentialError, match="missing access_token"):
        provider.credential_from_token({})

    incomplete = AuthlibOAuthProvider(
        "incomplete",
        OAuthClientConfig(
            client_id="client",
            authorization_endpoint=None,
            token_endpoint=None,
            redirect_uri=None,
        ),
    )
    with pytest.raises(OAuthProviderNotConfiguredError) as exc_info:
        asyncio.run(incomplete.login())
    assert exc_info.value.info.details["missing"] == [
        "authorization_endpoint",
        "token_endpoint",
        "redirect_uri",
    ]


def test_oauth_registry_and_status_cover_lifecycle_states(tmp_path: Path) -> None:
    provider = _FakeProvider(id="registry-test")
    register_oauth_provider(provider, replace=True)
    assert get_oauth_provider(provider.id) is provider
    with pytest.raises(ValueError, match="already registered"):
        register_oauth_provider(provider)

    store = FileCredentialStore(tmp_path)
    store.save(
        OAuthCredential(
            provider=provider.id,
            access_token="expiring",
            expires_at=1030,
        )
    )
    assert credential_status(provider.id, store=store, now=1000).state == "expiring"
    assert credential_status(provider.id, store=store, now=1100).state == "expired"
    assert asyncio.run(logout(provider.id, store=store, revoke=False)) is True
    assert asyncio.run(logout(provider.id, store=store)) is False
    with pytest.raises(KeyError, match="not registered"):
        credential_status("missing-registry-provider", store=store)
    with pytest.raises(TypeError, match="must define"):
        register_oauth_provider(object())  # type: ignore[arg-type]


def test_openai_codex_provider_is_read_only_and_reports_login_recovery(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    provider = OpenAICodexOAuthProvider(path)
    assert provider.load_external_credential() is None
    path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"access_token": "access", "refresh_token": "refresh"},
            }
        ),
        encoding="utf-8",
    )
    credential = provider.load_external_credential()
    assert credential is not None
    assert provider.load_credential_file(path) == credential
    with pytest.raises(OAuthProviderNotConfiguredError, match="codex login"):
        asyncio.run(provider.login())
    with pytest.raises(RefreshFailedError, match="codex login"):
        asyncio.run(provider.refresh(credential))
    asyncio.run(provider.revoke(credential))

from __future__ import annotations

import asyncio

import pytest

from loushang.ai.auth import OAuthReauthenticationRequiredError
from loushang.ai.auth.facade import register_builtin_oauth_providers
from loushang.ai.auth.oauth import get_oauth_api_key
from loushang.ai.auth.registry import get_default_oauth_registry
from loushang.ai.auth.types import OAuthCredentials


def test_oauth_credentials_repr_redacts_tokens() -> None:
    credentials = OAuthCredentials(
        provider="demo",
        access_token="access-secret",
        refresh_token="refresh-secret",
        extra={
            "account_id": "account-secret",
            "headers": {"chatgpt-account-id": "header-secret"},
        },
    )

    rendered = repr(credentials)

    assert "access-secret" not in rendered
    assert "refresh-secret" not in rendered
    assert "account-secret" not in rendered
    assert "header-secret" not in rendered


class _AsyncRefreshProvider:
    id = "demo"
    name = "Demo"

    async def login(self, callbacks) -> OAuthCredentials:
        raise AssertionError(f"unexpected login: {callbacks}")

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        await asyncio.sleep(0)
        return OAuthCredentials(
            provider=credentials.provider,
            access_token="new-token",
            refresh_token=credentials.refresh_token,
            expires_at=9999999999.0,
        )

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    def uses_callback_server(self) -> bool:
        return False

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        del credentials
        return models


@pytest.fixture
def _oauth_registry():
    registry = get_default_oauth_registry()
    registry.clear()
    yield registry
    registry.clear()
    register_builtin_oauth_providers()


def test_get_oauth_api_key_refreshes_async_provider_inside_running_loop(
    _oauth_registry,
) -> None:
    _oauth_registry.register(_AsyncRefreshProvider(), source_id="test")
    expired = OAuthCredentials(
        provider="demo",
        access_token="old-token",
        refresh_token="refresh-token",
        expires_at=0.0,
    )

    async def _run() -> None:
        result = get_oauth_api_key("demo", {"demo": expired})

        assert result is not None
        assert result["apiKey"] == "new-token"
        assert result["newCredentials"].access_token == "new-token"

    asyncio.run(_run())


def test_get_oauth_api_key_ignores_empty_access_token() -> None:
    result = get_oauth_api_key(
        "demo",
        {"demo": OAuthCredentials(provider="demo", access_token="  ")},
    )

    assert result is None


@pytest.mark.parametrize("refresh_token", [None, "", "   "])
@pytest.mark.parametrize("access_token", ["old-secret-token", "", "   "])
def test_get_oauth_api_key_requires_login_for_expired_token_without_refresh(
    access_token: str,
    refresh_token: str | None,
) -> None:
    credentials = OAuthCredentials(
        provider="demo",
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=0.0,
    )

    with pytest.raises(OAuthReauthenticationRequiredError) as captured:
        get_oauth_api_key("demo", {"demo": credentials})

    rendered = f"{captured.value!r} {captured.value}"
    assert "log in again" in rendered
    assert "old-secret-token" not in rendered
    assert credentials.expires_at == 0.0

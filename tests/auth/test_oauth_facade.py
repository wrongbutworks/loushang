from __future__ import annotations

import asyncio
from dataclasses import asdict

import pytest

from loushang.ai.auth import facade
from loushang.ai.auth.facade import oauth_login, oauth_refresh, resolve_oauth_api_key
from loushang.ai.auth.registry import OAuthProviderRegistry
from loushang.ai.auth.types import OAuthCredentials


class _Callbacks:
    def on_auth(self, info: dict) -> None:
        del info

    async def on_prompt(self, prompt: dict) -> str:
        raise AssertionError(f"unexpected prompt: {prompt}")

    def on_progress(self, message: str) -> None:
        del message

    async def on_manual_code_input(self) -> str:
        return ""

    @property
    def signal(self) -> object | None:
        return None


class _FakeProvider:
    id = "demo"
    name = "Demo"

    async def login(self, callbacks) -> OAuthCredentials:
        del callbacks
        return OAuthCredentials(
            provider=self.id,
            access_token="login-token",
            refresh_token="refresh-token",
        )

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        return OAuthCredentials(
            provider=credentials.provider,
            access_token="refreshed-token",
            refresh_token=credentials.refresh_token,
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


def _registry() -> OAuthProviderRegistry:
    registry = OAuthProviderRegistry()
    registry.register_oauth_provider(_FakeProvider(), source_id="test")
    return registry


def test_oauth_login_persists_into_explicit_credentials_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_calls: list[dict[str, OAuthCredentials]] = []
    monkeypatch.setattr(
        facade,
        "load_credentials",
        lambda: pytest.fail("explicit credentials should not load storage"),
    )
    monkeypatch.setattr(facade, "save_credentials", lambda data: save_calls.append(data))

    result = asyncio.run(
        oauth_login(
            "demo",
            _Callbacks(),
            registry=_registry(),
            credentials={},
            persist=True,
        )
    )

    assert result.access_token == "login-token"
    assert [asdict(saved["demo"]) for saved in save_calls] == [asdict(result)]


def test_oauth_login_without_persist_does_not_touch_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credentials",
        lambda: pytest.fail("non-persistent login should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "save_credentials",
        lambda _data: pytest.fail("non-persistent login should not save storage"),
    )

    result = asyncio.run(
        oauth_login("demo", _Callbacks(), registry=_registry(), persist=False)
    )

    assert result.provider == "demo"
    assert result.access_token == "login-token"


def test_oauth_refresh_persists_refreshed_stored_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = OAuthCredentials(
        provider="demo",
        access_token="old-token",
        refresh_token="refresh-token",
    )
    save_calls: list[dict[str, OAuthCredentials]] = []
    monkeypatch.setattr(facade, "load_credentials", lambda: {"demo": original})
    monkeypatch.setattr(facade, "save_credentials", lambda data: save_calls.append(data))

    result = asyncio.run(oauth_refresh("demo", registry=_registry(), persist=True))

    assert result.access_token == "refreshed-token"
    assert [asdict(saved["demo"]) for saved in save_calls] == [asdict(result)]


def test_oauth_refresh_explicit_credentials_without_persist_does_not_touch_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credentials",
        lambda: pytest.fail("explicit non-persistent refresh should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "save_credentials",
        lambda _data: pytest.fail("explicit non-persistent refresh should not save storage"),
    )

    result = asyncio.run(
        oauth_refresh(
            "demo",
            OAuthCredentials(
                provider="demo",
                access_token="old-token",
                refresh_token="refresh-token",
            ),
            registry=_registry(),
            persist=False,
        )
    )

    assert result.access_token == "refreshed-token"


def test_resolve_oauth_api_key_uses_explicit_empty_credentials_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credentials",
        lambda: pytest.fail("explicit credentials should not load storage"),
    )

    assert resolve_oauth_api_key("demo", credentials={}) is None

from __future__ import annotations

import asyncio
from dataclasses import asdict

import pytest

import loushang.ai.auth as auth_module
import loushang.ai.auth.facade as facade
from loushang.ai.auth import OAuthReauthenticationRequiredError
from loushang.ai.auth.facade import (
    oauth_login,
    oauth_refresh,
    register_builtin_oauth_providers,
    resolve_oauth_api_key,
)
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


class _RefreshSpyProvider(_FakeProvider):
    def __init__(self) -> None:
        self.refresh_calls = 0

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        self.refresh_calls += 1
        return await super().refresh_token(credentials)


def _registry() -> OAuthProviderRegistry:
    registry = OAuthProviderRegistry()
    registry.register(_FakeProvider(), source_id="test")
    return registry


def _capture_store_updates(store, save_calls):
    def _update(mutator):
        result = mutator(store)
        save_calls.append(
            {
                "providers": dict(store["providers"]),
                "endpoints": dict(store["endpoints"]),
                "models": dict(store["models"]),
            }
        )
        return result

    return _update


def test_ai_auth_exports_lifecycle_api_without_registry_method_wrappers() -> None:
    lifecycle_exports = (
        "CredentialStore",
        "OAuthProviderRegistry",
        "OAuthError",
        "OAuthReauthenticationRequiredError",
        "get_default_oauth_registry",
        "get_oauth_api_key",
        "load_credentials",
        "oauth_login",
        "oauth_refresh",
        "register_builtin_oauth_providers",
    )
    removed_facade_wrappers = (
        "register_oauth_provider",
        "get_oauth_provider",
        "list_oauth_providers",
        "clear_oauth_providers",
        "reset_oauth_providers",
        "ensure_builtin_oauth_providers",
    )

    for name in lifecycle_exports:
        assert hasattr(auth_module, name)

    for name in removed_facade_wrappers:
        assert not hasattr(auth_module, name)
        assert not hasattr(facade, name)


def test_register_builtin_oauth_providers_does_not_reset_registry() -> None:
    registry = _registry()

    register_builtin_oauth_providers(registry=registry)

    assert registry.get("demo") is not None
    assert registry.get("anthropic") is not None


def test_oauth_login_persists_into_explicit_credentials_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_calls: list[dict[str, OAuthCredentials]] = []
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("explicit credentials should not load storage"),
    )
    monkeypatch.setattr(
        facade, "save_credentials", lambda data: save_calls.append(data)
    )

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


def test_oauth_login_persists_provider_scope_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = {"providers": {}, "endpoints": {}, "models": {}}
    save_calls: list[dict[str, dict[str, OAuthCredentials]]] = []
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        _capture_store_updates(store, save_calls),
    )

    result = asyncio.run(
        oauth_login("demo", _Callbacks(), registry=_registry(), persist=True)
    )

    assert result.access_token == "login-token"
    assert save_calls[0]["providers"]["demo"] == result
    assert save_calls[0]["endpoints"] == {}
    assert save_calls[0]["models"] == {}


def test_oauth_login_persists_model_scope_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = {"providers": {}, "endpoints": {}, "models": {}}
    save_calls: list[dict[str, dict[str, OAuthCredentials]]] = []
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        _capture_store_updates(store, save_calls),
    )

    result = asyncio.run(
        oauth_login(
            "demo",
            _Callbacks(),
            registry=_registry(),
            endpoint_id="responses",
            model_id="chat",
            persist=True,
        )
    )

    assert save_calls[0]["models"]["demo:responses:chat"] == result


def test_oauth_login_without_persist_does_not_touch_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("non-persistent login should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail("non-persistent login should not update storage"),
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
    store = {"providers": {"demo": original}, "endpoints": {}, "models": {}}
    save_calls: list[dict[str, dict[str, OAuthCredentials]]] = []
    monkeypatch.setattr(facade, "load_credential_store", lambda: store)
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        _capture_store_updates(store, save_calls),
    )

    result = asyncio.run(oauth_refresh("demo", registry=_registry(), persist=True))

    assert result.access_token == "refreshed-token"
    assert [asdict(saved["providers"]["demo"]) for saved in save_calls] == [
        asdict(result)
    ]


def test_oauth_refresh_explicit_credentials_without_persist_does_not_touch_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("explicit non-persistent refresh should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail(
            "explicit non-persistent refresh should not update storage"
        ),
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


def test_oauth_refresh_explicit_credentials_default_does_not_touch_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("explicit refresh should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail("explicit refresh should not update storage"),
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
        )
    )

    assert result.access_token == "refreshed-token"


def test_oauth_refresh_rejects_explicit_credentials_without_refresh_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _RefreshSpyProvider()
    registry = OAuthProviderRegistry()
    registry.register(provider, source_id="test")
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail("failed refresh must not update storage"),
    )

    with pytest.raises(OAuthReauthenticationRequiredError, match="log in again"):
        asyncio.run(
            oauth_refresh(
                "demo",
                OAuthCredentials(
                    provider="demo",
                    access_token="expired-secret",
                    refresh_token=None,
                    expires_at=0.0,
                ),
                registry=registry,
                persist=True,
            )
        )

    assert provider.refresh_calls == 0


def test_oauth_refresh_rejects_stored_credentials_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _RefreshSpyProvider()
    registry = OAuthProviderRegistry()
    registry.register(provider, source_id="test")
    store = {
        "providers": {
            "demo": OAuthCredentials(
                provider="demo",
                access_token="expired-secret",
                refresh_token="  ",
                expires_at=0.0,
            )
        },
        "endpoints": {},
        "models": {},
    }
    monkeypatch.setattr(facade, "load_credential_store", lambda: store)
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail("failed refresh must not update storage"),
    )

    with pytest.raises(OAuthReauthenticationRequiredError, match="log in again"):
        asyncio.run(oauth_refresh("demo", registry=registry))

    assert provider.refresh_calls == 0


def test_resolve_oauth_api_key_uses_explicit_empty_credentials_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("explicit credentials should not load storage"),
    )

    assert resolve_oauth_api_key("demo", credentials={}) is None


def test_resolve_oauth_api_key_explicit_credentials_default_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: pytest.fail("explicit credentials should not load storage"),
    )
    monkeypatch.setattr(
        facade,
        "save_credentials",
        lambda _stored: pytest.fail(
            "explicit credentials should not persist by default"
        ),
    )

    result = resolve_oauth_api_key(
        "demo",
        credentials={
            "demo": OAuthCredentials(provider="demo", access_token="explicit-token")
        },
    )

    assert result is not None
    assert result["apiKey"] == "explicit-token"


def test_resolve_oauth_api_key_explicit_credentials_can_persist_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_calls: list[dict[str, OAuthCredentials]] = []
    monkeypatch.setattr(
        facade, "save_credentials", lambda stored: save_calls.append(stored)
    )

    result = resolve_oauth_api_key(
        "demo",
        credentials={
            "demo": OAuthCredentials(provider="demo", access_token="explicit-token")
        },
        persist_refresh=True,
    )

    assert result is not None
    assert [saved["demo"].access_token for saved in save_calls] == ["explicit-token"]


def test_resolve_oauth_api_key_prefers_model_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OAuthCredentials(provider="demo", access_token="provider-token")
    endpoint = OAuthCredentials(provider="demo", access_token="endpoint-token")
    model = OAuthCredentials(provider="demo", access_token="model-token")
    monkeypatch.setattr(
        facade,
        "load_credential_store",
        lambda: {
            "providers": {"demo": provider},
            "endpoints": {"demo:responses": endpoint},
            "models": {"demo:responses:chat": model},
        },
    )
    monkeypatch.setattr(
        facade,
        "update_credential_store",
        lambda _mutator: pytest.fail("persist_refresh=False should not update storage"),
    )

    result = resolve_oauth_api_key(
        "demo",
        endpoint_id="responses",
        model_id="chat",
        persist_refresh=False,
    )

    assert result is not None
    assert result["apiKey"] == "model-token"

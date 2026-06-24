from __future__ import annotations

from types import SimpleNamespace

import pytest

from loushang.ai.auth.env import get_env_oauth_credentials
from loushang.ai.auth.registry import get_default_oauth_registry
from loushang.ai.auth.support import AuthConfig, resolve_auth_for_model
from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.model import Auth, Endpoint, Model, ModelRegistry, Provider


class _FailingRefreshProvider:
    id = "demo"
    name = "Demo"

    def uses_callback_server(self) -> bool:
        return False

    async def login(self, callbacks):
        raise NotImplementedError

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        raise RuntimeError("refresh failed")

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        return models


def test_env_oauth_credentials_use_generic_provider_prefix_only() -> None:
    env = {
        "DEMO_ACCESS_TOKEN": "demo-token",
        "DEMO_ACCOUNT_ID": "demo-account",
        "DEMO_PLAN": "team",
        "CHATGPT_ACCESS_TOKEN": "chatgpt-token",
    }

    credentials = get_env_oauth_credentials("demo", env=env)

    assert credentials is not None
    assert credentials.access_token == "demo-token"
    assert credentials.extra == {"account_id": "demo-account", "plan": "team"}
    assert get_env_oauth_credentials("openai-codex", env=env) is None


def test_oauth_refresh_failure_does_not_fall_back_to_api_key() -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    registry.register(_FailingRefreshProvider(), source_id="test")
    try:
        model = SimpleNamespace(
            provider_id="demo",
            endpoint_id="demo",
            id="model-a",
            auth=AuthConfig(api_key_env="DEMO_API_KEY"),
        )
        options = SimpleNamespace(
            oauth_credentials={
                "demo": OAuthCredentials(
                    provider="demo",
                    access_token="expired",
                    refresh_token="refresh",
                    expires_at=0.0,
                )
            },
            api_key="fallback-key",
        )

        with pytest.raises(RuntimeError, match="refresh failed"):
            resolve_auth_for_model(model, options=options)
    finally:
        registry.clear()


def test_env_oauth_refresh_failure_does_not_fall_back_to_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    registry.register(_FailingRefreshProvider(), source_id="test")
    monkeypatch.setattr(
        "loushang.ai.auth.env.get_env_oauth_credentials",
        lambda provider, env=None: OAuthCredentials(
            provider=provider,
            access_token="expired",
            refresh_token="refresh",
            expires_at=0.0,
        ),
    )
    try:
        model = SimpleNamespace(
            provider_id="demo",
            endpoint_id="demo",
            id="model-a",
            auth=AuthConfig(api_key_env="DEMO_API_KEY"),
        )

        with pytest.raises(RuntimeError, match="refresh failed"):
            resolve_auth_for_model(model, env={"DEMO_API_KEY": "fallback-key"})
    finally:
        registry.clear()


def test_stored_oauth_refresh_failure_does_not_fall_back_to_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    registry.register(_FailingRefreshProvider(), source_id="test")
    monkeypatch.setattr(
        "loushang.ai.auth.storage.load_credential_store",
        lambda: {
            "providers": {
                "demo": OAuthCredentials(
                    provider="demo",
                    access_token="expired",
                    refresh_token="refresh",
                    expires_at=0.0,
                )
            },
            "endpoints": {},
            "models": {},
        },
    )
    try:
        model = SimpleNamespace(
            provider_id="demo",
            endpoint_id="demo",
            id="model-a",
            auth=AuthConfig(api_key_env="DEMO_API_KEY"),
        )

        with pytest.raises(RuntimeError, match="refresh failed"):
            resolve_auth_for_model(model, env={"DEMO_API_KEY": "fallback-key"})
    finally:
        registry.clear()


def test_empty_oauth_credentials_do_not_block_api_key_fallback() -> None:
    model = SimpleNamespace(
        provider_id="demo",
        endpoint_id="demo",
        id="model-a",
        auth=AuthConfig(api_key_env="DEMO_API_KEY"),
    )
    options = SimpleNamespace(
        oauth_credentials={
            "demo": OAuthCredentials(provider="demo", access_token="  ")
        },
        api_key="fallback-key",
    )

    view = resolve_auth_for_model(model, options=options)

    assert view.headers["Authorization"] == "Bearer fallback-key"


def test_auth_config_is_model_auth_type() -> None:
    assert AuthConfig is Auth


def test_auth_resolution_uses_model_effective_auth_without_registry_lookup() -> None:
    model = Model(
        id="ad-hoc",
        provider="demo",
        endpoint="responses",
        auth=Auth(header="X-API-Key", prefix="", api_key_env="DEMO_API_KEY"),
    )

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(api_key="secret"),
    )

    assert view.headers == {"X-API-Key": "secret"}


def test_loaded_model_holds_effective_provider_endpoint_auth() -> None:
    endpoint = Endpoint(
        id="responses",
        provider="demo",
        api="openai-responses",
        auth=Auth(extra_headers={"X-Endpoint": "endpoint"}),
        models={"ad-hoc": Model(id="ad-hoc", provider="demo", endpoint="responses")},
    )
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=Auth(header="X-Provider", prefix="Token "),
                endpoints={endpoint.id: endpoint},
            )
        }
    )
    model = registry.get_model("demo", "responses", "ad-hoc")

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(api_key="secret"),
    )

    assert view.headers == {
        "X-Provider": "Token secret",
        "X-Endpoint": "endpoint",
    }

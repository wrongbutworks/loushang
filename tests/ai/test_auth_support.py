from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def test_oauth_refresh_failure_does_not_fall_back_to_api_key() -> None:
    registry = get_default_oauth_registry()
    registry.reset_oauth_providers()
    registry.register_oauth_provider(_FailingRefreshProvider(), source_id="test")
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
        registry.reset_oauth_providers()


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


def test_provider_auth_applies_to_ad_hoc_model_on_registered_endpoint() -> None:
    endpoint = Endpoint(
        id="responses",
        provider="demo",
        api="openai-responses",
        models={},
    )
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=Auth(header="X-API-Key", prefix="", api_key_env="DEMO_API_KEY"),
                endpoints={endpoint.id: endpoint},
            )
        }
    )
    model = Model(id="ad-hoc", provider="demo", endpoint="responses")

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(api_key="secret"),
        registry=registry,
    )

    assert view.headers == {"X-API-Key": "secret"}


def test_partial_endpoint_auth_does_not_reset_provider_header() -> None:
    endpoint = Endpoint(
        id="responses",
        provider="demo",
        api="openai-responses",
        auth=Auth(extra_headers={"X-Endpoint": "endpoint"}),
        models={},
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
    model = Model(id="ad-hoc", provider="demo", endpoint="responses")

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(api_key="secret"),
        registry=registry,
    )

    assert view.headers == {
        "X-Provider": "Token secret",
        "X-Endpoint": "endpoint",
    }

from __future__ import annotations

import asyncio

import pytest

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.auth.registry import OAuthProviderRegistry
from loushang.ai.model import Endpoint, Model, Provider
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.coding.control import ModelRegistry
from loushang.coding.session.extension_provider_controller import (
    ExtensionProviderController,
)


class _ApiProvider:
    api = "proxy-api"

    async def invoke_raw(self, request):
        del request
        await asyncio.sleep(0)
        yield {"type": "response_done"}

    async def stream_simple(self, model, context, options, request):
        return await asyncio.sleep(0)


class _OAuthProvider:
    id = "proxy-oauth"


def test_extension_provider_controller_registers_native_provider_against_existing_provider() -> (
    None
):
    ai_registry = AiModelRegistry()
    ai_registry.register_provider(
        Provider(
            id="proxy",
            name="Existing Proxy",
            endpoints={
                "proxy-simple": Endpoint(
                    id="proxy-simple",
                    provider="proxy",
                    api="proxy-api",
                    base_url="https://old.example.com",
                    models={
                        "old-model": Model(
                            id="old-model",
                            provider="proxy",
                            endpoint="proxy-simple",
                            name="Old Model",
                        ),
                    },
                )
            },
        )
    )
    controller = ExtensionProviderController(
        model_registry=ModelRegistry(ai_registry=ai_registry),
        api_provider_registry=ApiProviderRegistry(),
        oauth_provider_registry=OAuthProviderRegistry(),
    )

    controller.register_provider(
        "proxy",
        {
            "website": "https://proxy.example.com",
            "endpoints": {
                "proxy-simple": {
                    "baseUrl": "https://new.example.com",
                },
                "proxy-advanced": {
                    "api": "proxy-api",
                    "models": {
                        "new-model": {
                            "displayName": "New Model",
                            "input": ["text", "image"],
                            "reasoning": True,
                        }
                    },
                },
            },
        },
    )

    provider = ai_registry.get_provider("proxy")
    assert provider is not None
    assert provider.name == "Existing Proxy"
    assert provider.website == "https://proxy.example.com"
    endpoint = ai_registry.get_endpoint("proxy", "proxy-simple")
    assert endpoint is not None
    assert endpoint.api == "proxy-api"
    assert endpoint.base_url == "https://new.example.com"
    assert (
        ai_registry.get_model("proxy", "proxy-simple", "old-model").name == "Old Model"
    )
    new_model = ai_registry.get_model("proxy", "proxy-advanced", "new-model")
    assert new_model.name == "New Model"
    assert new_model.supports_image_input is True
    assert new_model.supports_thinking is True


def test_extension_provider_controller_registers_canonical_endpoint_auth() -> None:
    ai_registry = AiModelRegistry()
    controller = ExtensionProviderController(
        model_registry=ModelRegistry(ai_registry=ai_registry),
        api_provider_registry=ApiProviderRegistry(),
        oauth_provider_registry=OAuthProviderRegistry(),
    )

    controller.register_provider(
        "proxy",
        {
            "endpoints": {
                "proxy-simple": {
                    "api": "proxy-api",
                    "auth": {
                        "kind": "apiKey",
                        "apiKeyEnv": "PROXY_API_KEY",
                        "extraHeaders": {"x-proxy": "yes"},
                    },
                }
            },
        },
    )

    endpoint = ai_registry.get_endpoint("proxy", "proxy-simple")
    assert endpoint is not None
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "PROXY_API_KEY"
    assert endpoint.auth.extra_headers == {"x-proxy": "yes"}


def test_extension_provider_controller_unregisters_provider_and_source_registrations() -> (
    None
):
    ai_registry = AiModelRegistry({"proxy": Provider(id="proxy")})
    api_registry = ApiProviderRegistry()
    oauth_registry = OAuthProviderRegistry()
    api_registry.register_api_provider(_ApiProvider(), source_id="provider:proxy")
    oauth_registry.register(_OAuthProvider(), source_id="provider:proxy")
    controller = ExtensionProviderController(
        model_registry=ModelRegistry(ai_registry=ai_registry),
        api_provider_registry=api_registry,
        oauth_provider_registry=oauth_registry,
    )

    controller.unregister_provider("proxy")

    assert ai_registry.get_provider("proxy") is None
    assert api_registry.list_api_providers() == []
    assert oauth_registry.list() == []


def test_extension_provider_controller_rejects_pi_style_provider_config() -> None:
    controller = ExtensionProviderController(
        model_registry=ModelRegistry(ai_registry=AiModelRegistry()),
        api_provider_registry=ApiProviderRegistry(),
        oauth_provider_registry=OAuthProviderRegistry(),
    )

    with pytest.raises(ValueError, match="pi-style flat provider config"):
        controller.register_provider(
            "proxy",
            {
                "api": "proxy-api",
                "baseUrl": "https://proxy.example.com",
                "models": [{"id": "proxy-model"}],
            },
        )

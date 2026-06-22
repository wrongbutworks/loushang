from __future__ import annotations

from loushang.ai.api_registry import (
    ApiProviderRegistry,
    RegisteredApiProvider,
    get_default_api_provider_registry,
)
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.provider.protocol import RequestAwareApiProvider


def _api_provider_registry() -> ApiProviderRegistry:
    return get_default_api_provider_registry()


def register_api_provider(
    provider: RegisteredApiProvider, *, source_id: str | None = None
) -> None:
    _api_provider_registry().register_api_provider(provider, source_id=source_id)


def get_api_provider(api: str) -> RequestAwareApiProvider:
    return _api_provider_registry().get_api_provider(api)


def list_api_providers() -> list[RequestAwareApiProvider]:
    return _api_provider_registry().list_api_providers()


def clear_api_providers() -> None:
    _api_provider_registry().clear_api_providers()


def reset_api_providers(
    *,
    anthropic_base_url: str | None = None,
    openai_base_url: str | None = None,
) -> None:
    clear_api_providers()
    register_builtin_ai_providers(
        _api_provider_registry(),
        anthropic_base_url=anthropic_base_url,
        openai_base_url=openai_base_url,
    )


__all__ = [
    "ApiProviderRegistry",
    "RegisteredApiProvider",
    "clear_api_providers",
    "get_api_provider",
    "get_default_api_provider_registry",
    "list_api_providers",
    "register_builtin_ai_providers",
    "register_api_provider",
    "reset_api_providers",
]

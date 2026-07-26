from __future__ import annotations

from loushang.ai.api_registry import (
    ApiProvider,
    ApiProviderRegistry,
    APIRegistry,
    RegisteredAPIAdapter,
    RegisteredApiProvider,
    get_default_api_provider_registry,
    get_default_api_registry,
)
from loushang.ai.bootstrap import (
    register_builtin_ai_providers,
    register_builtin_api_adapters,
)
from loushang.ai.provider.protocol import APIAdapter
from loushang.ai.provider_registry import (
    ProviderRegistry,
    get_default_provider_registry,
)


def _api_registry() -> APIRegistry:
    return get_default_api_registry()


def register_api_provider(
    provider: RegisteredApiProvider, *, source_id: str | None = None
) -> None:
    _api_registry().register_api_provider(provider, source_id=source_id)


def register_api_adapter(
    adapter: RegisteredAPIAdapter, *, source_id: str | None = None
) -> None:
    _api_registry().register_api_adapter(adapter, source_id=source_id)


def register_provider_adapter(
    provider_id: str,
    api: str,
    adapter: APIAdapter,
    *,
    source_id: str | None = None,
) -> None:
    get_default_provider_registry().register_provider_adapter(
        provider_id,
        api,
        adapter,
        source_id=source_id,
    )


def get_api_provider(api: str) -> ApiProvider:
    return _api_registry().get_api_provider(api)


def get_api_adapter(api: str) -> APIAdapter:
    return _api_registry().get_api_adapter(api)


def list_api_providers() -> list[ApiProvider]:
    return _api_registry().list_api_providers()


def list_api_adapters() -> list[APIAdapter]:
    return _api_registry().list_api_adapters()


def clear_api_providers() -> None:
    _api_registry().clear_api_providers()


def clear_api_adapters() -> None:
    _api_registry().clear_api_adapters()


def reset_api_providers() -> None:
    clear_api_providers()
    register_builtin_ai_providers(_api_registry())


def reset_api_adapters() -> None:
    clear_api_adapters()
    register_builtin_api_adapters(_api_registry())


__all__ = [
    "APIAdapter",
    "APIRegistry",
    "ApiProviderRegistry",
    "ProviderRegistry",
    "RegisteredAPIAdapter",
    "RegisteredApiProvider",
    "clear_api_adapters",
    "clear_api_providers",
    "get_api_adapter",
    "get_api_provider",
    "get_default_api_registry",
    "get_default_api_provider_registry",
    "get_default_provider_registry",
    "list_api_adapters",
    "list_api_providers",
    "register_api_adapter",
    "register_builtin_api_adapters",
    "register_builtin_ai_providers",
    "register_api_provider",
    "register_provider_adapter",
    "reset_api_adapters",
    "reset_api_providers",
]

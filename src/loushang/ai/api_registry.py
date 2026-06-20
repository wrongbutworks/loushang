from __future__ import annotations

from typing import Any, cast

from loushang.ai.provider.invocation import _RequestAwareProviderInvoker
from loushang.ai.provider.protocol import ApiProvider, RequestAwareApiProvider

RegisteredApiProvider = ApiProvider | RequestAwareApiProvider

__all__ = [
    "ApiProviderRegistry",
    "RegisteredApiProvider",
    "get_default_api_provider_registry",
]


class ApiProviderRegistry:
    def __init__(self) -> None:
        # api -> (request-aware invoker, source_id)
        self._providers: dict[str, tuple[RequestAwareApiProvider, str | None]] = {}

    def register_api_provider(
        self, provider: RegisteredApiProvider, *, source_id: str | None = None
    ) -> None:
        provider_any = cast(Any, provider)
        required = ("api", "stream", "stream_simple")
        for name in required:
            if not hasattr(provider_any, name):
                raise TypeError(f"Provider missing required attribute: {name}")
        for name in ("stream", "stream_simple"):
            if not callable(getattr(provider_any, name)):
                raise TypeError(f"Provider attribute must be callable: {name}")
        self._providers[provider_any.api] = (
            _RequestAwareProviderInvoker(provider_any),
            source_id,
        )

    def get_api_provider(self, api: str) -> RequestAwareApiProvider:
        return self._providers[api][0]

    def list_api_providers(self) -> list[RequestAwareApiProvider]:
        return [entry[0] for entry in self._providers.values()]

    def unregister_api_providers(self, source_id: str) -> None:
        """Unregister all providers that were registered with the given source identifier."""
        to_delete: list[str] = []
        for api, (_wrapped, sid) in self._providers.items():
            if sid == source_id:
                to_delete.append(api)
        for api in to_delete:
            del self._providers[api]

    def clear_api_providers(self) -> None:
        """Clear all registered API providers."""
        self._providers.clear()


_default_api_provider_registry: ApiProviderRegistry | None = None


def get_default_api_provider_registry() -> ApiProviderRegistry:
    global _default_api_provider_registry
    if _default_api_provider_registry is None:
        _default_api_provider_registry = ApiProviderRegistry()
    return _default_api_provider_registry

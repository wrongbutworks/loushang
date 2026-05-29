from __future__ import annotations

from loushang.ai.model.registry import resolve_model_api
from loushang.ai.provider.protocol import ApiProvider


class _ApiCheckedProvider:
    def __init__(self, provider: ApiProvider) -> None:
        self._provider = provider
        self.api = provider.api

    def _check_model_api(self, model) -> None:
        model_api = resolve_model_api(model)
        if model_api != self.api:
            raise ValueError(
                f"Mismatched api: provider={self.api!r} endpoint.api={model_api!r}"
            )

    async def stream(self, model, context, options):
        self._check_model_api(model)
        return await self._provider.stream(model, context, options)

    async def stream_simple(self, model, context, options):
        self._check_model_api(model)
        return await self._provider.stream_simple(model, context, options)


class ApiProviderRegistry:
    def __init__(self) -> None:
        # api -> (wrapped_provider, source_id)
        self._providers: dict[str, tuple[_ApiCheckedProvider, str | None]] = {}

    def register_api_provider(
        self, provider: ApiProvider, *, source_id: str | None = None
    ) -> None:
        required = ("api", "stream", "stream_simple")
        for name in required:
            if not hasattr(provider, name):
                raise TypeError(f"Provider missing required attribute: {name}")
        for name in ("stream", "stream_simple"):
            if not callable(getattr(provider, name)):
                raise TypeError(f"Provider attribute must be callable: {name}")
        self._providers[provider.api] = (_ApiCheckedProvider(provider), source_id)

    def get_api_provider(self, api: str) -> _ApiCheckedProvider:
        return self._providers[api][0]

    def list_api_providers(self) -> list[_ApiCheckedProvider]:
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

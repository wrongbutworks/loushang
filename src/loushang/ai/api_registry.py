from __future__ import annotations

from typing import Any, cast

from loushang.ai.provider.invocation import (
    validate_provider_invoke_raw_contract,
    validate_provider_request_validator_contract,
)
from loushang.ai.provider.protocol import APIAdapter, ApiProvider

RegisteredAPIAdapter = APIAdapter
RegisteredApiProvider = RegisteredAPIAdapter

__all__ = [
    "APIRegistry",
    "RegisteredAPIAdapter",
    "ApiProviderRegistry",
    "RegisteredApiProvider",
    "get_default_api_registry",
    "get_default_api_provider_registry",
]


def _validate_api_adapter(adapter: RegisteredAPIAdapter) -> str:
    adapter_any = cast(Any, adapter)
    required = ("api", "invoke_raw")
    for name in required:
        if not hasattr(adapter_any, name):
            raise TypeError(f"API adapter missing required attribute: {name}")
    if not callable(adapter_any.invoke_raw):
        raise TypeError("API adapter attribute must be callable: invoke_raw")
    api = adapter_any.api
    if not isinstance(api, str) or not api:
        raise TypeError("API adapter api must be a non-empty string")
    validate_provider_invoke_raw_contract(adapter_any)
    validate_provider_request_validator_contract(adapter_any)
    return api


class APIRegistry:
    def __init__(self) -> None:
        # api -> (protocol adapter, source_id)
        self._adapters: dict[str, tuple[APIAdapter, str | None]] = {}

    def register_api_adapter(
        self, adapter: RegisteredAPIAdapter, *, source_id: str | None = None
    ) -> None:
        api = _validate_api_adapter(adapter)
        if api in self._adapters:
            raise ValueError(f"API adapter already registered: {api}")
        self._adapters[api] = (adapter, source_id)

    def register_api_provider(
        self, provider: RegisteredApiProvider, *, source_id: str | None = None
    ) -> None:
        """Compatibility spelling for :meth:`register_api_adapter`."""

        self.register_api_adapter(provider, source_id=source_id)

    def get_api_adapter(self, api: str) -> APIAdapter:
        return self._adapters[api][0]

    def get_api_provider(self, api: str) -> ApiProvider:
        """Compatibility spelling for :meth:`get_api_adapter`."""

        return self.get_api_adapter(api)

    def list_api_adapters(self) -> list[APIAdapter]:
        return [entry[0] for entry in self._adapters.values()]

    def list_api_providers(self) -> list[ApiProvider]:
        """Compatibility spelling for :meth:`list_api_adapters`."""

        return self.list_api_adapters()

    def unregister_api_adapters(self, source_id: str) -> None:
        """Unregister adapters registered with the given source identifier."""

        to_delete: list[str] = []
        for api, (_adapter, sid) in self._adapters.items():
            if sid == source_id:
                to_delete.append(api)
        for api in to_delete:
            del self._adapters[api]

    def unregister_api_providers(self, source_id: str) -> None:
        """Compatibility spelling for :meth:`unregister_api_adapters`."""

        self.unregister_api_adapters(source_id)

    def clear_api_adapters(self) -> None:
        self._adapters.clear()

    def clear_api_providers(self) -> None:
        """Compatibility spelling for :meth:`clear_api_adapters`."""

        self.clear_api_adapters()


ApiProviderRegistry = APIRegistry

_default_api_registry: APIRegistry | None = None


def get_default_api_registry() -> APIRegistry:
    global _default_api_registry
    if _default_api_registry is None:
        _default_api_registry = APIRegistry()
    return _default_api_registry


def get_default_api_provider_registry() -> APIRegistry:
    """Compatibility spelling for :func:`get_default_api_registry`."""

    return get_default_api_registry()

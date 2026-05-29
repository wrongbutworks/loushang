from __future__ import annotations

from typing import Dict, Tuple

from loushang.ai.auth.types import OAuthProviderInterface


class OAuthProviderRegistry:
    def __init__(self) -> None:
        # id -> (provider, source_id)
        self._providers: Dict[str, Tuple[OAuthProviderInterface, str | None]] = {}

    def register_oauth_provider(
        self, provider: OAuthProviderInterface, *, source_id: str | None = None
    ) -> None:
        self._providers[provider.id] = (provider, source_id)

    def get_oauth_provider(self, provider_id: str) -> OAuthProviderInterface | None:
        entry = self._providers.get(provider_id)
        return entry[0] if entry else None

    def list_oauth_providers(self) -> list[OAuthProviderInterface]:
        return [p for p, _ in self._providers.values()]

    def unregister_oauth_providers(self, source_id: str) -> None:
        to_delete: list[str] = []
        for pid, (_p, sid) in self._providers.items():
            if sid == source_id:
                to_delete.append(pid)
        for pid in to_delete:
            del self._providers[pid]

    def reset_oauth_providers(self) -> None:
        self._providers.clear()


_default_oauth_registry: OAuthProviderRegistry | None = None


def get_default_oauth_registry() -> OAuthProviderRegistry:
    global _default_oauth_registry
    if _default_oauth_registry is None:
        _default_oauth_registry = OAuthProviderRegistry()
    return _default_oauth_registry

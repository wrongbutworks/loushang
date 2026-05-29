from __future__ import annotations

from typing import Mapping

from loushang.ai.auth.oauth import GetOAuthApiKeyResult
from loushang.ai.auth.providers.anthropic import AnthropicOAuthProvider
from loushang.ai.auth.providers.openai_codex import OpenAICodexOAuthProvider
from loushang.ai.auth.registry import OAuthProviderRegistry, get_default_oauth_registry
from loushang.ai.auth.storage import load_credentials, save_credentials
from loushang.ai.auth.types import (
    OAuthCredentials,
    OAuthLoginCallbacks,
    OAuthProviderInterface,
)


def register_oauth_provider(
    provider: OAuthProviderInterface,
    *,
    source_id: str | None = None,
    registry: OAuthProviderRegistry | None = None,
) -> None:
    resolved_registry = registry or get_default_oauth_registry()
    resolved_registry.register_oauth_provider(provider, source_id=source_id)


def get_oauth_provider(
    provider_id: str,
    *,
    registry: OAuthProviderRegistry | None = None,
) -> OAuthProviderInterface | None:
    resolved_registry = registry or get_default_oauth_registry()
    return resolved_registry.get_oauth_provider(provider_id)


def list_oauth_providers(
    *, registry: OAuthProviderRegistry | None = None
) -> list[OAuthProviderInterface]:
    resolved_registry = registry or get_default_oauth_registry()
    return resolved_registry.list_oauth_providers()


def clear_oauth_providers(*, registry: OAuthProviderRegistry | None = None) -> None:
    resolved_registry = registry or get_default_oauth_registry()
    resolved_registry.reset_oauth_providers()


def register_builtin_oauth_providers(
    *, registry: OAuthProviderRegistry | None = None
) -> None:
    resolved_registry = registry or get_default_oauth_registry()
    resolved_registry.reset_oauth_providers()
    _register_builtin_oauth_providers(resolved_registry)


def _register_builtin_oauth_providers(registry: OAuthProviderRegistry) -> None:
    _register_builtin_anthropic(registry)
    _register_builtin_openai_codex(registry)


def _register_builtin_anthropic(
    registry: OAuthProviderRegistry,
) -> OAuthProviderInterface:
    provider = AnthropicOAuthProvider()
    registry.register_oauth_provider(provider, source_id="builtin")
    return provider


def _register_builtin_openai_codex(
    registry: OAuthProviderRegistry,
) -> OAuthProviderInterface:
    provider = OpenAICodexOAuthProvider()
    registry.register_oauth_provider(provider, source_id="builtin")
    return provider


def reset_oauth_providers(
    *,
    registry: OAuthProviderRegistry | None = None,
    with_builtins: bool = True,
) -> None:
    resolved_registry = registry or get_default_oauth_registry()
    resolved_registry.reset_oauth_providers()
    if with_builtins:
        _register_builtin_oauth_providers(resolved_registry)


async def oauth_login(
    provider_id: str,
    callbacks: OAuthLoginCallbacks,
    *,
    registry: OAuthProviderRegistry | None = None,
    credentials: Mapping[str, OAuthCredentials] | None = None,
    persist: bool = True,
) -> OAuthCredentials:
    provider = get_oauth_provider(provider_id, registry=registry)
    if provider is None:
        raise ValueError(f"OAuth provider not found: {provider_id}")
    next_credentials = await provider.login(callbacks)
    if persist:
        stored = dict(credentials or load_credentials())
        stored[provider_id] = next_credentials
        save_credentials(stored)
    return next_credentials


async def oauth_refresh(
    provider_id: str,
    credentials: OAuthCredentials | None = None,
    *,
    registry: OAuthProviderRegistry | None = None,
    persist: bool = True,
) -> OAuthCredentials:
    provider = get_oauth_provider(provider_id, registry=registry)
    if provider is None:
        raise ValueError(f"OAuth provider not found: {provider_id}")
    stored = load_credentials() if (persist or credentials is None) else {}
    current = credentials or stored.get(provider_id)
    if current is None:
        raise ValueError(f"OAuth credentials not found for provider: {provider_id}")
    refreshed = await provider.refresh_token(current)
    if persist:
        stored[provider_id] = refreshed
        save_credentials(stored)
    return refreshed


def resolve_oauth_api_key(
    provider_id: str,
    *,
    credentials: Mapping[str, OAuthCredentials] | None = None,
    persist_refresh: bool = True,
) -> GetOAuthApiKeyResult | None:
    stored = dict(credentials or load_credentials())
    from loushang.ai.auth.oauth import get_oauth_api_key

    result = get_oauth_api_key(provider_id, stored)
    if result is None:
        return None
    if persist_refresh:
        stored[provider_id] = result["newCredentials"]
        save_credentials(stored)
    return result

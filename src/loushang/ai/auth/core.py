from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from loushang.ai.auth.credentials import OAuthCredential
from loushang.ai.auth.errors import InvalidCredentialError
from loushang.ai.auth.oauth.base import AuthorizationCallback, OAuthProvider
from loushang.ai.auth.store import FileCredentialStore

CredentialState = Literal["missing", "valid", "expiring", "expired"]


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    provider: str
    state: CredentialState
    expires_at: float | int | None = None
    source: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.state in {"valid", "expiring"}


_oauth_providers: dict[str, OAuthProvider] = {}
_builtins_registered = False


def register_oauth_provider(provider: OAuthProvider, *, replace: bool = False) -> None:
    _validate_provider(provider)
    if provider.id in _oauth_providers and not replace:
        raise ValueError(f"OAuth provider already registered: {provider.id}")
    _oauth_providers[provider.id] = provider


def get_oauth_provider(provider_id: str) -> OAuthProvider | None:
    _register_builtin_oauth_providers()
    return _oauth_providers.get(provider_id)


async def login(
    provider: str | OAuthProvider,
    *,
    store: FileCredentialStore | None = None,
    authorize: AuthorizationCallback | None = None,
) -> OAuthCredential:
    adapter = _resolve_provider(provider)
    credential = await adapter.login(authorize=authorize)
    _validate_provider_credential(adapter, credential)
    (store or FileCredentialStore()).save(credential)
    return credential


async def logout(
    provider: str | OAuthProvider,
    *,
    store: FileCredentialStore | None = None,
    revoke: bool = True,
) -> bool:
    adapter = _resolve_provider(provider)
    resolved_store = store or FileCredentialStore()
    credential = resolved_store.load(adapter.id)
    if credential is None:
        return False
    if revoke:
        await adapter.revoke(credential)
    return resolved_store.delete(adapter.id)


def credential_status(
    provider: str | OAuthProvider,
    *,
    store: FileCredentialStore | None = None,
    refresh_window_seconds: float = 60.0,
    now: float | None = None,
) -> CredentialStatus:
    adapter = _resolve_provider(provider)
    resolved_store = store or FileCredentialStore()
    credential = resolved_store.load(adapter.id)
    source = "default_store"
    if credential is None:
        loader = getattr(adapter, "load_external_credential", None)
        if callable(loader):
            credential = loader()
            source = "provider_external"
    if credential is None:
        return CredentialStatus(provider=adapter.id, state="missing")
    _validate_provider_credential(adapter, credential)
    timestamp = time.time() if now is None else now
    if credential.is_expired(now=timestamp):
        state: CredentialState = "expired"
    elif credential.expires_within(refresh_window_seconds, now=timestamp):
        state = "expiring"
    else:
        state = "valid"
    return CredentialStatus(
        provider=adapter.id,
        state=state,
        expires_at=credential.expires_at,
        source=source,
    )


def _resolve_provider(provider: str | OAuthProvider) -> OAuthProvider:
    if isinstance(provider, str):
        adapter = get_oauth_provider(provider)
        if adapter is None:
            raise KeyError(f"OAuth provider is not registered: {provider}")
        return adapter
    _validate_provider(provider)
    return provider


def _validate_provider(provider: OAuthProvider) -> None:
    if (
        not isinstance(getattr(provider, "id", None), str)
        or not provider.id.strip()
        or not callable(getattr(provider, "login", None))
        or not callable(getattr(provider, "refresh", None))
        or not callable(getattr(provider, "revoke", None))
    ):
        raise TypeError("OAuth provider must define id, login, refresh, and revoke")


def _validate_provider_credential(
    provider: OAuthProvider,
    credential: OAuthCredential,
) -> None:
    if not isinstance(credential, OAuthCredential):
        raise InvalidCredentialError(
            "OAuth provider returned an unsupported credential type.",
            provider=provider.id,
            details={"recovery": "reconfigure"},
        )
    if credential.provider != provider.id:
        raise InvalidCredentialError(
            "OAuth provider returned a credential for a different provider.",
            provider=provider.id,
            details={
                "credential_provider": credential.provider,
                "recovery": "reconfigure",
            },
        )


def _register_builtin_oauth_providers() -> None:
    global _builtins_registered
    if _builtins_registered:
        return
    from loushang.ai.auth.oauth.providers import (
        KimiCodeOAuthProvider,
        OpenAICodexOAuthProvider,
    )

    for provider in (OpenAICodexOAuthProvider(), KimiCodeOAuthProvider()):
        _oauth_providers.setdefault(provider.id, provider)
    _builtins_registered = True


__all__ = [
    "CredentialState",
    "CredentialStatus",
    "credential_status",
    "get_oauth_provider",
    "login",
    "logout",
    "register_oauth_provider",
]

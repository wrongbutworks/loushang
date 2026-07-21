from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from loushang.ai.auth.credentials import OAuthCredential
from loushang.ai.auth.errors import InvalidCredentialError
from loushang.ai.auth.oauth.base import AuthorizationCallback, OAuthProvider
from loushang.ai.auth.sources import get_credential_source
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


def register_oauth_provider(provider: OAuthProvider, *, replace: bool = False) -> None:
    _validate_provider(provider)
    if provider.id in _oauth_providers and not replace:
        raise ValueError(f"OAuth provider already registered: {provider.id}")
    _oauth_providers[provider.id] = provider


def get_oauth_provider(provider_id: str) -> OAuthProvider | None:
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
    if isinstance(provider, str):
        provider_id = provider
        adapter = get_oauth_provider(provider_id)
        source_adapter = get_credential_source(provider_id)
        if adapter is None and source_adapter is None:
            raise KeyError(
                "OAuth provider or credential source is not registered: "
                f"{provider_id}"
            )
    else:
        _validate_provider(provider)
        provider_id = provider.id
        source_adapter = get_credential_source(provider_id)
    resolved_store = store or FileCredentialStore()
    credential = resolved_store.load(provider_id)
    source = "default_store"
    if credential is None and source_adapter is not None:
        credential = source_adapter.load()
        source = "credential_source"
    if credential is None:
        return CredentialStatus(provider=provider_id, state="missing")
    _validate_credential_owner(provider_id, credential)
    timestamp = time.time() if now is None else now
    if credential.is_expired(now=timestamp):
        state: CredentialState = "expired"
    elif credential.expires_within(refresh_window_seconds, now=timestamp):
        state = "expiring"
    else:
        state = "valid"
    return CredentialStatus(
        provider=provider_id,
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
    _validate_credential_owner(provider.id, credential)


def _validate_credential_owner(
    provider_id: str,
    credential: OAuthCredential,
) -> None:
    if not isinstance(credential, OAuthCredential):
        raise InvalidCredentialError(
            "Authentication component returned an unsupported credential type.",
            provider=provider_id,
            details={"recovery": "reconfigure"},
        )
    if credential.provider != provider_id:
        raise InvalidCredentialError(
            "Authentication component returned a credential for a different provider.",
            provider=provider_id,
            details={
                "credential_provider": credential.provider,
                "recovery": "reconfigure",
            },
        )


__all__ = [
    "CredentialState",
    "CredentialStatus",
    "credential_status",
    "get_oauth_provider",
    "login",
    "logout",
    "register_oauth_provider",
]

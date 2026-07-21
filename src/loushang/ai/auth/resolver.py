from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from loushang.ai.auth.core import get_oauth_provider
from loushang.ai.auth.credentials import (
    AuthCredential,
    OAuthCredential,
)
from loushang.ai.auth.errors import (
    CredentialExpiredError,
    InvalidCredentialError,
    MissingCredentialError,
    RefreshFailedError,
)
from loushang.ai.auth.oauth.base import OAuthProvider
from loushang.ai.auth.store import (
    FileCredentialStore,
    load_credential_file,
    save_credential_file,
)
from loushang.ai.auth.support import normalize_auth_kind, resolve_api_key_auth


@dataclass(frozen=True, slots=True)
class _ResolvedCredential:
    credential: OAuthCredential
    source: str
    path: Path | None = None


async def resolve_auth(
    model,
    *,
    options=None,
    credential: OAuthCredential | None = None,
    credential_file: str | Path | None = None,
    store: FileCredentialStore | None = None,
    providers: Mapping[str, OAuthProvider] | None = None,
    env: Mapping[str, str] | None = None,
    refresh_window_seconds: float = 60.0,
    now: float | None = None,
) -> AuthCredential | None:
    """Resolve request auth by explicit-auth, credential, file, store, then env."""

    declaration = getattr(model, "auth", None)
    explicit_auth = getattr(options, "auth", None) if options is not None else None
    if explicit_auth is not None:
        return explicit_auth

    explicit_credential = credential
    if explicit_credential is None and options is not None:
        explicit_credential = getattr(options, "credential", None)
    explicit_file = credential_file
    if explicit_file is None and options is not None:
        explicit_file = getattr(options, "credential_file", None)

    kind = normalize_auth_kind(getattr(declaration, "kind", None))
    if declaration is None or kind == "none":
        if explicit_credential is None and explicit_file is None:
            return None
        kind = "oauth"
    if kind == "api_key":
        if explicit_credential is not None or explicit_file is not None:
            raise InvalidCredentialError(
                "OAuth credentials cannot authenticate a model configured for API key auth.",
                provider=getattr(model, "provider_id", None),
                endpoint=getattr(model, "endpoint_id", None),
                model=getattr(model, "id", None),
                details={"recovery": "reconfigure"},
            )
        return resolve_api_key_auth(
            declaration,
            model=model,
            env=os.environ if env is None else env,
        )
    if kind != "oauth":
        raise InvalidCredentialError(
            "Model has an unsupported authentication kind.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"auth_kind": str(kind), "recovery": "reconfigure"},
        )

    provider_id = _oauth_provider_id(model, declaration)
    resolved = _load_oauth_credential(
        provider_id,
        credential=explicit_credential,
        credential_file=explicit_file,
        store=store,
        providers=providers,
    )
    if resolved is None:
        raise MissingCredentialError(
            "Model requires OAuth login but no credential was found.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={
                "oauth_provider": provider_id,
                "recovery": "login",
            },
        )
    _validate_credential_provider(resolved.credential, provider_id, model=model)
    timestamp = time.time() if now is None else now
    prepared = await _refresh_if_needed(
        resolved,
        provider_id=provider_id,
        store=store,
        providers=providers,
        refresh_window_seconds=refresh_window_seconds,
        now=timestamp,
        model=model,
    )
    return prepared.to_auth()


def _load_oauth_credential(
    provider_id: str,
    *,
    credential: OAuthCredential | None,
    credential_file: str | Path | None,
    store: FileCredentialStore | None,
    providers: Mapping[str, OAuthProvider] | None,
) -> _ResolvedCredential | None:
    if credential is not None:
        if not isinstance(credential, OAuthCredential):
            raise InvalidCredentialError(
                "credential must be OAuthCredential.",
                details={"recovery": "reconfigure"},
            )
        return _ResolvedCredential(credential=credential, source="explicit")
    if credential_file is not None:
        path = Path(credential_file).expanduser()
        adapter = _provider_for(provider_id, providers)
        provider_loader = getattr(adapter, "load_credential_file", None)
        if callable(provider_loader):
            return _ResolvedCredential(
                credential=provider_loader(path),
                source="provider_credential_file",
                path=path,
            )
        return _ResolvedCredential(
            credential=load_credential_file(path),
            source="credential_file",
            path=path,
        )
    resolved_store = store or FileCredentialStore()
    stored = resolved_store.load(provider_id)
    if stored is not None:
        return _ResolvedCredential(credential=stored, source="default_store")
    adapter = _provider_for(provider_id, providers)
    loader = getattr(adapter, "load_external_credential", None)
    if callable(loader):
        external = loader()
        if external is not None:
            return _ResolvedCredential(
                credential=external,
                source="provider_external",
            )
    return None


async def _refresh_if_needed(
    resolved: _ResolvedCredential,
    *,
    provider_id: str,
    store: FileCredentialStore | None,
    providers: Mapping[str, OAuthProvider] | None,
    refresh_window_seconds: float,
    now: float,
    model,
) -> OAuthCredential:
    credential = resolved.credential
    if not credential.expires_within(refresh_window_seconds, now=now):
        return credential
    if credential.refresh_token is None:
        raise CredentialExpiredError(
            "OAuth credential is expired or near expiry and has no refresh token.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"oauth_provider": provider_id, "recovery": "login"},
        )
    adapter = _provider_for(provider_id, providers)
    if adapter is None:
        raise RefreshFailedError(
            "OAuth credential needs refresh but no provider adapter is registered.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"oauth_provider": provider_id, "recovery": "login"},
        )
    try:
        refreshed = await adapter.refresh(credential)
    except RefreshFailedError:
        raise
    except Exception as error:
        raise RefreshFailedError(
            "OAuth credential refresh failed.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={
                "oauth_provider": provider_id,
                "cause": type(error).__name__,
                "recovery": "login",
            },
        ) from error
    _validate_credential_provider(refreshed, provider_id, model=model)
    if refreshed.is_expired(now=now):
        raise RefreshFailedError(
            "OAuth provider returned an expired credential.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"oauth_provider": provider_id, "recovery": "login"},
        )
    if resolved.source == "credential_file" and resolved.path is not None:
        save_credential_file(resolved.path, refreshed)
    elif resolved.source == "default_store":
        (store or FileCredentialStore()).save(refreshed)
    return refreshed


def _oauth_provider_id(model, declaration) -> str:
    configured = getattr(declaration, "provider", None)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    provider_id = getattr(model, "provider_id", None)
    if not isinstance(provider_id, str) or not provider_id:
        raise InvalidCredentialError(
            "OAuth model has no provider identity.",
            details={"recovery": "reconfigure"},
        )
    return provider_id


def _provider_for(
    provider_id: str,
    providers: Mapping[str, OAuthProvider] | None,
) -> OAuthProvider | None:
    if providers is not None and provider_id in providers:
        return providers[provider_id]
    return get_oauth_provider(provider_id)


def _validate_credential_provider(
    credential: OAuthCredential,
    provider_id: str,
    *,
    model,
) -> None:
    if not isinstance(credential, OAuthCredential):
        raise InvalidCredentialError(
            "OAuth provider returned an unsupported credential.",
            details={"recovery": "reconfigure"},
        )
    if credential.provider != provider_id:
        raise InvalidCredentialError(
            "OAuth credential provider does not match the model auth provider.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={
                "credential_provider": credential.provider,
                "oauth_provider": provider_id,
                "recovery": "reconfigure",
            },
        )


__all__ = ["resolve_auth"]

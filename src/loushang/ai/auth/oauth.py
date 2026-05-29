from __future__ import annotations

import time
from typing import TypedDict

from loushang.ai.auth.types import OAuthCredentials


class GetOAuthApiKeyResult(TypedDict):
    newCredentials: OAuthCredentials
    apiKey: str


def get_oauth_api_key(
    provider: str, credentials_map: dict[str, OAuthCredentials]
) -> GetOAuthApiKeyResult | None:
    creds = credentials_map.get(provider)
    if creds is None:
        return None
    now = time.time()
    needs_refresh = creds.expires_at is not None and creds.expires_at <= now
    if needs_refresh and creds.refresh_token:
        refreshed = refresh_oauth_token(provider, creds)
        return {"newCredentials": refreshed, "apiKey": refreshed.access_token}
    return {"newCredentials": creds, "apiKey": creds.access_token}


def refresh_oauth_token(provider: str, creds: OAuthCredentials) -> OAuthCredentials:
    from loushang.ai.auth.registry import get_default_oauth_registry

    reg = get_default_oauth_registry()
    prov = reg.get_oauth_provider(provider)
    if prov is None:
        raise ValueError(f"OAuth provider not found: {provider}")
    rt = prov.refresh_token  # type: ignore[attr-defined]
    if rt is None:
        raise ValueError(f"OAuth provider does not support refresh: {provider}")
    maybe = rt(creds)
    if hasattr(maybe, "__await__"):
        import asyncio

        return asyncio.get_event_loop().run_until_complete(maybe)  # type: ignore[arg-type]
    return maybe  # type: ignore[return-value]

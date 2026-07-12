from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Awaitable
from typing import TypedDict, cast

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
    token = _non_empty_token(creds.access_token)
    if token is None:
        return None
    now = time.time()
    needs_refresh = creds.expires_at is not None and creds.expires_at <= now
    if needs_refresh and creds.refresh_token:
        refreshed = refresh_oauth_token(provider, creds)
        refreshed_token = _non_empty_token(refreshed.access_token)
        if refreshed_token is None:
            return None
        return {"newCredentials": refreshed, "apiKey": refreshed_token}
    if needs_refresh:
        return None
    return {"newCredentials": creds, "apiKey": token}


def refresh_oauth_token(provider: str, creds: OAuthCredentials) -> OAuthCredentials:
    from loushang.ai.auth.registry import get_default_oauth_registry

    reg = get_default_oauth_registry()
    prov = reg.get(provider)
    if prov is None:
        raise ValueError(f"OAuth provider not found: {provider}")
    rt = prov.refresh_token  # type: ignore[attr-defined]
    if rt is None:
        raise ValueError(f"OAuth provider does not support refresh: {provider}")
    maybe = rt(creds)
    if inspect.isawaitable(maybe):
        return _run_awaitable_sync(cast("Awaitable[OAuthCredentials]", maybe))
    return maybe  # type: ignore[return-value]


def _run_awaitable_sync(awaitable: Awaitable[OAuthCredentials]) -> OAuthCredentials:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_result(awaitable))

    result: dict[str, OAuthCredentials] = {}
    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(_await_result(awaitable))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result["value"]


async def _await_result(awaitable: Awaitable[OAuthCredentials]) -> OAuthCredentials:
    return await awaitable


def _non_empty_token(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None

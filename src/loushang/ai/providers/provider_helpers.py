from __future__ import annotations

import inspect
from collections.abc import Mapping, MutableMapping

AUTH_HEADER_KEYS = frozenset({"authorization", "x-api-key"})


def extract_sdk_api_key(
    headers: Mapping[str, str],
    *,
    error_message: str,
    prefer_x_api_key: bool = False,
) -> str:
    bearer = _bearer_token(headers)
    x_api_key = _non_empty_str(headers.get("x-api-key"))
    candidates = (x_api_key, bearer) if prefer_x_api_key else (bearer, x_api_key)
    for candidate in candidates:
        if candidate:
            return candidate
    raise ValueError(error_message)


def sdk_default_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in AUTH_HEADER_KEYS
    }


def apply_cache_key_headers(
    headers: MutableMapping[str, str],
    cache_key: str | None,
    *,
    include_session_id: bool = True,
    include_client_request_id: bool = True,
    include_affinity: bool = False,
) -> bool:
    if not isinstance(cache_key, str) or not cache_key:
        return False
    if include_session_id:
        headers["session_id"] = cache_key
    if include_client_request_id:
        headers["x-client-request-id"] = cache_key
    if include_affinity:
        headers["x-session-affinity"] = cache_key
    return True


async def close_provider_stream(stream: object) -> None:
    for name in ("aclose", "close"):
        close = getattr(stream, name, None)
        if not callable(close):
            continue
        result = close()
        if inspect.isawaitable(result):
            await result
        return


def _bearer_token(headers: Mapping[str, str]) -> str | None:
    auth = headers.get("Authorization") or headers.get("authorization")
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        return _non_empty_str(auth.split(" ", 1)[1].strip())
    return None


def _non_empty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None

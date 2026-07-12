from __future__ import annotations

import inspect
from collections.abc import Mapping, MutableMapping

_SDK_AUTH_HEADER_NAMES = {
    "authorization": "Authorization",
    "x-api-key": "X-Api-Key",
}


def canonicalize_sdk_headers(headers: Mapping[str, str]) -> dict[str, str]:
    canonicalized: dict[str, str] = {}
    for key, value in headers.items():
        set_header_case_insensitive(
            canonicalized,
            _SDK_AUTH_HEADER_NAMES.get(key.casefold(), key),
            value,
        )
    return canonicalized


def get_header_case_insensitive(
    headers: Mapping[str, str],
    name: str,
) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if key.casefold() == target:
            return value
    return None


def set_header_case_insensitive(
    headers: MutableMapping[str, str],
    name: str,
    value: str,
) -> None:
    target = name.casefold()
    for key in tuple(headers):
        if key.casefold() == target:
            del headers[key]
    headers[name] = value


def merge_headers_case_insensitive(
    *sources: Mapping[str, str],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            set_header_case_insensitive(merged, key, value)
    return merged


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
        set_header_case_insensitive(headers, "session_id", cache_key)
    if include_client_request_id:
        set_header_case_insensitive(headers, "x-client-request-id", cache_key)
    if include_affinity:
        set_header_case_insensitive(headers, "x-session-affinity", cache_key)
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

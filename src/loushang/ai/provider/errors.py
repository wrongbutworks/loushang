from __future__ import annotations

from typing import NotRequired, TypedDict


class ProviderErrorInfo(TypedDict):
    message: str
    code: NotRequired[int]


def map_provider_error(error: Exception) -> str:
    return str(error)


def classify_provider_error(
    error: Exception,
    *,
    source: str = "provider",
) -> ProviderErrorInfo:
    del source
    info: ProviderErrorInfo = {"message": str(error)}
    status_code = _http_status_code(getattr(error, "status_code", None))
    if status_code is None:
        status_code = _http_status_code(getattr(error, "status", None))
    if status_code is not None:
        info["code"] = status_code
    return info


def provider_error_part(
    error: Exception,
    *,
    source: str = "provider",
) -> dict[str, object]:
    info = classify_provider_error(error, source=source)
    return {"type": "response_error", **info}


def _http_status_code(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        code = value
    elif isinstance(value, str) and value.isdecimal():
        code = int(value)
    else:
        return None
    if is_http_status_code(code):
        return code
    return None


def is_http_status_code(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599
    )

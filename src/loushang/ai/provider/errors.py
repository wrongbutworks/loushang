from __future__ import annotations

from typing import TypedDict


class ProviderErrorInfo(TypedDict):
    message: str
    code: str
    source: str
    retryable: bool


def map_provider_error(error: Exception) -> str:
    return str(error)


def classify_provider_error(
    error: Exception,
    *,
    source: str = "provider",
) -> ProviderErrorInfo:
    status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
    name = type(error).__name__.lower()
    message = str(error)

    if status_code in {401, 403} or "auth" in name or "permission" in name:
        code = "auth_error"
        retryable = False
    elif status_code == 429 or "rate" in name:
        code = "rate_limit"
        retryable = True
    elif status_code in {408, 504} or "timeout" in name:
        code = "timeout"
        retryable = True
    elif status_code is not None and int(status_code) >= 500:
        code = "provider_error"
        retryable = True
    else:
        code = "provider_error"
        retryable = False

    return {
        "message": message,
        "code": code,
        "source": source,
        "retryable": retryable,
    }


def provider_error_part(
    error: Exception,
    *,
    source: str = "provider",
) -> dict[str, object]:
    info = classify_provider_error(error, source=source)
    return {"type": "response_error", **info}

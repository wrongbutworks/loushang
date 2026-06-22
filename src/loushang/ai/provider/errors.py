from __future__ import annotations

from collections.abc import Mapping
from typing import NotRequired, TypedDict

from loushang.ai.errors import (
    AIAuthenticationError,
    AIError,
    AIErrorCode,
    AIErrorInfo,
    AIProviderError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from loushang.observability.problem import JSONValue


class ProviderErrorInfo(TypedDict):
    message: str
    code: NotRequired[int]
    error_info: NotRequired[dict[str, JSONValue]]


_ERROR_CLASS_BY_CODE: dict[AIErrorCode, type[AIProviderError | AIAuthenticationError]] = {
    AIErrorCode.AUTHENTICATION: AIAuthenticationError,
    AIErrorCode.RATE_LIMIT: AIRateLimitError,
    AIErrorCode.TIMEOUT: AITimeoutError,
    AIErrorCode.SERVICE_UNAVAILABLE: AIServiceUnavailableError,
    AIErrorCode.PROVIDER: AIProviderError,
}


def classify_provider_error(
    error: Exception,
    *,
    source: str = "provider",
) -> ProviderErrorInfo:
    normalized = normalize_provider_error(error, source=source)
    info: ProviderErrorInfo = {
        "message": normalized.info.message,
        "error_info": normalized.info.to_dict(),
    }
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


def normalize_provider_error(
    error: Exception,
    *,
    source: str = "provider",
) -> AIError:
    status_code = _provider_status_code(error)
    code = _provider_error_code(error, status_code)
    error_type = _ERROR_CLASS_BY_CODE.get(code, AIProviderError)
    normalized = error_type(
        str(error) or error.__class__.__name__,
        source=source,
        retryable=_is_retryable_provider_error(code),
        status_code=status_code,
        details={"exceptionType": error.__class__.__name__},
    )
    normalized.__cause__ = error
    return normalized


def provider_error_info_from_raw(
    part: Mapping[str, object],
    *,
    source: str,
    provider: str | None = None,
    model: str | None = None,
) -> AIErrorInfo:
    raw_info = part.get("error_info")
    if isinstance(raw_info, Mapping):
        return _ai_error_info_from_mapping(raw_info)
    message = part.get("message")
    status_code = _http_status_code(part.get("code"))
    code = _provider_error_code_from_status(status_code)
    return AIErrorInfo(
        code=code,
        message=message if isinstance(message, str) and message else "Unknown error",
        source=source,
        retryable=_is_retryable_provider_error(code),
        provider=provider,
        model=model,
        status_code=status_code,
    )


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


def _provider_status_code(error: Exception) -> int | None:
    status_code = _http_status_code(getattr(error, "status_code", None))
    if status_code is None:
        status_code = _http_status_code(getattr(error, "status", None))
    return status_code


def _provider_error_code(error: Exception, status_code: int | None) -> AIErrorCode:
    if isinstance(error, TimeoutError):
        return AIErrorCode.TIMEOUT
    return _provider_error_code_from_status(status_code)


def _provider_error_code_from_status(status_code: int | None) -> AIErrorCode:
    if status_code in {401, 403}:
        return AIErrorCode.AUTHENTICATION
    if status_code == 408:
        return AIErrorCode.TIMEOUT
    if status_code == 429:
        return AIErrorCode.RATE_LIMIT
    if status_code is not None and 500 <= status_code <= 599:
        return AIErrorCode.SERVICE_UNAVAILABLE
    return AIErrorCode.PROVIDER


def _is_retryable_provider_error(code: AIErrorCode) -> bool:
    return code in {
        AIErrorCode.RATE_LIMIT,
        AIErrorCode.TIMEOUT,
        AIErrorCode.SERVICE_UNAVAILABLE,
    }


def _ai_error_info_from_mapping(raw: Mapping[str, object]) -> AIErrorInfo:
    details = raw.get("details")
    return AIErrorInfo(
        code=_required_str(raw, "code"),
        message=_required_str(raw, "message"),
        source=_required_str(raw, "source"),
        retryable=bool(raw.get("retryable")),
        provider=_optional_str(raw.get("provider")),
        endpoint=_optional_str(raw.get("endpoint")),
        model=_optional_str(raw.get("model")),
        status_code=_http_status_code(raw.get("statusCode")),
        request_id=_optional_str(raw.get("requestId")),
        details=details if isinstance(details, Mapping) else {},
    )


def _required_str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"error_info.{key} must be a non-empty string")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None

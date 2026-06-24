from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

from loushang.ai.errors import (
    AIAuthenticationError,
    AIError,
    AIErrorCode,
    AIErrorInfo,
    AIProviderError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
    ai_error_info_from_mapping,
)
from loushang.observability.problem import JSONValue

if TYPE_CHECKING:
    from loushang.ai.event_stream.raw_parts import RawPart, ResponseErrorPart


class ProviderErrorInfo(TypedDict):
    message: str
    code: NotRequired[int]
    error_info: NotRequired[dict[str, JSONValue]]


_ERROR_CLASS_BY_CODE: dict[
    AIErrorCode, type[AIProviderError | AIAuthenticationError]
] = {
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
) -> "RawPart":
    info = classify_provider_error(error, source=source)
    return cast("RawPart", {"type": "response_error", **info})


def provider_error_part_from_raw(
    message: object,
    *,
    code: object = None,
    source: str = "provider",
) -> "RawPart":
    message_text = message if isinstance(message, str) and message else "Unknown error"
    status_code = _http_status_code(code)
    error_code = _provider_error_code_from_raw(code, status_code)
    info = AIErrorInfo(
        code=error_code,
        message=message_text,
        source=source,
        retryable=_is_retryable_provider_error(error_code),
        status_code=status_code,
        details={"rawCode": str(code)} if code is not None else {},
    )
    part = cast(
        "ResponseErrorPart",
        {
            "type": "response_error",
            "message": message_text,
            "error_info": info.to_dict(),
        },
    )
    if status_code is not None:
        part["code"] = status_code
    return cast("RawPart", part)


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
        request_id=_provider_request_id(error),
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
        return ai_error_info_from_mapping(raw_info)
    message = part.get("message")
    status_code = _http_status_code(part.get("code"))
    code = _provider_error_code_from_raw(part.get("code"), status_code)
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


def _provider_request_id(error: Exception) -> str | None:
    for name in (
        "request_id",
        "requestId",
        "x_request_id",
        "x_requestid",
    ):
        value = getattr(error, name, None)
        if isinstance(value, str) and value:
            return value
    headers = getattr(error, "headers", None)
    request_id = _request_id_from_headers(headers)
    if request_id is not None:
        return request_id
    response = getattr(error, "response", None)
    return _request_id_from_headers(getattr(response, "headers", None))


def _request_id_from_headers(headers: object) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value:
            continue
        if key.lower() in {
            "x-request-id",
            "request-id",
            "x-ms-request-id",
            "x-amzn-requestid",
        }:
            return value
    return None


def _provider_error_code(error: Exception, status_code: int | None) -> AIErrorCode:
    if _is_timeout_exception(error):
        return AIErrorCode.TIMEOUT
    return _provider_error_code_from_status(status_code)


def _is_timeout_exception(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    for cls in type(error).__mro__:
        module = getattr(cls, "__module__", "")
        name = getattr(cls, "__name__", "")
        if name in {
            "APITimeoutError",
            "ConnectTimeout",
            "PoolTimeout",
            "ReadTimeout",
            "TimeoutException",
            "WriteTimeout",
        } and module.startswith(("anthropic", "httpcore", "httpx", "openai")):
            return True
    return False


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


def _provider_error_code_from_raw(
    raw_code: object,
    status_code: int | None,
) -> AIErrorCode:
    if status_code is not None:
        return _provider_error_code_from_status(status_code)
    if not isinstance(raw_code, str):
        return AIErrorCode.PROVIDER
    normalized = raw_code.strip().lower().replace("-", "_")
    if normalized in {"rate_limit", "rate_limited", "too_many_requests"}:
        return AIErrorCode.RATE_LIMIT
    if normalized in {"timeout", "timed_out", "request_timeout"}:
        return AIErrorCode.TIMEOUT
    if normalized in {
        "server_error",
        "service_unavailable",
        "temporarily_unavailable",
        "overloaded",
        "unavailable",
    }:
        return AIErrorCode.SERVICE_UNAVAILABLE
    if normalized in {"authentication", "authentication_error", "invalid_api_key"}:
        return AIErrorCode.AUTHENTICATION
    return AIErrorCode.PROVIDER


def _is_retryable_provider_error(code: AIErrorCode) -> bool:
    return code in {
        AIErrorCode.RATE_LIMIT,
        AIErrorCode.TIMEOUT,
        AIErrorCode.SERVICE_UNAVAILABLE,
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None

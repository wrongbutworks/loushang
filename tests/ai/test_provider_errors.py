from __future__ import annotations

import pytest

from loushang.ai import AIErrorCode
from loushang.ai.errors import (
    AIAuthenticationError,
    AIProviderProtocolError,
    AIRateLimitError,
)
from loushang.ai.provider.errors import (
    normalize_provider_error,
    provider_error_info_from_raw,
    provider_error_part,
    provider_error_part_from_raw,
)


class _HttpError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _HttpErrorWithHeaders(_HttpError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message, status_code)
        self.headers = {"x-request-id": "req_headers"}


HttpxReadTimeout = type("ReadTimeout", (Exception,), {"__module__": "httpx"})
OpenAIAPITimeoutError = type(
    "APITimeoutError",
    (Exception,),
    {"__module__": "openai"},
)
AnthropicAPITimeoutError = type(
    "APITimeoutError",
    (Exception,),
    {"__module__": "anthropic"},
)


@pytest.mark.parametrize(
    ("status_code", "code", "retryable", "message"),
    [
        (401, AIErrorCode.AUTHENTICATION, False, "Provider authentication failed."),
        (403, AIErrorCode.AUTHENTICATION, False, "Provider authentication failed."),
        (408, AIErrorCode.TIMEOUT, True, "Provider request timed out."),
        (429, AIErrorCode.RATE_LIMIT, True, "Provider rate limit exceeded."),
        (500, AIErrorCode.SERVICE_UNAVAILABLE, True, "Provider service unavailable."),
        (503, AIErrorCode.SERVICE_UNAVAILABLE, True, "Provider service unavailable."),
    ],
)
def test_provider_error_part_maps_http_status_codes_to_error_info(
    status_code: int,
    code: AIErrorCode,
    retryable: bool,
    message: str,
) -> None:
    part = provider_error_part(
        _HttpError("provider failed", status_code), source="openai"
    )

    assert part["type"] == "response_error"
    assert part["message"] == message
    assert part["code"] == status_code
    assert part["error_info"]["code"] == code.value
    assert part["error_info"]["source"] == "openai"
    assert part["error_info"]["retryable"] is retryable
    assert part["error_info"]["statusCode"] == status_code


def test_provider_error_part_maps_timeout_without_http_status() -> None:
    part = provider_error_part(TimeoutError("connection timed out"), source="openai")

    assert part["type"] == "response_error"
    assert part["message"] == "Provider request timed out."
    assert "code" not in part
    assert part["error_info"]["code"] == "timeout"
    assert part["error_info"]["retryable"] is True


@pytest.mark.parametrize(
    "error",
    [
        HttpxReadTimeout("read timed out"),
        OpenAIAPITimeoutError("request timed out"),
        AnthropicAPITimeoutError("request timed out"),
    ],
)
def test_provider_error_part_maps_sdk_timeout_exceptions(error: Exception) -> None:
    part = provider_error_part(error, source="provider")

    assert part["type"] == "response_error"
    assert part["error_info"]["code"] == "timeout"
    assert part["error_info"]["retryable"] is True


def test_provider_error_part_omits_non_http_status_code() -> None:
    part = provider_error_part(_HttpError("grpc unavailable", 14), source="openai")

    assert part["type"] == "response_error"
    assert part["message"] == "Provider request failed."
    assert "code" not in part
    assert part["error_info"]["code"] == "provider"
    assert part["error_info"]["retryable"] is False


@pytest.mark.parametrize(
    ("raw_code", "code", "retryable"),
    [
        ("rate-limited", "rate_limit", True),
        ("request_timeout", "timeout", True),
        ("overloaded", "service_unavailable", True),
        ("invalid_api_key", "authentication", False),
        ("unknown_error", "provider", False),
        (object(), "provider", False),
    ],
)
def test_provider_error_part_from_raw_maps_known_string_codes(
    raw_code: object,
    code: str,
    retryable: bool,
) -> None:
    part = provider_error_part_from_raw(
        "provider failed",
        code=raw_code,
        source="provider",
    )

    assert part["type"] == "response_error"
    assert "code" not in part
    assert part["error_info"]["code"] == code
    assert part["error_info"]["retryable"] is retryable


def test_normalize_provider_error_does_not_retain_raw_exception_text() -> None:
    original = _HttpError("Authorization: Bearer secret-token", 429)
    normalized = normalize_provider_error(original, source="openai")

    assert normalized.info.code is AIErrorCode.RATE_LIMIT
    assert normalized.info.retryable is True
    assert normalized.info.message == "Provider rate limit exceeded."
    assert normalized.__cause__ is None
    assert "secret-token" not in repr(normalized)


def test_normalize_provider_error_preserves_request_id_from_headers() -> None:
    normalized = normalize_provider_error(
        _HttpErrorWithHeaders("rate limited", 429),
        source="openai",
    )

    assert normalized.info.request_id == "req_headers"


def test_existing_authentication_error_is_forced_non_retryable() -> None:
    normalized = normalize_provider_error(
        AIAuthenticationError(
            "unsafe",
            retryable=True,
            status_code=401,
        )
    )

    assert normalized.info.code is AIErrorCode.AUTHENTICATION
    assert normalized.info.retryable is False
    assert normalized.info.message == "Provider authentication failed."


def test_existing_non_authentication_retry_policy_is_preserved() -> None:
    normalized = normalize_provider_error(
        AIRateLimitError(
            "unsafe",
            retryable=False,
            status_code=429,
        )
    )

    assert normalized.info.code is AIErrorCode.RATE_LIMIT
    assert normalized.info.retryable is False
    assert normalized.info.message == "Provider rate limit exceeded."


@pytest.mark.parametrize("status_code", [401, 403])
def test_raw_auth_error_info_cannot_override_authentication_invariants(
    status_code: int,
) -> None:
    info = provider_error_info_from_raw(
        {
            "type": "response_error",
            "code": status_code,
            "message": "Authorization: Bearer secret-token",
            "error_info": {
                "code": "service_unavailable",
                "message": "Authorization: Bearer secret-token",
                "source": "custom-provider",
                "retryable": True,
                "statusCode": status_code,
                "details": {"headers": {"X-Custom": "secret-token"}},
            },
        },
        source="custom-provider",
    )

    assert info.code is AIErrorCode.AUTHENTICATION
    assert info.retryable is False
    assert info.message == "Provider authentication failed."
    assert info.details == {}


def test_raw_non_authentication_retry_policy_is_preserved() -> None:
    info = provider_error_info_from_raw(
        {
            "type": "response_error",
            "code": 429,
            "message": "unsafe",
            "error_info": {
                "code": "rate_limit",
                "message": "unsafe",
                "source": "custom-provider",
                "retryable": False,
                "statusCode": 429,
            },
        },
        source="custom-provider",
    )

    assert info.code is AIErrorCode.RATE_LIMIT
    assert info.retryable is False


def test_outer_http_status_is_the_authoritative_error_classification() -> None:
    info = provider_error_info_from_raw(
        {
            "type": "response_error",
            "code": 429,
            "error_info": {
                "code": "authentication",
                "message": "unsafe",
                "source": "custom-provider",
                "retryable": False,
                "statusCode": 429,
            },
        },
        source="custom-provider",
    )

    assert info.code is AIErrorCode.RATE_LIMIT
    assert info.retryable is False


def test_provider_protocol_error_only_keeps_safe_numeric_details() -> None:
    normalized = normalize_provider_error(
        AIProviderProtocolError(
            "unsafe",
            details={
                "maxParts": 2,
                "partCount": 3,
                "upstreamPayload": "secret-payload",
            },
        )
    )

    assert isinstance(normalized, AIProviderProtocolError)
    assert normalized.info.details == {"maxParts": 2, "partCount": 3}
    assert "secret-payload" not in repr(normalized.to_dict())

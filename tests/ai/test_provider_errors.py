from __future__ import annotations

import pytest

from loushang.ai import AIErrorCode
from loushang.ai.provider.errors import (
    normalize_provider_error,
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
    ("status_code", "code", "retryable"),
    [
        (401, AIErrorCode.AUTHENTICATION, False),
        (403, AIErrorCode.AUTHENTICATION, False),
        (408, AIErrorCode.TIMEOUT, True),
        (429, AIErrorCode.RATE_LIMIT, True),
        (500, AIErrorCode.SERVICE_UNAVAILABLE, True),
        (503, AIErrorCode.SERVICE_UNAVAILABLE, True),
    ],
)
def test_provider_error_part_maps_http_status_codes_to_error_info(
    status_code: int,
    code: AIErrorCode,
    retryable: bool,
) -> None:
    part = provider_error_part(
        _HttpError("provider failed", status_code), source="openai"
    )

    assert part["type"] == "response_error"
    assert part["message"] == "provider failed"
    assert part["code"] == status_code
    assert part["error_info"]["code"] == code.value
    assert part["error_info"]["source"] == "openai"
    assert part["error_info"]["retryable"] is retryable
    assert part["error_info"]["statusCode"] == status_code


def test_provider_error_part_maps_timeout_without_http_status() -> None:
    part = provider_error_part(TimeoutError("connection timed out"), source="openai")

    assert part["type"] == "response_error"
    assert part["message"] == "connection timed out"
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
    assert part["message"] == "grpc unavailable"
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


def test_normalize_provider_error_preserves_original_as_cause() -> None:
    original = _HttpError("rate limited", 429)
    normalized = normalize_provider_error(original, source="openai")

    assert normalized.info.code is AIErrorCode.RATE_LIMIT
    assert normalized.info.retryable is True
    assert normalized.__cause__ is original


def test_normalize_provider_error_preserves_request_id_from_headers() -> None:
    normalized = normalize_provider_error(
        _HttpErrorWithHeaders("rate limited", 429),
        source="openai",
    )

    assert normalized.info.request_id == "req_headers"

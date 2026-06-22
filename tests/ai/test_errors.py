from __future__ import annotations

import json

import pytest

import loushang.ai.errors as errors
from loushang.ai import AIError, AIErrorCode, AIErrorInfo
from loushang.ai.errors import (
    AIAuthenticationError,
    AIProviderProtocolError,
    AIRateLimitError,
    AITimeoutError,
    ModelNotFoundError,
    ToolValidationError,
    UnsupportedCapabilityError,
)


def test_error_info_serializes_stable_shape_and_redacts_secrets() -> None:
    error = AIAuthenticationError(
        "Missing API key.",
        provider="moonshot",
        endpoint="openai-completions",
        model="kimi-k2.5",
        request_id="req_123",
        details={
            "hint": "Set MOONSHOT_API_KEY.",
            "Authorization": "Bearer secret-token",
            "headers": {"x-request-id": "req_123", "api_key": "secret-key"},
            "oauth": [{"refresh_token": "refresh-secret"}],
        },
    )

    payload = error.to_dict()

    assert payload == {
        "code": "authentication",
        "message": "Missing API key.",
        "source": "loushang.ai",
        "retryable": False,
        "provider": "moonshot",
        "endpoint": "openai-completions",
        "model": "kimi-k2.5",
        "statusCode": None,
        "requestId": "req_123",
        "details": {
            "hint": "Set MOONSHOT_API_KEY.",
            "Authorization": "[redacted]",
            "headers": {"x-request-id": "req_123", "api_key": "[redacted]"},
            "oauth": "[redacted]",
        },
    }
    json.dumps(payload)


def test_error_info_rejects_non_json_details() -> None:
    with pytest.raises(TypeError, match="details.value"):
        AIErrorInfo(
            code=AIErrorCode.REQUEST_VALIDATION,
            message="Invalid request.",
            source="client",
            retryable=False,
            details={"value": object()},
        )


def test_error_subclasses_have_stable_codes_and_retry_defaults() -> None:
    assert ModelNotFoundError("missing").info.code is AIErrorCode.MODEL_NOT_FOUND
    assert (
        UnsupportedCapabilityError("unsupported").info.code
        is AIErrorCode.UNSUPPORTED_CAPABILITY
    )
    assert ToolValidationError("invalid").info.code is AIErrorCode.TOOL_VALIDATION
    assert AIRateLimitError("rate limited").info.retryable is True
    assert AITimeoutError("timeout").info.retryable is True
    assert AIProviderProtocolError("bad event").info.retryable is False


def test_root_error_exports_are_stable_base_entries() -> None:
    assert AIError is errors.AIError
    error = AIError(
        AIErrorInfo(
            code="provider",
            message="Provider failed.",
            source="provider",
            retryable=True,
            status_code=503,
        )
    )

    assert str(error) == "Provider failed."
    assert error.to_dict()["statusCode"] == 503

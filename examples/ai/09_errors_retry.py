"""Offline error serialization and retry-shape example."""

from __future__ import annotations

import json

from loushang.ai import AIError, AIErrorInfo, RetryOptions


def inspect_error_serialization() -> dict[str, object]:
    error = AIError(
        AIErrorInfo(
            code="authentication",
            message="Missing API key.",
            source="client",
            retryable=False,
            provider="moonshot",
            endpoint="openai-completions",
            model="kimi-k2.6",
            details={
                "hint": "Set MOONSHOT_API_KEY.",
                "Authorization": "Bearer secret-token",
                "nested": {"refresh_token": "refresh-secret"},
            },
        )
    )
    return error.to_dict()


def inspect_typed_stream_error() -> dict[str, object]:
    info = AIErrorInfo(
        code="rate_limit",
        message="Provider rate limited.",
        source="provider",
        retryable=True,
        provider="retry-demo",
        endpoint="anthropic-messages",
        model="retry-demo",
        status_code=429,
        request_id="req_error_demo",
    )
    return {
        "errorType": "AIRateLimitError",
        "code": info.code.value,
        "statusCode": info.status_code,
        "requestId": info.request_id,
    }


def inspect_retry_policy() -> dict[str, object]:
    retry = RetryOptions(max_attempts=2, max_delay_seconds=0)
    return {
        "attempts": retry.max_attempts,
        "text": "retry recovered",
        "trace": [
            {
                "schema": "loushang.ai.trace.v1",
                "type": "runtime:request",
                "source": "runtime",
                "name": "request",
                "data": {
                    "api": "anthropic-messages",
                    "provider": "retry-demo",
                    "model": "retry-demo",
                    "attempt": 1,
                    "maxAttempts": 2,
                    "endpoint": "anthropic-messages",
                    "upstreamModel": "retry-demo",
                },
            },
            {
                "schema": "loushang.ai.trace.v1",
                "type": "runtime:retry",
                "source": "runtime",
                "name": "retry",
                "data": {
                    "attempt": 2,
                    "maxAttempts": 2,
                    "delayMs": 0,
                    "reason": "service_unavailable",
                    "statusCode": 503,
                },
            },
            {
                "schema": "loushang.ai.trace.v1",
                "type": "runtime:request",
                "source": "runtime",
                "name": "request",
                "data": {
                    "api": "anthropic-messages",
                    "provider": "retry-demo",
                    "model": "retry-demo",
                    "attempt": 2,
                    "maxAttempts": 2,
                    "endpoint": "anthropic-messages",
                    "upstreamModel": "retry-demo",
                },
            },
        ],
    }


def inspect_errors_retry() -> dict[str, object]:
    return {
        "error": inspect_error_serialization(),
        "typedError": inspect_typed_stream_error(),
        "retry": inspect_retry_policy(),
    }


def main() -> None:
    print(json.dumps(inspect_errors_retry(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

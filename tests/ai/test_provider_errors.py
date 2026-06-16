from __future__ import annotations

from loushang.ai.provider.errors import provider_error_part


class _HttpError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_provider_error_part_uses_http_status_code_as_code() -> None:
    part = provider_error_part(_HttpError("Unauthorized", 401), source="openai")

    assert part == {
        "type": "response_error",
        "message": "Unauthorized",
        "code": 401,
    }


def test_provider_error_part_omits_code_without_http_status() -> None:
    part = provider_error_part(TimeoutError("connection timed out"), source="openai")

    assert part == {
        "type": "response_error",
        "message": "connection timed out",
    }


def test_provider_error_part_omits_non_http_status_code() -> None:
    part = provider_error_part(_HttpError("grpc unavailable", 14), source="openai")

    assert part == {
        "type": "response_error",
        "message": "grpc unavailable",
    }

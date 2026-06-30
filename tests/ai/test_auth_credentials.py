from __future__ import annotations

from loushang.ai.auth import (
    ApiKeyAuth,
    HeadersAuth,
    NoAuth,
    OAuthBearerAuth,
)
from loushang.ai.auth.credentials import AuthCredential
from loushang.ai.errors import AIAuthenticationError


def test_request_auth_credentials_are_importable_from_auth_package() -> None:
    credentials: list[AuthCredential] = [
        ApiKeyAuth("api-secret", header="x-api-key", prefix=""),
        OAuthBearerAuth("oauth-secret"),
        NoAuth(),
        HeadersAuth({"Authorization": "Bearer header-secret"}),
    ]

    assert credentials[0].header == "x-api-key"
    assert credentials[1].prefix is None
    assert isinstance(credentials[2], NoAuth)
    assert credentials[3].headers["Authorization"] == "Bearer header-secret"


def test_request_auth_credential_repr_does_not_expose_secrets() -> None:
    values = [
        repr(ApiKeyAuth("api-secret")),
        repr(OAuthBearerAuth("oauth-secret")),
        repr(HeadersAuth({"Authorization": "Bearer header-secret"})),
        repr(NoAuth()),
    ]

    rendered = "\n".join(values)

    assert "api-secret" not in rendered
    assert "oauth-secret" not in rendered
    assert "header-secret" not in rendered


def test_headers_auth_values_are_redacted_by_error_details() -> None:
    error = AIAuthenticationError(
        "Missing auth.",
        details={
            "headers": {
                "Authorization": "Bearer header-secret",
                "X-Provider-Token": "provider-secret",
                "x-request-id": "req_123",
            }
        },
    )

    assert error.to_dict()["details"] == {
        "headers": {
            "Authorization": "[redacted]",
            "X-Provider-Token": "[redacted]",
            "x-request-id": "req_123",
        }
    }

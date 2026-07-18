from __future__ import annotations

from types import MappingProxyType

import pytest

from loushang.ai.auth.credentials import ApiKeyAuth, OAuthBearerAuth


def test_auth_credentials_are_minimal_and_redacted() -> None:
    api_key = ApiKeyAuth("api-secret")
    oauth = OAuthBearerAuth(
        "oauth-secret",
        extra_headers={"chatgpt-account-id": "account"},
    )

    assert set(ApiKeyAuth.__dataclass_fields__) == {"value"}
    assert set(OAuthBearerAuth.__dataclass_fields__) == {
        "access_token",
        "extra_headers",
    }
    assert isinstance(oauth.extra_headers, MappingProxyType)
    assert "api-secret" not in repr(api_key)
    assert "oauth-secret" not in repr(oauth)


def test_oauth_extra_headers_are_defensively_copied() -> None:
    source = {"x-account": "one"}
    auth = OAuthBearerAuth("token", extra_headers=source)

    source["x-account"] = "two"

    assert auth.extra_headers == {"x-account": "one"}
    with pytest.raises(TypeError):
        auth.extra_headers["x-new"] = "value"  # type: ignore[index]

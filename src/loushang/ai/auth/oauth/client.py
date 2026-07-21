from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loushang.ai.auth.credentials import OAuthCredential
from loushang.ai.auth.errors import (
    AuthError,
    InvalidCredentialError,
    OAuthProviderNotConfiguredError,
    RefreshFailedError,
)
from loushang.ai.auth.oauth.base import AuthorizationCallback


@dataclass(frozen=True, slots=True)
class OAuthClientConfig:
    client_id: str | None
    authorization_endpoint: str | None
    token_endpoint: str | None
    redirect_uri: str | None
    client_secret: str | None = None
    scopes: Sequence[str] = ()
    revocation_endpoint: str | None = None
    token_endpoint_auth_method: str | None = None


class AuthlibOAuthProvider:
    """OAuth authorization-code provider implemented by Authlib."""

    id: str

    def __init__(self, provider_id: str, config: OAuthClientConfig) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be a non-empty string")
        self.id = provider_id.strip()
        self.config = config

    async def login(
        self,
        *,
        authorize: AuthorizationCallback | None = None,
    ) -> OAuthCredential:
        self._require_login_config()
        if authorize is None:
            raise OAuthProviderNotConfiguredError(
                "OAuth login requires an authorization callback that returns the final redirect URL.",
                provider=self.id,
                details={"recovery": "provide_login_interaction"},
            )
        from authlib.common.security import (  # type: ignore[import-untyped]
            generate_token,
        )

        client = self._new_client()
        code_verifier = generate_token(48)
        try:
            try:
                authorization_url, _state = client.create_authorization_url(
                    self.config.authorization_endpoint,
                    code_verifier=code_verifier,
                )
                authorization_response = await authorize(authorization_url)
                if (
                    not isinstance(authorization_response, str)
                    or not authorization_response.strip()
                ):
                    raise InvalidCredentialError(
                        "OAuth authorization callback returned no redirect URL.",
                        provider=self.id,
                        details={"recovery": "login"},
                    )
                token = await client.fetch_token(
                    self.config.token_endpoint,
                    authorization_response=authorization_response,
                    code_verifier=code_verifier,
                )
            except AuthError:
                raise
            except Exception as error:
                raise AuthError(
                    "OAuth login failed.",
                    provider=self.id,
                    details={
                        "cause": type(error).__name__,
                        "recovery": "login",
                    },
                ) from error
        finally:
            await client.aclose()
        return self.credential_from_token(token)

    async def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        self._require_refresh_config()
        if credential.provider != self.id:
            raise InvalidCredentialError(
                "OAuth credential provider does not match the refresh adapter.",
                provider=self.id,
                details={
                    "credential_provider": credential.provider,
                    "recovery": "reconfigure",
                },
            )
        if credential.refresh_token is None:
            raise InvalidCredentialError(
                "OAuth credential has no refresh token.",
                provider=self.id,
                details={"recovery": "login"},
            )
        client = self._new_client(token=_oauth_token(credential))
        try:
            try:
                token = await client.refresh_token(
                    self.config.token_endpoint,
                    refresh_token=credential.refresh_token,
                )
            except AuthError:
                raise
            except Exception as error:
                raise RefreshFailedError(
                    "OAuth credential refresh failed.",
                    provider=self.id,
                    details={
                        "cause": type(error).__name__,
                        "recovery": "login",
                    },
                ) from error
        finally:
            await client.aclose()
        return self.credential_from_token(token, previous=credential)

    async def revoke(self, credential: OAuthCredential) -> None:
        if not self.config.revocation_endpoint:
            return
        self._require_client_id()
        client = self._new_client(token=_oauth_token(credential))
        try:
            await client.revoke_token(
                self.config.revocation_endpoint,
                token=credential.refresh_token or credential.access_token,
                token_type_hint=(
                    "refresh_token" if credential.refresh_token else "access_token"
                ),
            )
        finally:
            await client.aclose()

    def credential_from_token(
        self,
        token: Mapping[str, Any],
        *,
        previous: OAuthCredential | None = None,
    ) -> OAuthCredential:
        if not isinstance(token, Mapping):
            raise InvalidCredentialError(
                "OAuth token response must be a mapping.",
                provider=self.id,
                details={"recovery": "login"},
            )
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise InvalidCredentialError(
                "OAuth token response is missing access_token.",
                provider=self.id,
                details={"recovery": "login"},
            )
        refresh_token = token.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            refresh_token = previous.refresh_token if previous is not None else None
        token_type = token.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type.strip():
            token_type = "Bearer"
        expires_at = _expires_at_from_token(token)
        if expires_at is None and previous is not None:
            expires_at = previous.expires_at
        extra_headers = self.extra_headers_from_token(token, previous=previous) or (
            previous.extra_headers if previous is not None else {}
        )
        return OAuthCredential(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            provider=self.id,
            extra_headers=extra_headers,
        )

    def extra_headers_from_token(
        self,
        token: Mapping[str, Any],
        *,
        previous: OAuthCredential | None,
    ) -> Mapping[str, str]:
        del token, previous
        return {}

    def _new_client(self, *, token: Mapping[str, object] | None = None):
        from authlib.integrations.httpx_client import (  # type: ignore[import-untyped]
            AsyncOAuth2Client,
        )

        return AsyncOAuth2Client(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            redirect_uri=self.config.redirect_uri,
            scope=" ".join(self.config.scopes) or None,
            token=token,
            token_endpoint_auth_method=self.config.token_endpoint_auth_method,
            code_challenge_method="S256",
        )

    def _require_client_id(self) -> None:
        if not self.config.client_id:
            raise OAuthProviderNotConfiguredError(
                "OAuth provider has no authorized client_id.",
                provider=self.id,
                details={"recovery": "configure_client"},
            )

    def _require_login_config(self) -> None:
        self._require_client_id()
        missing = [
            name
            for name in (
                "authorization_endpoint",
                "token_endpoint",
                "redirect_uri",
            )
            if not getattr(self.config, name)
        ]
        if missing:
            raise OAuthProviderNotConfiguredError(
                "OAuth provider login configuration is incomplete.",
                provider=self.id,
                details={
                    "missing": list(missing),
                    "recovery": "configure_client",
                },
            )

    def _require_refresh_config(self) -> None:
        self._require_client_id()
        if not self.config.token_endpoint:
            raise OAuthProviderNotConfiguredError(
                "OAuth provider has no token endpoint for refresh.",
                provider=self.id,
                details={"recovery": "configure_client"},
            )


def _expires_at_from_token(token: Mapping[str, Any]) -> float | int | None:
    expires_at = token.get("expires_at")
    if (
        not isinstance(expires_at, bool)
        and isinstance(expires_at, int | float)
        and expires_at > 0
    ):
        return expires_at
    expires_in = token.get("expires_in")
    if (
        not isinstance(expires_in, bool)
        and isinstance(expires_in, int | float)
        and expires_in > 0
    ):
        return time.time() + expires_in
    return None


def _oauth_token(credential: OAuthCredential) -> dict[str, object]:
    token: dict[str, object] = {
        "access_token": credential.access_token,
        "token_type": credential.token_type,
    }
    if credential.refresh_token is not None:
        token["refresh_token"] = credential.refresh_token
    if credential.expires_at is not None:
        token["expires_at"] = credential.expires_at
    return token


__all__ = ["AuthlibOAuthProvider", "OAuthClientConfig"]

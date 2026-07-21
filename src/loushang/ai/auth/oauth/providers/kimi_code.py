from __future__ import annotations

from collections.abc import Sequence

from loushang.ai.auth.oauth.client import AuthlibOAuthProvider, OAuthClientConfig


class KimiCodeOAuthProvider(AuthlibOAuthProvider):
    """Reserved Kimi Code OAuth adapter; no client identity is fabricated."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        redirect_uri: str | None = None,
        client_secret: str | None = None,
        scopes: Sequence[str] = (),
        revocation_endpoint: str | None = None,
    ) -> None:
        super().__init__(
            "kimi-code",
            OAuthClientConfig(
                client_id=client_id,
                client_secret=client_secret,
                authorization_endpoint=authorization_endpoint,
                token_endpoint=token_endpoint,
                redirect_uri=redirect_uri,
                scopes=scopes,
                revocation_endpoint=revocation_endpoint,
            ),
        )


__all__ = ["KimiCodeOAuthProvider"]

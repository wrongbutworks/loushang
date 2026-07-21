from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from loushang.ai.auth.oauth.client import AuthlibOAuthProvider, OAuthClientConfig


@dataclass(frozen=True, slots=True)
class KimiOAuthConfig:
    """Authorized Kimi OAuth client configuration supplied by the application."""

    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    redirect_uri: str
    client_secret: str | None = None
    scopes: Sequence[str] = ()
    revocation_endpoint: str | None = None
    token_endpoint_auth_method: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "client_id",
            "authorization_endpoint",
            "token_endpoint",
            "redirect_uri",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Kimi OAuth {name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        if self.client_secret is not None and (
            not isinstance(self.client_secret, str) or not self.client_secret.strip()
        ):
            raise ValueError("Kimi OAuth client_secret must be non-empty or None")
        for name in ("revocation_endpoint", "token_endpoint_auth_method"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Kimi OAuth {name} must be non-empty or None")
            object.__setattr__(self, name, value.strip())
        if isinstance(self.scopes, str) or not isinstance(self.scopes, Sequence):
            raise ValueError("Kimi OAuth scopes must be a sequence of strings")
        scopes = tuple(self.scopes)
        if any(not isinstance(scope, str) or not scope.strip() for scope in scopes):
            raise ValueError("Kimi OAuth scopes must contain non-empty strings")
        object.__setattr__(self, "scopes", tuple(scope.strip() for scope in scopes))


class KimiCodeOAuthProvider(AuthlibOAuthProvider):
    """Kimi Code OAuth adapter backed by an explicitly authorized client."""

    def __init__(self, config: KimiOAuthConfig) -> None:
        if not isinstance(config, KimiOAuthConfig):
            raise TypeError("config must be KimiOAuthConfig")
        super().__init__(
            "kimi-code",
            OAuthClientConfig(
                client_id=config.client_id,
                client_secret=config.client_secret,
                authorization_endpoint=config.authorization_endpoint,
                token_endpoint=config.token_endpoint,
                redirect_uri=config.redirect_uri,
                scopes=config.scopes,
                revocation_endpoint=config.revocation_endpoint,
                token_endpoint_auth_method=config.token_endpoint_auth_method,
            ),
        )


__all__ = ["KimiCodeOAuthProvider", "KimiOAuthConfig"]

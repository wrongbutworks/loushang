from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path

from loushang.ai.auth.credentials import OAuthCredential
from loushang.ai.auth.errors import (
    InvalidCredentialError,
    OAuthProviderNotConfiguredError,
    RefreshFailedError,
)
from loushang.ai.auth.oauth.base import AuthorizationCallback


class OpenAICodexOAuthProvider:
    """Experimental read-only adapter for an existing Codex CLI file login."""

    id = "openai-codex"
    experimental = True

    def __init__(self, auth_path: str | Path | None = None) -> None:
        self.auth_path = (
            Path(auth_path).expanduser()
            if auth_path is not None
            else Path.home() / ".codex" / "auth.json"
        )

    def load_external_credential(self) -> OAuthCredential | None:
        if not self.auth_path.exists():
            return None
        return load_codex_credential(self.auth_path)

    def load_credential_file(self, path: str | Path) -> OAuthCredential:
        return load_codex_credential(path)

    async def login(
        self,
        *,
        authorize: AuthorizationCallback | None = None,
    ) -> OAuthCredential:
        del authorize
        raise OAuthProviderNotConfiguredError(
            "Loushang does not own an OpenAI OAuth client; use `codex login` and reuse its existing file credential experimentally.",
            provider=self.id,
            details={"experimental": True, "recovery": "codex_login"},
        )

    async def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        del credential
        raise RefreshFailedError(
            "Loushang cannot refresh the experimental Codex credential; run `codex login` again.",
            provider=self.id,
            details={"experimental": True, "recovery": "codex_login"},
        )

    async def revoke(self, credential: OAuthCredential) -> None:
        del credential


def load_codex_credential(path: str | Path) -> OAuthCredential:
    resolved = Path(path).expanduser()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidCredentialError(
            "Codex auth file could not be read.",
            provider="openai-codex",
            details={
                "path": str(resolved),
                "cause": type(error).__name__,
                "experimental": True,
                "recovery": "codex_login",
            },
        ) from error
    if not isinstance(raw, Mapping) or raw.get("auth_mode") != "chatgpt":
        raise InvalidCredentialError(
            "Codex auth file does not contain a ChatGPT login.",
            provider="openai-codex",
            details={"experimental": True, "recovery": "codex_login"},
        )
    tokens = raw.get("tokens")
    if not isinstance(tokens, Mapping):
        raise InvalidCredentialError(
            "Codex auth file is missing its token object.",
            provider="openai-codex",
            details={"experimental": True, "recovery": "codex_login"},
        )
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    account_id = tokens.get("account_id")
    if not isinstance(access_token, str) or not access_token.strip():
        raise InvalidCredentialError(
            "Codex auth file is missing access_token.",
            provider="openai-codex",
            details={"experimental": True, "recovery": "codex_login"},
        )
    extra_headers = (
        {"ChatGPT-Account-ID": account_id}
        if isinstance(account_id, str) and account_id.strip()
        else {}
    )
    expires_at = tokens.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, int | float):
        expires_at = _jwt_exp(access_token)
    return OAuthCredential(
        provider="openai-codex",
        access_token=access_token,
        refresh_token=(
            refresh_token
            if isinstance(refresh_token, str) and refresh_token.strip()
            else None
        ),
        expires_at=expires_at,
        token_type="Bearer",
        extra_headers=extra_headers,
    )


def _jwt_exp(token: str) -> int | float | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        padding = "=" * (-len(parts[1]) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
        )
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    expires_at = payload.get("exp")
    if isinstance(expires_at, bool) or not isinstance(expires_at, int | float):
        return None
    return expires_at if expires_at > 0 else None


__all__ = ["OpenAICodexOAuthProvider", "load_codex_credential"]

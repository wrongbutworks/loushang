from __future__ import annotations

import json
import os

from loushang.ai.auth.types import OAuthCredentials


def _auth_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".codex", "auth.json")


def load_codex_cli_auth() -> dict[str, object] | None:
    path = _auth_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def get_codex_cli_oauth_credentials() -> OAuthCredentials | None:
    payload = load_codex_cli_auth()
    if not payload:
        return None

    auth_mode = payload.get("auth_mode")
    if auth_mode != "chatgpt":
        return None

    tokens = payload.get("tokens")
    token_map = tokens if isinstance(tokens, dict) else {}
    access_token = token_map.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        return None
    account_id = token_map.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        return None

    extra: dict[str, object] = {
        "source": "codex-cli",
        "auth_mode": "chatgpt",
        "account_id": account_id.strip(),
    }
    last_refresh = payload.get("last_refresh")
    expires_at = None
    if isinstance(last_refresh, (int, float)):
        expires_at = float(last_refresh)

    refresh_token = token_map.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        refresh_token = None

    return OAuthCredentials(
        provider="openai-codex",
        access_token=access_token.strip(),
        refresh_token=refresh_token,
        expires_at=expires_at,
        extra=extra,
    )

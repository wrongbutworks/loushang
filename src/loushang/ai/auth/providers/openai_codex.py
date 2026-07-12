from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from loushang.ai.auth.browser import CallbackWaiter, open_browser, wait_for_callback_url
from loushang.ai.auth.registry import OAuthProviderRegistry, get_default_oauth_registry
from loushang.ai.auth.types import (
    OAuthCredentials,
    OAuthLoginCallbacks,
    OAuthProviderInterface,
)

AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPES = "openid profile email offline_access"
JWT_CLAIM_PATH = "https://api.openai.com/auth"
LOGIN_URL = AUTHORIZE_URL


def _codex_cli_auth_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".codex", "auth.json")


def load_codex_cli_auth(
    path: str | os.PathLike[str] | None = None,
) -> dict[str, object] | None:
    resolved_path = os.fspath(path) if path is not None else _codex_cli_auth_path()
    if not os.path.exists(resolved_path):
        return None
    try:
        with open(resolved_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        if path is None:
            return None
        raise
    return payload if isinstance(payload, dict) else None


def get_codex_cli_oauth_credentials(
    path: str | os.PathLike[str] | None = None,
) -> OAuthCredentials | None:
    payload = load_codex_cli_auth() if path is None else load_codex_cli_auth(path)
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
    access_token = access_token.strip()
    account_id = token_map.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        return None

    account_id = account_id.strip()
    extra: dict[str, object] = {
        "source": "codex-cli",
        "auth_mode": "chatgpt",
        "account_id": account_id,
    }
    refresh_token = token_map.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        refresh_token = None
    else:
        refresh_token = refresh_token.strip()

    expires_at = _extract_token_expiry(access_token)
    return OAuthCredentials(
        provider="openai-codex",
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        extra=extra,
    )


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    verifier = _base64url_encode(secrets.token_bytes(32))
    challenge = _base64url_encode(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def create_state() -> str:
    return secrets.token_hex(16)


def _parse_authorization_input(input_text: str) -> tuple[str | None, str | None]:
    value = input_text.strip()
    if not value:
        return None, None

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        params = parse_qs(parsed.query)
        return params.get("code", [None])[0], params.get("state", [None])[0]

    if "#" in value:
        code, state = value.split("#", 1)
        return code or None, state or None

    if "code=" in value:
        params = parse_qs(value)
        return params.get("code", [None])[0], params.get("state", [None])[0]

    return value, None


def _decode_jwt_payload(access_token: str) -> dict[str, Any]:
    parts = access_token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid token")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
    data = json.loads(decoded)
    if not isinstance(data, dict):
        raise ValueError("invalid token payload")
    return data


def _extract_token_expiry(access_token: str) -> float | None:
    try:
        expires_at = _decode_jwt_payload(access_token).get("exp")
    except Exception:
        return None
    if (
        isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or not math.isfinite(expires_at)
    ):
        return None
    return float(expires_at) - 300.0


def _extract_account_id(access_token: str) -> str:
    try:
        data = _decode_jwt_payload(access_token)
        account_id = data.get(JWT_CLAIM_PATH, {}).get("chatgpt_account_id")
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("missing account id")
        return account_id
    except Exception as exc:
        raise ValueError("Failed to extract accountId from token") from exc


async def _post_form(url: str, body: dict[str, str]) -> dict[str, Any]:
    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "httpx is required for OpenAI Codex OAuth. Install via `pip install httpx`"
        ) from exc

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data=body,
        )
        response.raise_for_status()
        return response.json()


class OpenAICodexOAuthProvider(OAuthProviderInterface):
    def __init__(
        self,
        *,
        http_post_form: Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]
        | None = None,
        pkce_generator: Callable[[], tuple[str, str]] | None = None,
        state_generator: Callable[[], str] | None = None,
        browser_opener: Callable[[str], bool] | None = None,
        callback_waiter: CallbackWaiter | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._http_post_form = http_post_form or _post_form
        self._pkce_generator = pkce_generator or generate_pkce_pair
        self._state_generator = state_generator or create_state
        self._browser_opener = browser_opener or open_browser
        self._callback_waiter = callback_waiter or wait_for_callback_url
        self._time_fn = time_fn or time.time

    @property
    def id(self) -> str:
        return "openai-codex"

    @property
    def name(self) -> str:
        return "OpenAI Codex"

    def uses_callback_server(self) -> bool:
        return True

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        return models

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    def get_auth_headers(self, credentials: OAuthCredentials) -> dict[str, str]:
        account_id = _account_id_from_extra(credentials.extra)
        if account_id is None:
            return {}
        return {"chatgpt-account-id": account_id}

    async def login(self, callbacks: OAuthLoginCallbacks) -> OAuthCredentials:
        verifier, challenge = self._pkce_generator()
        expected_state = self._state_generator()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": expected_state,
                "id_token_add_organizations": "true",
                "codex_cli_simplified_flow": "true",
                "originator": "loushang",
            }
        )
        auth_url = f"{AUTHORIZE_URL}?{query}"

        with suppress(Exception):
            callbacks.on_auth(
                {
                    "url": auth_url,
                    "instructions": (
                        "Complete login in your browser. If the automatic localhost callback "
                        "does not arrive, paste the final redirect URL or the authorization code here."
                    ),
                }
            )

        with suppress(Exception):
            opened = self._browser_opener(auth_url)
            if opened:
                callbacks.on_progress("Opened browser for OpenAI Codex login")
            callbacks.on_progress("Waiting for OpenAI Codex authorization callback")

        try:
            raw_input = (
                await self._callback_waiter(
                    REDIRECT_URI,
                    timeout=300.0,
                    signal=getattr(callbacks, "signal", None),
                )
                or ""
            )
        except Exception:
            raw_input = ""

        if not raw_input.strip():
            with suppress(Exception):
                callbacks.on_progress(
                    "Callback not received; waiting for manual code input"
                )

        try:
            if not raw_input.strip():
                raw_input = await callbacks.on_manual_code_input()
        except Exception:
            if not raw_input.strip():
                raw_input = ""

        if not raw_input.strip():
            raw_input = await callbacks.on_prompt(
                {
                    "message": "Paste the authorization code or full redirect URL",
                    "placeholder": REDIRECT_URI,
                    "allow_empty": False,
                }
            )

        code, returned_state = _parse_authorization_input(raw_input)
        if not code:
            raise ValueError(
                "OpenAI Codex OAuth login did not receive an authorization code"
            )
        if returned_state and returned_state != expected_state:
            raise ValueError("OpenAI Codex OAuth state mismatch")

        payload = await self._http_post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
            },
        )
        return self._credentials_from_token_payload(payload)

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        if not credentials.refresh_token:
            raise ValueError("OpenAI Codex OAuth credentials missing refresh_token")

        payload = await self._http_post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": credentials.refresh_token,
                "client_id": CLIENT_ID,
            },
        )
        return self._credentials_from_token_payload(payload, previous=credentials)

    def _credentials_from_token_payload(
        self,
        payload: dict[str, Any],
        *,
        previous: OAuthCredentials | None = None,
    ) -> OAuthCredentials:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("OpenAI Codex OAuth token response missing access_token")

        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            refresh_token = previous.refresh_token if previous is not None else None

        expires_in = payload.get("expires_in")
        expires_at: float | None = None
        if (
            not isinstance(expires_in, bool)
            and isinstance(expires_in, (int, float))
            and math.isfinite(expires_in)
            and expires_in > 0
        ):
            expires_at = self._time_fn() + float(expires_in) - 300.0
        else:
            expires_at = _extract_token_expiry(access_token)

        extra: dict[str, Any] = {
            "account_id": _extract_account_id(access_token),
        }
        token_type = payload.get("token_type")
        scope = payload.get("scope")
        if isinstance(token_type, str):
            extra["token_type"] = token_type
        if isinstance(scope, str):
            extra["scope"] = scope

        return OAuthCredentials(
            provider=self.id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            extra=extra,
        )


def register_openai_codex_oauth_provider(
    *,
    source_id: str | None = None,
    registry: OAuthProviderRegistry | None = None,
) -> None:
    resolved_registry = registry or get_default_oauth_registry()
    resolved_registry.register(OpenAICodexOAuthProvider(), source_id=source_id)


def _account_id_from_extra(extra: object) -> str | None:
    if not isinstance(extra, dict):
        return None
    headers = extra.get("headers")
    if isinstance(headers, dict):
        header_value = headers.get("chatgpt-account-id")
        if isinstance(header_value, str) and header_value.strip():
            return header_value.strip()
    account_id = extra.get("account_id")
    if isinstance(account_id, str) and account_id.strip():
        return account_id.strip()
    return None

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from loushang.ai.auth.browser import CallbackWaiter, open_browser, wait_for_callback_url
from loushang.ai.auth.registry import get_default_oauth_registry
from loushang.ai.auth.types import (
    OAuthCredentials,
    OAuthLoginCallbacks,
    OAuthProviderInterface,
)

AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
REDIRECT_URI = "http://localhost:53692/callback"
SCOPES = (
    "org:create_api_key user:profile user:inference user:sessions:claude_code "
    "user:mcp_servers user:file_upload"
)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    verifier = _base64url_encode(secrets.token_bytes(32))
    challenge = _base64url_encode(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def _parse_authorization_input(input_text: str) -> tuple[str | None, str | None]:
    value = input_text.strip()
    if not value:
        return None, None

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        return code, state

    if "#" in value:
        code, state = value.split("#", 1)
        return code or None, state or None

    if "code=" in value:
        params = parse_qs(value)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        return code, state

    return value, None


async def _post_json(url: str, body: dict[str, str]) -> dict[str, Any]:
    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "httpx is required for Anthropic OAuth. Install via `pip install httpx`"
        ) from exc

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            content=json.dumps(body),
        )
        response.raise_for_status()
        return response.json()


class AnthropicOAuthProvider(OAuthProviderInterface):
    def __init__(
        self,
        *,
        http_post_json: Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]
        | None = None,
        pkce_generator: Callable[[], tuple[str, str]] | None = None,
        browser_opener: Callable[[str], bool] | None = None,
        callback_waiter: CallbackWaiter | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._http_post_json = http_post_json or _post_json
        self._pkce_generator = pkce_generator or generate_pkce_pair
        self._browser_opener = browser_opener or open_browser
        self._callback_waiter = callback_waiter or wait_for_callback_url
        self._time_fn = time_fn or time.time

    @property
    def id(self) -> str:
        return "anthropic"

    @property
    def name(self) -> str:
        return "Anthropic (Claude)"

    def uses_callback_server(self) -> bool:
        return True

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        return models

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    async def login(self, callbacks: OAuthLoginCallbacks) -> OAuthCredentials:
        verifier, challenge = self._pkce_generator()
        query = urlencode(
            {
                "code": "true",
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": verifier,
            }
        )
        auth_url = f"{AUTHORIZE_URL}?{query}"

        with suppress(Exception):
            callbacks.on_auth(
                {
                    "url": auth_url,
                    "instructions": (
                        "Complete login in your browser. If the automatic localhost callback "
                        "does not arrive, paste the final redirect URL or the authorization "
                        "code here."
                    ),
                }
            )

        with suppress(Exception):
            opened = self._browser_opener(auth_url)
            if opened:
                callbacks.on_progress("Opened browser for Anthropic login")
            callbacks.on_progress("Waiting for Anthropic authorization callback")

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

        code, state = _parse_authorization_input(raw_input)
        if not code:
            raise ValueError(
                "Anthropic OAuth login did not receive an authorization code"
            )
        if state and state != verifier:
            raise ValueError("Anthropic OAuth state mismatch")

        payload = await self._http_post_json(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "state": state or verifier,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
        return self._credentials_from_token_payload(payload)

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        if not credentials.refresh_token:
            return replace(credentials, expires_at=self._time_fn() + 3600)

        payload = await self._http_post_json(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": credentials.refresh_token,
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
            raise ValueError("Anthropic OAuth token response missing access_token")

        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            refresh_token = previous.refresh_token if previous is not None else None

        expires_in = payload.get("expires_in")
        expires_at: float | None = None
        if isinstance(expires_in, int | float):
            expires_at = self._time_fn() + float(expires_in) - 300.0
        elif previous is not None:
            expires_at = previous.expires_at

        extra: dict[str, Any] | None = None
        token_type = payload.get("token_type")
        scope = payload.get("scope")
        if isinstance(token_type, str) or isinstance(scope, str):
            extra = {}
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


def register_anthropic_oauth_provider(*, source_id: str | None = None) -> None:
    get_default_oauth_registry().register(AnthropicOAuthProvider(), source_id=source_id)

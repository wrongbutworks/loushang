from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from loushang.ai.auth import OAuthError, OAuthReauthenticationRequiredError
from loushang.ai.auth.providers.anthropic import (
    AUTHORIZE_URL,
    CLIENT_ID,
    REDIRECT_URI,
    TOKEN_URL,
    AnthropicOAuthProvider,
    generate_pkce_pair,
)
from loushang.ai.auth.types import OAuthCredentials

_VERIFIER = "test-verifier"
_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(_VERIFIER.encode()).digest())
    .decode("ascii")
    .rstrip("=")
)
_STATE = "test-state"


def test_generate_pkce_pair_returns_s256_challenge() -> None:
    verifier, challenge = generate_pkce_pair()

    assert verifier
    assert "=" not in verifier
    assert "=" not in challenge
    assert challenge == (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode("ascii")
        .rstrip("=")
    )


def test_anthropic_oauth_provider_source_stays_python_311_compatible() -> None:
    source = Path("src/loushang/ai/auth/providers/anthropic.py").read_text()

    assert "?{\n" not in source


def test_login_exchanges_authorization_code_and_returns_credentials() -> None:
    calls: list[tuple[str, dict[str, str]]] = []
    opened_urls: list[str] = []
    callbacks = _Callbacks()

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {
            "access_token": "access-123",
            "refresh_token": "refresh-123",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "user:inference",
        }

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda url: opened_urls.append(url) is None,
        callback_waiter=_return_callback_url,
        time_fn=lambda: 1_000.0,
    )

    creds = _run(provider.login(callbacks))

    assert callbacks.auth_info is not None
    auth_url = callbacks.auth_info["url"]
    params = parse_qs(urlparse(auth_url).query)
    assert auth_url.startswith(AUTHORIZE_URL)
    assert params["client_id"] == [CLIENT_ID]
    assert params["state"] == [_STATE]
    assert params["state"] != [_VERIFIER]
    assert params["code_challenge"] == [_CHALLENGE]
    assert params["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in params
    assert _VERIFIER not in auth_url
    assert _VERIFIER not in repr(callbacks.auth_info)
    assert _VERIFIER not in repr(callbacks.progress_messages)
    assert opened_urls == [auth_url]
    assert callbacks.progress_messages == [
        "Opened browser for Anthropic login",
        "Waiting for Anthropic authorization callback",
    ]
    assert calls == [
        (
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": "auth_code",
                "state": _STATE,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": _VERIFIER,
            },
        )
    ]
    assert asdict(creds) == asdict(
        OAuthCredentials(
            provider="anthropic",
            access_token="access-123",
            refresh_token="refresh-123",
            expires_at=4_300.0,
            extra={"token_type": "Bearer", "scope": "user:inference"},
        )
    )


def test_login_rejects_state_mismatch() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {}

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda _url: False,
        callback_waiter=_return_wrong_state_url,
    )
    callbacks = _Callbacks()

    with pytest.raises(OAuthError, match="state mismatch") as captured:
        _run(provider.login(callbacks))

    assert calls == []
    assert _VERIFIER not in str(captured.value)


@pytest.mark.parametrize(
    "callback_url",
    [
        f"{REDIRECT_URI}?code=auth_code",
        f"{REDIRECT_URI}?code=auth_code&state=",
        f"{REDIRECT_URI}?code=auth_code&state=%C3%A9",
        f"{REDIRECT_URI}?code=auth_code&state={_STATE}&state=wrong",
    ],
)
def test_login_rejects_redirect_without_matching_state(callback_url: str) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {}

    async def callback_waiter(*_args, **_kwargs) -> str:
        return callback_url

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda _url: False,
        callback_waiter=callback_waiter,
    )

    with pytest.raises(OAuthError, match="state mismatch"):
        _run(provider.login(_Callbacks()))

    assert calls == []


def test_login_rejects_plain_code_from_callback() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {}

    async def callback_waiter(*_args, **_kwargs) -> str:
        return "auth_code"

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda _url: False,
        callback_waiter=callback_waiter,
    )

    with pytest.raises(OAuthError, match="state-bound redirect"):
        _run(provider.login(_Callbacks()))

    assert calls == []


def test_login_falls_back_to_manual_input_when_callback_waiter_fails() -> None:
    calls: list[tuple[str, dict[str, str]]] = []
    callbacks = _Callbacks(manual_code_input="auth_code")

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {
            "access_token": "access-123",
            "refresh_token": "refresh-123",
            "expires_in": 3600,
        }

    async def broken_callback_waiter(*_args, **_kwargs) -> str | None:
        raise OSError("bind failed")

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda _url: False,
        callback_waiter=broken_callback_waiter,
    )

    creds = _run(provider.login(callbacks))

    assert creds.access_token == "access-123"
    assert calls[0][1]["code"] == "auth_code"
    assert (
        "Callback not received; waiting for manual code input"
        in callbacks.progress_messages
    )
    assert (
        "Using manually entered authorization code without OAuth state validation"
        in callbacks.progress_messages
    )
    assert calls[0][1]["state"] == _STATE
    assert calls[0][1]["code_verifier"] == _VERIFIER


def test_login_redacts_verifier_from_token_exchange_error() -> None:
    async def leaking_post(_url: str, body: dict[str, str]) -> dict[str, object]:
        raise RuntimeError(f"failed request: {body}")

    provider = AnthropicOAuthProvider(
        http_post_json=leaking_post,
        pkce_generator=lambda: (_VERIFIER, _CHALLENGE),
        state_generator=lambda: _STATE,
        browser_opener=lambda _url: False,
        callback_waiter=_return_callback_url,
    )

    with pytest.raises(OAuthError, match="token exchange failed") as captured:
        _run(provider.login(_Callbacks()))

    assert _VERIFIER not in str(captured.value)
    assert captured.value.__context__ is None


def test_refresh_token_posts_refresh_request() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {
            "access_token": "access-456",
            "refresh_token": "refresh-456",
            "expires_in": 1800,
        }

    provider = AnthropicOAuthProvider(
        http_post_json=fake_post,
        time_fn=lambda: 2_000.0,
    )

    creds = _run(
        provider.refresh_token(
            OAuthCredentials(
                provider="anthropic",
                access_token="access-123",
                refresh_token="refresh-123",
                expires_at=time.time() - 10,
            )
        )
    )

    assert calls == [
        (
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": "refresh-123",
            },
        )
    ]
    assert creds.access_token == "access-456"
    assert creds.refresh_token == "refresh-456"
    assert creds.expires_at == 3_500.0


def test_refresh_without_refresh_token_requires_reauthentication() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_post(url: str, body: dict[str, str]) -> dict[str, object]:
        calls.append((url, body))
        return {}

    credentials = OAuthCredentials(
        provider="anthropic",
        access_token="access-secret",
        refresh_token=None,
        expires_at=100.0,
    )
    provider = AnthropicOAuthProvider(http_post_json=fake_post)

    with pytest.raises(OAuthReauthenticationRequiredError) as captured:
        _run(provider.refresh_token(credentials))

    rendered = f"{captured.value!r} {captured.value}"
    assert "log in again" in rendered
    assert "access-secret" not in rendered
    assert credentials.expires_at == 100.0
    assert calls == []


async def _return_callback_url(*_args, **_kwargs) -> str:
    return f"{REDIRECT_URI}?code=auth_code&state={_STATE}"


async def _return_wrong_state_url(*_args, **_kwargs) -> str:
    return "http://localhost:53692/callback?code=auth_code&state=wrong-state"


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


@dataclass
class _Callbacks:
    manual_code_input: str = ""
    prompt_response: str = ""

    def __post_init__(self) -> None:
        self.auth_info: dict | None = None
        self.progress_messages: list[str] = []

    def on_auth(self, info: dict) -> None:
        self.auth_info = info

    async def on_prompt(self, prompt: dict) -> str:
        return self.prompt_response

    def on_progress(self, message: str) -> None:
        self.progress_messages.append(message)

    async def on_manual_code_input(self) -> str:
        return self.manual_code_input

    @property
    def signal(self) -> object | None:
        return None

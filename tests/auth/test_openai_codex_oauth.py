from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlparse

import pytest

from loushang.ai.auth import (
    get_default_oauth_registry,
    register_builtin_oauth_providers,
)
from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.contrib.openai_codex.oauth import (
    AUTHORIZE_URL,
    CLIENT_ID,
    REDIRECT_URI,
    OpenAICodexOAuthProvider,
    register_openai_codex_oauth_provider,
)


def _build_fake_jwt(account_id: str) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{header}.{payload}.sig"


def test_openai_codex_login_uses_callback_result() -> None:
    callbacks = _Callbacks()
    auth_calls: list[tuple[str, dict[str, str]]] = []
    token = _build_fake_jwt("acc_1")
    provider = OpenAICodexOAuthProvider(
        pkce_generator=lambda: ("verifier-1", "challenge-1"),
        state_generator=lambda: "state-1",
        browser_opener=lambda _url: True,
        callback_waiter=lambda *_args, **_kwargs: asyncio.sleep(
            0, result=f"{REDIRECT_URI}?code=code-1&state=state-1"
        ),
        http_post_form=lambda url, body: _fake_post_form(
            auth_calls,
            url,
            body,
            {
                "access_token": token,
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "openid profile",
            },
        ),
        time_fn=lambda: 1000.0,
    )

    creds = asyncio.run(provider.login(callbacks))

    parsed = urlparse(callbacks.auth_info["url"])
    assert callbacks.auth_info["url"].startswith(f"{AUTHORIZE_URL}?")
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.openai.com"
    assert parsed.path == "/oauth/authorize"
    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["state"] == ["state-1"]
    assert params["code_challenge"] == ["challenge-1"]
    assert callbacks.progress_messages == [
        "Opened browser for OpenAI Codex login",
        "Waiting for OpenAI Codex authorization callback",
    ]
    assert auth_calls == [
        (
            "https://auth.openai.com/oauth/token",
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": "code-1",
                "code_verifier": "verifier-1",
                "redirect_uri": REDIRECT_URI,
            },
        )
    ]
    assert asdict(creds) == asdict(
        OAuthCredentials(
            provider="openai-codex",
            access_token=token,
            refresh_token="refresh-1",
            expires_at=4300.0,
            extra={
                "account_id": "acc_1",
                "token_type": "Bearer",
                "scope": "openid profile",
            },
        )
    )


def test_openai_codex_login_falls_back_to_manual_input() -> None:
    callbacks = _Callbacks(manual_code_input="code-2#state-2")
    provider = OpenAICodexOAuthProvider(
        pkce_generator=lambda: ("verifier-2", "challenge-2"),
        state_generator=lambda: "state-2",
        browser_opener=lambda _url: False,
        callback_waiter=lambda *_args, **_kwargs: asyncio.sleep(0, result=None),
        http_post_form=lambda _url, _body: asyncio.sleep(
            0,
            result={
                "access_token": _build_fake_jwt("acc_2"),
                "refresh_token": "refresh-2",
                "expires_in": 1800,
            },
        ),
        time_fn=lambda: 200.0,
    )

    creds = asyncio.run(provider.login(callbacks))

    assert creds.extra == {"account_id": "acc_2"}
    assert callbacks.progress_messages == [
        "Waiting for OpenAI Codex authorization callback",
        "Callback not received; waiting for manual code input",
    ]


def test_openai_codex_login_rejects_state_mismatch() -> None:
    callbacks = _Callbacks(manual_code_input=f"{REDIRECT_URI}?code=code-3&state=wrong")
    provider = OpenAICodexOAuthProvider(
        pkce_generator=lambda: ("verifier-3", "challenge-3"),
        state_generator=lambda: "state-3",
        browser_opener=lambda _url: False,
        callback_waiter=lambda *_args, **_kwargs: asyncio.sleep(0, result=None),
        http_post_form=lambda _url, _body: asyncio.sleep(0, result={}),
    )

    with pytest.raises(ValueError, match="state mismatch"):
        asyncio.run(provider.login(callbacks))


def test_openai_codex_refresh_exchanges_refresh_token() -> None:
    calls: list[tuple[str, dict[str, str]]] = []
    provider = OpenAICodexOAuthProvider(
        http_post_form=lambda url, body: _fake_post_form(
            calls,
            url,
            body,
            {
                "access_token": _build_fake_jwt("acc_4"),
                "refresh_token": "refresh-4b",
                "expires_in": 7200,
            },
        ),
        time_fn=lambda: 500.0,
    )

    refreshed = asyncio.run(
        provider.refresh_token(
            OAuthCredentials(
                provider="openai-codex",
                access_token="old-token",
                refresh_token="refresh-4",
                expires_at=0.0,
            )
        )
    )

    assert calls == [
        (
            "https://auth.openai.com/oauth/token",
            {
                "grant_type": "refresh_token",
                "refresh_token": "refresh-4",
                "client_id": CLIENT_ID,
            },
        )
    ]
    assert refreshed.refresh_token == "refresh-4b"
    assert refreshed.expires_at == 7400.0
    assert refreshed.extra == {"account_id": "acc_4"}


def test_openai_codex_refresh_requires_refresh_token() -> None:
    provider = OpenAICodexOAuthProvider()
    with pytest.raises(ValueError, match="missing refresh_token"):
        asyncio.run(
            provider.refresh_token(
                OAuthCredentials(
                    provider="openai-codex",
                    access_token="old-token",
                    refresh_token=None,
                )
            )
        )


def test_register_builtin_oauth_providers_excludes_openai_codex() -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    register_builtin_oauth_providers()
    assert registry.get("openai-codex") is None


def test_register_builtin_oauth_providers_lists_anthropic_only() -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    register_builtin_oauth_providers()

    providers = registry.list()

    assert [provider.id for provider in providers] == ["anthropic"]


def test_clear_then_register_builtin_oauth_providers_restores_anthropic_only() -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    register_builtin_oauth_providers()
    assert registry.get("openai-codex") is None
    assert registry.get("anthropic") is not None


def test_openai_codex_contrib_registers_oauth_provider_explicitly() -> None:
    registry = get_default_oauth_registry()
    registry.clear()
    register_openai_codex_oauth_provider()
    assert registry.get("openai-codex") is not None


async def _fake_post_form(
    calls: list[tuple[str, dict[str, str]]],
    url: str,
    body: dict[str, str],
    payload: dict[str, object],
) -> dict[str, object]:
    calls.append((url, body))
    return payload


@dataclass
class _Callbacks:
    manual_code_input: str = ""

    def __post_init__(self) -> None:
        self.auth_info: dict | None = None
        self.progress_messages: list[str] = []

    def on_auth(self, info: dict) -> None:
        self.auth_info = info

    async def on_prompt(self, prompt: dict) -> str:
        raise AssertionError(f"unexpected prompt: {prompt}")

    def on_progress(self, message: str) -> None:
        self.progress_messages.append(message)

    async def on_manual_code_input(self) -> str:
        return self.manual_code_input

    @property
    def signal(self) -> object | None:
        return None

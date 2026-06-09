from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from loushang.ai.auth.providers.anthropic import (
	AUTHORIZE_URL,
	CLIENT_ID,
	REDIRECT_URI,
	TOKEN_URL,
	AnthropicOAuthProvider,
	generate_pkce_pair,
)
from loushang.ai.auth.types import OAuthCredentials


def test_generate_pkce_pair_returns_urlsafe_verifier_and_challenge() -> None:
	verifier, challenge = generate_pkce_pair()

	assert verifier
	assert challenge
	assert "=" not in verifier
	assert "=" not in challenge


def test_anthropic_oauth_provider_source_stays_python_311_compatible() -> None:
	source = Path("src/loushang/ai/auth/providers/anthropic.py").read_text()

	assert '?{\n' not in source


def test_login_exchanges_authorization_code_and_returns_credentials() -> None:
	calls: list[tuple[str, dict[str, str]]] = []
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
		pkce_generator=lambda: ("test-verifier", "test-challenge"),
		browser_opener=lambda _url: True,
		callback_waiter=_return_callback_url,
		time_fn=lambda: 1_000.0,
	)

	creds = _run(provider.login(callbacks))

	assert callbacks.auth_info is not None
	assert callbacks.auth_info["url"].startswith(AUTHORIZE_URL)
	assert "client_id=" + CLIENT_ID in callbacks.auth_info["url"]
	assert "code_challenge=test-challenge" in callbacks.auth_info["url"]
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
				"state": "test-verifier",
				"redirect_uri": REDIRECT_URI,
				"code_verifier": "test-verifier",
			},
		)
	]
	assert asdict(creds) == asdict(OAuthCredentials(
		provider="anthropic",
		access_token="access-123",
		refresh_token="refresh-123",
		expires_at=4_300.0,
		extra={"token_type": "Bearer", "scope": "user:inference"},
	))


def test_login_rejects_state_mismatch() -> None:
	provider = AnthropicOAuthProvider(
		http_post_json=_unexpected_post,
		pkce_generator=lambda: ("expected-state", "test-challenge"),
		browser_opener=lambda _url: False,
		callback_waiter=_return_wrong_state_url,
	)
	callbacks = _Callbacks()

	with pytest.raises(ValueError, match="state mismatch"):
		_run(provider.login(callbacks))


def test_login_falls_back_to_manual_input_when_callback_waiter_fails() -> None:
	calls: list[tuple[str, dict[str, str]]] = []
	callbacks = _Callbacks(
		manual_code_input="http://localhost:53692/callback?code=auth_code&state=test-verifier"
	)

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
		pkce_generator=lambda: ("test-verifier", "test-challenge"),
		browser_opener=lambda _url: False,
		callback_waiter=broken_callback_waiter,
	)

	creds = _run(provider.login(callbacks))

	assert creds.access_token == "access-123"
	assert calls[0][1]["code"] == "auth_code"
	assert "Callback not received; waiting for manual code input" in callbacks.progress_messages


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


def test_refresh_without_refresh_token_keeps_fallback_extension() -> None:
	provider = AnthropicOAuthProvider(time_fn=lambda: 5_000.0)

	creds = _run(
		provider.refresh_token(
			OAuthCredentials(
				provider="anthropic",
				access_token="access-123",
				refresh_token=None,
				expires_at=100.0,
			)
		)
	)

	assert creds.access_token == "access-123"
	assert creds.expires_at == 8_600.0


async def _unexpected_post(url: str, body: dict[str, str]) -> dict[str, object]:
	raise AssertionError(f"unexpected HTTP call: {url} {body}")


async def _return_callback_url(*_args, **_kwargs) -> str:
	return "http://localhost:53692/callback?code=auth_code&state=test-verifier"


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

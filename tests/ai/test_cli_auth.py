from __future__ import annotations

import pytest

from loushang.ai.auth.registry import get_default_oauth_registry
from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.cli.__main__ import main


class _FakeProvider:
    id = "openai-codex"
    name = "OpenAI Codex"

    def uses_callback_server(self) -> bool:
        return False

    async def login(self, callbacks) -> OAuthCredentials:
        callbacks.on_auth({"url": "https://chatgpt.com", "instructions": "Sign in"})
        callbacks.on_progress("Waiting")
        return OAuthCredentials(
            provider=self.id,
            access_token="token",
            expires_at=123.0,
            extra={"account_id": "acc_1", "plan": "pro"},
        )

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        return credentials

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        return models


@pytest.fixture(autouse=True)
def _reset_oauth_registry(monkeypatch: pytest.MonkeyPatch):
    registry = get_default_oauth_registry()
    registry.reset_oauth_providers()
    registry.register_oauth_provider(_FakeProvider(), source_id="test")
    monkeypatch.setattr(
        "loushang.ai.cli.__main__.register_builtin_oauth_providers",
        lambda: None,
    )


def test_auth_providers_outputs_registered_oauth_providers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["auth", "providers"])

    captured = capsys.readouterr()
    assert "openai-codex" in captured.out


def test_auth_show_outputs_stored_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "loushang.ai.cli.__main__.load_credential_store",
        lambda: {
            "providers": {
                "openai-codex": OAuthCredentials(
                    provider="openai-codex",
                    access_token="token",
                    expires_at=123.0,
                    extra={"account_id": "acc_1"},
                )
            },
            "endpoints": {},
            "models": {},
        },
    )

    main(["auth", "show", "openai-codex"])

    captured = capsys.readouterr()
    assert "has_credentials" in captured.out
    assert "acc_1" in captured.out
    assert '"source": "stored"' in captured.out


def test_auth_login_uses_oauth_login(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    async def _fake_login(provider_id, callbacks, *, endpoint_id=None, model_id=None, persist=True):
        assert provider_id == "openai-codex"
        assert endpoint_id is None
        assert model_id is None
        assert persist is True
        callbacks.on_auth({"url": "https://chatgpt.com", "instructions": "Sign in"})
        callbacks.on_progress("Waiting")
        return OAuthCredentials(
            provider="openai-codex",
            access_token="token",
            expires_at=123.0,
            extra={"account_id": "acc_1", "plan": "pro"},
        )

    monkeypatch.setattr("loushang.ai.cli.__main__.oauth_login", _fake_login)

    main(["auth", "login", "openai-codex"])

    captured = capsys.readouterr()
    assert "LOGIN_URL https://chatgpt.com" in captured.out
    assert '"provider": "openai-codex"' in captured.out
    assert '"stored": true' in captured.out
    assert '"source": "stored"' in captured.out


def test_auth_login_can_prompt_for_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["1", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    async def _fake_login(provider_id, callbacks, *, endpoint_id=None, model_id=None, persist=True):
        assert provider_id == "openai-codex"
        assert endpoint_id is None
        assert model_id is None
        assert persist is True
        return OAuthCredentials(
            provider="openai-codex",
            access_token="token",
            expires_at=123.0,
            extra={"account_id": "acc_1"},
        )

    monkeypatch.setattr("loushang.ai.cli.__main__.oauth_login", _fake_login)

    main(["auth", "login"])

    captured = capsys.readouterr()
    assert "Select OAuth provider:" in captured.out
    assert "1. openai-codex (OpenAI Codex)" in captured.out

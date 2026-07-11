from __future__ import annotations

import base64
import json

import pytest

import loushang.auth as auth
from loushang.auth.providers.openai_codex import (
    get_codex_cli_oauth_credentials,
    load_codex_cli_auth,
)


def _build_fake_jwt(*, expires_at: object) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expires_at}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    return f"header.{payload}.signature"


def test_get_codex_cli_oauth_credentials_reads_chatgpt_auth_payload(
    monkeypatch,
) -> None:
    access_token = _build_fake_jwt(expires_at=2_000_000_000.0)
    monkeypatch.setattr(
        "loushang.auth.providers.openai_codex.load_codex_cli_auth",
        lambda: {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "refresh-token",
                "account_id": "acc_1",
            },
            "last_refresh": "2026-04-21T00:00:00Z",
        },
    )

    credentials = get_codex_cli_oauth_credentials()

    assert credentials is not None
    assert credentials.provider == "openai-codex"
    assert credentials.access_token == access_token
    assert credentials.refresh_token == "refresh-token"
    assert credentials.expires_at == 1_999_999_700.0
    assert credentials.extra == {
        "source": "codex-cli",
        "auth_mode": "chatgpt",
        "account_id": "acc_1",
    }
    assert auth.get_codex_cli_oauth_credentials is get_codex_cli_oauth_credentials
    assert auth.OpenAICodexOAuthProvider is not None


def test_get_codex_cli_oauth_credentials_ignores_non_chatgpt_auth_mode(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "loushang.auth.providers.openai_codex.load_codex_cli_auth",
        lambda: {
            "auth_mode": "apiKey",
            "OPENAI_API_KEY": "sk-test",
            "tokens": {},
        },
    )

    assert get_codex_cli_oauth_credentials() is None


@pytest.mark.parametrize("expires_at", [True, float("nan"), float("inf"), "later"])
def test_get_codex_cli_oauth_credentials_preserves_unknown_expiry(
    monkeypatch,
    expires_at: object,
) -> None:
    monkeypatch.setattr(
        "loushang.auth.providers.openai_codex.load_codex_cli_auth",
        lambda: {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": _build_fake_jwt(expires_at=expires_at),
                "account_id": "acc_1",
            },
        },
    )

    credentials = get_codex_cli_oauth_credentials()

    assert credentials is not None
    assert credentials.expires_at is None


def test_load_codex_cli_auth_preserves_default_discovery_error_contract(
    monkeypatch,
    tmp_path,
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        "loushang.auth.providers.openai_codex._codex_cli_auth_path",
        lambda: str(auth_path),
    )

    assert load_codex_cli_auth() is None
    with pytest.raises(json.JSONDecodeError):
        load_codex_cli_auth(auth_path)

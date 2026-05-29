from __future__ import annotations

from loushang.ai.cli.codex_auth import get_codex_cli_oauth_credentials


def test_get_codex_cli_oauth_credentials_reads_chatgpt_auth_payload(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "loushang.ai.cli.codex_auth.load_codex_cli_auth",
        lambda: {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "chatgpt-access-token",
                "refresh_token": "refresh-token",
                "account_id": "acc_1",
            },
            "last_refresh": "2026-04-21T00:00:00Z",
        },
    )

    credentials = get_codex_cli_oauth_credentials()

    assert credentials is not None
    assert credentials.provider == "openai-codex"
    assert credentials.access_token == "chatgpt-access-token"
    assert credentials.refresh_token == "refresh-token"
    assert credentials.extra == {
        "source": "codex-cli",
        "auth_mode": "chatgpt",
        "account_id": "acc_1",
    }


def test_get_codex_cli_oauth_credentials_ignores_non_chatgpt_auth_mode(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "loushang.ai.cli.codex_auth.load_codex_cli_auth",
        lambda: {
            "auth_mode": "apiKey",
            "OPENAI_API_KEY": "sk-test",
            "tokens": {},
        },
    )

    assert get_codex_cli_oauth_credentials() is None

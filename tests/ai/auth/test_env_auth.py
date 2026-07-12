from __future__ import annotations

from loushang.ai.auth.env import get_env_oauth_credentials


def test_get_env_oauth_credentials_reads_provider_prefix_env_names() -> None:
    credentials = get_env_oauth_credentials(
        "openai-codex",
        env={
            "OPENAI_CODEX_ACCESS_TOKEN": "token-1",
            "OPENAI_CODEX_ACCOUNT_ID": "acc_1",
            "OPENAI_CODEX_PLAN": "pro",
            "CHATGPT_ACCESS_TOKEN": "ignored-token",
        },
    )

    assert credentials is not None
    assert credentials.provider == "openai-codex"
    assert credentials.access_token == "token-1"
    assert credentials.extra == {"account_id": "acc_1", "plan": "pro"}


def test_get_env_oauth_credentials_ignores_chatgpt_aliases() -> None:
    credentials = get_env_oauth_credentials(
        "openai-codex",
        env={
            "CHATGPT_ACCESS_TOKEN": "token-1",
            "CHATGPT_ACCOUNT_ID": "acc_1",
            "CHATGPT_PLAN": "pro",
        },
    )

    assert credentials is None

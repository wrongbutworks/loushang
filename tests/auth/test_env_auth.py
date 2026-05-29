from __future__ import annotations

from loushang.ai.auth.env import get_env_oauth_credentials


def test_get_env_oauth_credentials_reads_openai_codex_env_names() -> None:
    credentials = get_env_oauth_credentials(
        "openai-codex",
        env={
            "CHATGPT_ACCESS_TOKEN": "token-1",
            "CHATGPT_ACCOUNT_ID": "acc_1",
            "CHATGPT_PLAN": "pro",
        },
    )

    assert credentials is not None
    assert credentials.provider == "openai-codex"
    assert credentials.access_token == "token-1"
    assert credentials.extra == {"account_id": "acc_1", "plan": "pro"}

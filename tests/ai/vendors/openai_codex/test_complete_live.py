from __future__ import annotations

import asyncio

import pytest

from loushang.ai import get_model
from loushang.ai.auth import (
    load_credentials,
    register_builtin_oauth_providers,
    resolve_oauth_api_key,
)
from loushang.ai.contrib.openai_codex import (
    OpenAICodexResponsesOptions,
    register_openai_codex_contrib,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.vendor_verification,
]


def test_openai_codex_complete_live() -> None:
    register_builtin_oauth_providers()
    register_openai_codex_contrib()
    credentials = load_credentials().get("openai-codex")
    if credentials is None:
        pytest.skip(
            "openai-codex credentials not found; run `loushang.ai.cli auth login openai-codex` first"
        )

    account_id = (credentials.extra or {}).get("account_id") or (
        credentials.extra or {}
    ).get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id:
        pytest.skip("openai-codex credentials missing account_id")
    try:
        resolved_api_key = resolve_oauth_api_key(
            "openai-codex",
            credentials={"openai-codex": credentials},
            persist_refresh=False,
        )
    except Exception as exc:
        pytest.skip(f"openai-codex credentials could not be refreshed: {exc}")
    if resolved_api_key is None:
        pytest.skip("openai-codex credentials could not be resolved to an API key")

    model = get_model("openai-codex", "openai-codex-responses", "gpt-5.3-codex")

    async def _run() -> None:
        message = await model.complete(
            {
                "system_prompt": "You are Codex. Keep answers short.",
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            },
            OpenAICodexResponsesOptions(
                oauth_credentials={"openai-codex": credentials},
                reasoning="low",
                text_verbosity="low",
                timeout=30,
            ),
        )

        if (
            message.response_id is None
            and message.error_message
            and "model is not supported" in message.error_message
            and "ChatGPT account" in message.error_message
        ):
            pytest.skip(message.error_message)
        assert message.response_id is not None
        assert message.stop_reason in {"stop", "length"}
        text = "".join(
            part.text
            for part in message.content
            if getattr(part, "type", None) == "text"
        ).strip()
        assert text

    asyncio.run(_run())

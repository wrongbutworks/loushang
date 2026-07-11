"""Call an OpenAI model with an existing ChatGPT Coding Plan login."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    get_model,
    stream,
)
from loushang.auth import OAuthCredentials

PROVIDER_ID = "openai"
ENDPOINT_ID = "openai-responses-chatgpt"
MODEL_ID = "gpt-5.5-chatgpt"
USER_PROMPT = "Reply exactly: ok"


def load_call_auth(
    path: Path | None = None,
) -> tuple[OAuthCredentials, dict[str, str]]:
    auth_path = path or Path.home() / ".codex" / "auth.json"
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"Codex auth file not found: {auth_path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Codex auth file is not valid JSON: {auth_path}") from error

    if not isinstance(payload, dict):
        raise RuntimeError("Codex auth file must contain a JSON object")
    if payload.get("auth_mode") != "chatgpt":
        raise RuntimeError("Codex auth file must use auth_mode='chatgpt'")

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise RuntimeError("Codex auth file is missing the tokens object")
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("Codex auth file is missing tokens.access_token")
    account_id = tokens.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise RuntimeError("Codex auth file is missing tokens.account_id")

    return (
        OAuthCredentials(
            provider=PROVIDER_ID,
            access_token=access_token.strip(),
        ),
        {"chatgpt-account-id": account_id.strip()},
    )


async def run(path: Path | None = None) -> str:
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    credentials, headers = load_call_auth(path)
    events = await stream(
        model,
        {"messages": [{"role": "user", "content": USER_PROMPT}]},
        CallOptions(
            oauth_credentials=credentials,
            headers=headers,
            reasoning=ReasoningOptions(effort="low"),
        ),
    )
    message = await events.result()
    text = "".join(
        part.text for part in message.content if getattr(part, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError(message.error_message or "Model returned no text")
    return text


def main() -> None:
    print(asyncio.run(run()))


if __name__ == "__main__":
    main()

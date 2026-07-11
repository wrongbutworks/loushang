"""Call an OpenAI model with an existing ChatGPT Coding Plan login."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from loushang.ai import (
    CallOptions,
    OAuthBearerAuth,
    ReasoningOptions,
    get_model,
    stream,
)
from loushang.auth import (
    OAuthCredentials,
    OpenAICodexOAuthProvider,
    get_codex_cli_oauth_credentials,
)

PROVIDER_ID = "openai"
ENDPOINT_ID = "openai-responses-chatgpt"
MODEL_ID = "gpt-5.5-chatgpt"
USER_PROMPT = "Reply exactly: ok"


def load_credentials(path: Path | None = None) -> OAuthCredentials:
    auth_path = path or Path.home() / ".codex" / "auth.json"
    if not auth_path.is_file():
        raise RuntimeError(f"Codex auth file not found: {auth_path}")
    try:
        credentials = get_codex_cli_oauth_credentials(auth_path)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Failed to read Codex auth file: {auth_path}") from error
    if credentials is None:
        raise RuntimeError(
            "Codex auth file must contain a valid ChatGPT login with "
            "access_token and account_id"
        )
    return credentials


async def resolve_call_auth(
    path: Path | None = None,
) -> tuple[OAuthBearerAuth, dict[str, str]]:
    credentials = load_credentials(path)
    provider = OpenAICodexOAuthProvider()
    expires_at = credentials.expires_at
    if expires_at is None:
        raise RuntimeError(
            "Codex access token expiry cannot be verified; run `codex login` "
            "to update the credential store"
        )
    if expires_at is not None and expires_at <= time.time():
        raise RuntimeError(
            "Codex access token is expired; run `codex login` so Codex CLI "
            "can refresh its credential store"
        )

    access_token = provider.get_api_key(credentials).strip()
    if not access_token:
        raise RuntimeError("Codex OAuth provider returned an empty access token")
    headers = provider.get_auth_headers(credentials)
    if "chatgpt-account-id" not in headers:
        raise RuntimeError("Codex OAuth credentials are missing the ChatGPT account ID")
    return OAuthBearerAuth(access_token=access_token), headers


async def run(path: Path | None = None) -> str:
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    auth, headers = await resolve_call_auth(path)
    events = await stream(
        model,
        {"messages": [{"role": "user", "content": USER_PROMPT}]},
        CallOptions(
            auth=auth,
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

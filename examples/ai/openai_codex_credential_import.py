"""Call an OpenAI model through the experimental Codex credential source."""

from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    get_model,
    stream,
)
from loushang.ai.auth import (
    AuthExtensionRegistry,
    OpenAICodexCredentialSource,
    get_auth,
)

MODEL_REF = ("openai", "coding-responses", "gpt-5.5")
USER_PROMPT = "Reply exactly: ok"


async def run(path: Path | None = None) -> str:
    model = get_model(*MODEL_REF)
    extensions = (
        AuthExtensionRegistry([OpenAICodexCredentialSource(path)])
        if path is not None
        else None
    )
    request_auth = await get_auth(model, extensions=extensions)
    events = await stream(
        model,
        {"messages": [{"role": "user", "content": USER_PROMPT}]},
        CallOptions(reasoning=ReasoningOptions(effort="low")),
        auth=request_auth,
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

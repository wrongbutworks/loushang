"""Call an OpenAI model with an existing ChatGPT Coding Plan login."""

from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.ai import (
    CallOptions,
    ReasoningOptions,
    get_model,
    stream,
)

MODEL_REF = ("openai", "coding-responses", "gpt-5.5")
USER_PROMPT = "Reply exactly: ok"


async def run(path: Path | None = None) -> str:
    events = await stream(
        get_model(*MODEL_REF),
        {"messages": [{"role": "user", "content": USER_PROMPT}]},
        CallOptions(
            credential_file=path,
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

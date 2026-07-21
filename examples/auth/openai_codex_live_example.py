"""Call the Codex endpoint with an existing Codex CLI ChatGPT login."""

from __future__ import annotations

import asyncio
import json
import sys

import loushang.ai as ai

MODEL_REF = ("openai", "coding-responses", "gpt-5.5")
USER_PROMPT = "Reply exactly: ok"


async def run() -> str:
    model = ai.get_model(*MODEL_REF)
    request_auth = await ai.auth.get_auth(model)
    events = await ai.stream(
        model,
        {"messages": [{"role": "user", "content": USER_PROMPT}]},
        ai.CallOptions(reasoning=ai.ReasoningOptions(effort="low")),
        auth=request_auth,
    )
    message = await events.result()
    text = "".join(
        part.text for part in message.content if getattr(part, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError(message.error_message or "Model returned no text")
    return text


def _error_report(error: Exception) -> dict[str, object]:
    if isinstance(error, ai.AIError):
        return {
            "httpStatus": error.info.status_code,
            "message": error.info.message,
        }
    status = getattr(error, "status_code", None)
    return {
        "httpStatus": status if isinstance(status, int) else None,
        "message": str(error),
    }


def main() -> None:
    try:
        print(asyncio.run(run()))
    except Exception as error:
        print(json.dumps(_error_report(error), sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import (
    attach_stream_printer,
    build_kimi_model,
    create_kimi_session,
    describe_model,
    print_message_summary,
)


async def main() -> None:
    model = build_kimi_model(endpoint_id="kimi-code-anthropic")
    model_info = describe_model(model)
    session = create_kimi_session(model=model, thinking_level="medium")
    attach_stream_printer(session, show_thinking=True)

    print("=== Coding Session With Explicit Model Selection ===")
    print(f"Provider: {model_info['provider']}")
    print(f"Model: {model_info['model']}")
    print(f"Endpoint: {model_info['endpoint']}")
    print(f"API: {model_info['api']}")
    print(f"Base URL: {model_info['base_url']}")
    print(f"Thinking level: {session.agent.thinking_level}")
    print()

    await session.prompt("Say hello in one sentence. and write sort program by python")
    print_message_summary(session)
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

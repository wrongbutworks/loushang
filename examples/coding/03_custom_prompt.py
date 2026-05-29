from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import attach_stream_printer, create_kimi_session, make_appended_prompt


async def main() -> None:
    print("=== Replace Prompt ===")
    replaced = create_kimi_session(
        system_prompt=(
            "You are a helpful assistant that speaks like a pirate. "
            'Always end responses with "Arrr!"'
        )
    )
    attach_stream_printer(replaced)
    await replaced.prompt("What is 2 + 2?")
    print()

    print("=== Modify Prompt ===")
    appended = create_kimi_session(
        system_prompt=make_appended_prompt(
            "- Always be concise\n- Use bullet points when listing things"
        )
    )
    attach_stream_printer(appended)
    await appended.prompt("List 3 benefits of TypeScript.")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

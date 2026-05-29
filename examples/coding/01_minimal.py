from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import (
    CalcTool,
    attach_stream_printer,
    build_kimi_model,
    create_kimi_session,
    describe_model,
    print_message_summary,
)


async def main() -> None:
    model = build_kimi_model()
    model_info = describe_model(model)
    session = create_kimi_session(model=model, tools=[CalcTool()])
    attach_stream_printer(session)

    print("=== Coding Session Minimal ===")
    print(f"Provider: {model_info['provider']}")
    print(f"Model: {model_info['model']}")
    print(f"API: {model_info['api']}")
    print(f"Base URL: {model_info['base_url']}")
    print(f"CWD: {session.session_manager.get_cwd()}")
    print("Tools: calculate")
    print()

    await session.prompt("请使用 calculate 工具计算 1+23 * 145 + 100，并告诉我结果。")
    if session.agent.error_message:
        print(f"[错误: {session.agent.error_message}]", file=sys.stderr)
        raise SystemExit(1)
    print()
    print_message_summary(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

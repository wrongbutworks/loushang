from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import assistant_text_message, build_runtime, print_messages, stream_with_final_message


EXTENSION_SOURCE = """
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent / "lifecycle.log"


def _append(line: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\\n")


def register(api):
    def _session_start(session, ctx):
        _append(f"session_start cwd={ctx.cwd}")

    def _before_agent_start(session, ctx):
        _append("before_agent_start")

    def _session_shutdown(session, ctx):
        _append("session_shutdown")

    api.on("session_start", _session_start)
    api.on("before_agent_start", _before_agent_start)
    api.on("session_shutdown", _session_shutdown)
"""


async def main() -> None:
    with TemporaryDirectory(prefix="loushang-ext-lifecycle-") as tmpdir:
        project_root = Path(tmpdir)
        extensions_dir = project_root / "extensions"
        extensions_dir.mkdir(parents=True)
        extension_file = extensions_dir / "lifecycle_demo.py"
        extension_file.write_text(EXTENSION_SOURCE.strip() + "\n", encoding="utf-8")

        async def stream_fn(model, context, options=None):
            return stream_with_final_message(assistant_text_message("Lifecycle example finished one offline turn."))

        runtime = build_runtime(
            session_dir=project_root / ".loushang-sessions",
            stream_fn=stream_fn,
            system_prompt="Lifecycle extension example.",
        )
        session = await runtime.create_session(cwd=str(project_root))

        print("=== Extension Example: Lifecycle Hooks ===")
        print(f"Project root: {project_root}")
        print(f"Extension file: {extension_file}")
        print()

        await session.prompt("Run one turn so the lifecycle hooks fire.")
        await session.dispose()

        print("Messages:")
        print_messages(session)
        print()

        print("Lifecycle log:")
        print((extensions_dir / "lifecycle.log").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

from __future__ import annotations

import asyncio
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO_ROOT = Path(__file__).resolve().parents[2]
while not (REPO_ROOT / "src").exists() and REPO_ROOT.parent != REPO_ROOT:
    REPO_ROOT = REPO_ROOT.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from loushang.coding.cli.__main__ import run_cli


async def _run_cli(project_root: Path, argv: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = await run_cli(
        argv,
        cwd=project_root,
        stdout=stdout,
        stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


async def main() -> None:
    with TemporaryDirectory(prefix="loushang-coding-cli-session-") as tmpdir:
        project_root = Path(tmpdir)
        print("=== CLI session surface demo ===")
        print(f"Project root: {project_root}")
        print()

        export_code, export_stdout, export_stderr = await _run_cli(
            project_root,
            [
                "--session-name",
                "CLI Session Demo",
                "--export",
                "--export-format",
                "jsonl",
                "--export-result-format",
                "json",
            ],
        )
        print("--session-name + --export-format jsonl -> code", export_code)
        print(export_stdout or "<no output>")
        if export_stderr:
            print(f"stderr: {export_stderr}", file=sys.stderr)

        print()

        list_code, list_stdout, list_stderr = await _run_cli(project_root, ["--list-sessions"])
        print("--list-sessions -> code", list_code)
        print(list_stdout or "<no output>")
        if list_stderr:
            print(f"stderr: {list_stderr}", file=sys.stderr)

        print()

        json_list_code, json_list_stdout, json_list_stderr = await _run_cli(
            project_root,
            ["--list-sessions", "--list-sessions-format", "json"],
        )
        print("--list-sessions --list-sessions-format json -> code", json_list_code)
        print(json_list_stdout or "<no output>")
        if json_list_stderr:
            print(f"stderr: {json_list_stderr}", file=sys.stderr)

        print()
        print("CLI session invocation finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

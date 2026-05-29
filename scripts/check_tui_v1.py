#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


GATE_COMMANDS = (
    ("uv", "--cache-dir", ".uv-cache", "run", "pytest", "tests/tui/test_import_boundaries.py", "-q"),
    (
        "uv",
        "--cache-dir",
        ".uv-cache",
        "run",
        "pytest",
        "tests/tui/test_public_api_guide.py",
        "tests/tui/test_v1_readiness_doc.py",
        "-q",
    ),
    ("make", "test-tui"),
    ("uv", "--cache-dir", ".uv-cache", "run", "mypy", "src/loushang/tui", "--show-error-codes"),
    ("uv", "--cache-dir", ".uv-cache", "run", "ruff", "check", "src/loushang/tui", "tests/tui"),
    ("git", "diff", "--check"),
)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the loushang.tui v1 release gate.")
    parser.add_argument("--list", action="store_true", help="Print gate commands without running them.")
    args = parser.parse_args(argv)

    if args.list:
        for command in GATE_COMMANDS:
            print(_format_command(command))
        return 0

    for command in GATE_COMMANDS:
        print(f"$ {_format_command(command)}", flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

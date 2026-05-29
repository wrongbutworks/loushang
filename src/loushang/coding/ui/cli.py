from __future__ import annotations

import asyncio
import sys

from loushang.coding.cli.__main__ import run_cli


def main() -> None:
    raise SystemExit(asyncio.run(run_cli(("--tui", *sys.argv[1:]))))


__all__ = ["main"]

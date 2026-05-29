from __future__ import annotations

import inspect
from typing import Any


async def run_non_interactive_prompt_loop(**kwargs: Any) -> int:
    stdin = kwargs["stdin"]
    handle_prompt = kwargs["handle_prompt"]
    while True:
        line = stdin.readline()
        if line == "":
            return 0
        text = line.rstrip("\r\n")
        if not text.strip():
            continue
        result = handle_prompt(text)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, int):
            return result

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import time
from typing import Any

from loushang.coding.extensions import ExtensionRunner


ExtensionRunnerProvider = Callable[[], ExtensionRunner | None]
CwdProvider = Callable[[], str]


@dataclass
class ExtensionEventSink:
    get_extension_runner: ExtensionRunnerProvider
    get_cwd: CwdProvider

    _turn_index: int = 0

    async def emit_agent_event(self, event: dict[str, Any]) -> None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return
        event_type = event["type"]
        if event_type == "agent_start":
            self._turn_index = 0
            await extension_runner.emit_event({"type": "agent_start"}, cwd=self.get_cwd())
            return
        if event_type == "turn_start":
            await extension_runner.emit_event(
                {
                    "type": "turn_start",
                    "turn_index": self._turn_index,
                    "timestamp": int(time() * 1000),
                },
                cwd=self.get_cwd(),
            )
            return
        if event_type == "turn_end":
            await extension_runner.emit_event(
                {
                    "type": "turn_end",
                    "turn_index": self._turn_index,
                    "message": event["message"],
                    "tool_results": event["tool_results"],
                },
                cwd=self.get_cwd(),
            )
            self._turn_index += 1
            return
        await extension_runner.emit_event(event, cwd=self.get_cwd())

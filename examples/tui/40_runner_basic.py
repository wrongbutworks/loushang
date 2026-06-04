from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Tui,
    TuiInputResult,
    TuiRunner,
)


@dataclass(slots=True)
class CounterApp(FocusableMixin):
    count: int = 0
    last_event: str = "none"

    def __post_init__(self) -> None:
        super().__init__()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = (
            "Loushang TUI Runner",
            "",
            f"Count: {self.count}",
            f"Last event: {self.last_event}",
            "",
            "Press + or right to increment, - or left to decrement, q to quit.",
        )
        return RenderResult.from_lines([RenderLine(row[: constraints.width]) for row in rows], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if not isinstance(event, InputEvent):
            return None
        self.last_event = _event_label(event)
        if event.kind == "text":
            for char in event.text:
                if char == "+":
                    self.count += 1
                elif char == "-":
                    self.count -= 1
        elif event.kind == "key":
            if event.key == "right":
                self.count += 1
            elif event.key == "left":
                self.count -= 1
        return None


async def main() -> int:
    app = CounterApp()
    tui = Tui()
    tui.add_child(app)
    tui.set_focus(app)

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if _is_quit_event(event):
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _is_quit_event(event: InputEvent) -> bool:
    if event.kind == "key" and event.key in {"ctrl+c", "escape"}:
        return True
    return event.kind == "text" and "q" in event.text.lower()


def _event_label(event: InputEvent) -> str:
    if event.kind == "text":
        return repr(event.text)
    if event.kind == "key":
        return event.key
    return event.kind


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

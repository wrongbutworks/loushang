from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Toast,
    ToastStack,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class ToastApp(FocusableMixin):
    stack: ToastStack = field(
        default_factory=lambda: ToastStack(
            (
                Toast("Welcome", title="Loushang", kind="info", duration_ms=None),
                Toast("Changes saved", kind="success", duration_ms=None),
            ),
            newest_on_top=True,
        )
    )
    counter: int = 0

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        toast_result = self.stack.render(
            RenderConstraints(
                width=constraints.width,
                max_height=max(1, constraints.max_height - 3),
            )
        )
        rows = [
            RenderLine(truncate_to_width("Toast Stack", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            *toast_result.lines,
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "Press i/s/w/d to add, x to dismiss oldest, c to clear, q to quit.",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") != "text":
            return None
        key = getattr(event, "text", "").lower()
        if key == "c":
            self.stack.clear()
            return True
        if key == "x":
            return self.stack.dismiss_oldest()
        kinds = {"i": "info", "s": "success", "w": "warning", "d": "danger"}
        kind = kinds.get(key)
        if kind is None:
            return None
        self.counter += 1
        self.stack.push(f"Toast {self.counter}", kind=kind)
        return True


def build_app() -> Tui:
    tui = Tui()
    app = ToastApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

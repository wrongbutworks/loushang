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
    ThemeResolver,
    Toast,
    ToastStack,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14
TOAST_EXAMPLE_THEME = ThemeResolver(
    defaults={
        "widget.toast.danger": {"color": "red"},
        "widget.toast.info": {"color": "cyan"},
        "widget.toast.message": {"color": "white"},
        "widget.toast.success": {"color": "green"},
        "widget.toast.title": {"bold": True},
        "widget.toast.warning": {"color": "yellow"},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class ToastApp(FocusableMixin):
    stack: ToastStack = field(
        default_factory=lambda: ToastStack(
            (
                Toast("Welcome", title="Loushang", kind="info", duration_ms=None),
                Toast("Changes saved", kind="success", duration_ms=None),
            ),
            newest_on_top=True,
            theme=TOAST_EXAMPLE_THEME,
        )
    )
    counter: int = 0
    last_event: str = "none"
    pipeline_status: str = "waiting"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        toast_result = self.stack.render(
            RenderConstraints(
                width=constraints.width,
                max_height=max(1, constraints.max_height - 9),
            )
        )
        rows = [
            RenderLine(truncate_to_width("Deploy Console", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            _field("Pipeline", "api-server", width=constraints.width),
            _field("Status", self.pipeline_status, width=constraints.width),
            _field("Last event", self.last_event, width=constraints.width),
            RenderLine(""),
            RenderLine("Notifications"),
            *toast_result.lines,
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[i] info  [s] success  [w] warning  [d] danger  [x] dismiss  [c] clear  [q] quit",
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
            self.last_event = "cleared notifications"
            return True
        if key == "x":
            dismissed = self.stack.dismiss_oldest()
            self.last_event = "dismissed oldest" if dismissed else "nothing to dismiss"
            return dismissed
        kinds = {"i": "info", "s": "success", "w": "warning", "d": "danger"}
        kind = kinds.get(key)
        if kind is None:
            return None
        self.counter += 1
        self.stack.push(f"Toast {self.counter}", kind=kind)
        self.last_event = f"{kind} toast added"
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

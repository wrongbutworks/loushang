# Building TUI Apps

English | [中文](../../zh-CN/user-guide/tui.md)

This guide shows how to build a small terminal UI with `loushang.tui`. Use it when you want a product-facing interactive terminal surface. For exact API details, see the [TUI Runner reference](../reference/tui-runner.md).

## Choose The Entry Point

Use `TuiRunner` for normal applications. It owns terminal setup, input parsing, render scheduling, output, and cleanup.

Use lower-level APIs such as `TuiRuntime`, `RenderLoop`, `InputReader`, and `TerminalSession` only when you need a custom loop or a playback harness.

## Render A Root View

A renderable object implements `render(constraints)` and returns `RenderResult`.

```python
from loushang.tui import RenderConstraints, RenderLine, RenderResult


class StatusView:
    def __init__(self) -> None:
        self.status = "Ready"

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            "Loushang TUI",
            "",
            f"Status: {self.status}",
        ]
        return RenderResult.from_lines([RenderLine(row[: constraints.width]) for row in rows], constraints=constraints)
```

Attach it to a `Tui` and run it:

```python
import asyncio

from loushang.tui import Tui, TuiRunner


async def main() -> int:
    tui = Tui()
    tui.add_child(StatusView())
    return await TuiRunner(tui).run()


raise SystemExit(asyncio.run(main()))
```

## Handle Input

Without `on_input`, `TuiRunner` routes events through `tui.handle_input(event)`. This works well when focusable children or surfaces own input.

Pass `on_input` when the app needs top-level commands:

```python
from loushang.tui import InputEvent, TuiInputResult


async def on_input(event: InputEvent, context) -> TuiInputResult:
    if event.kind == "text" and "q" in event.text.lower():
        return context.stop(0)
    context.tui.handle_input(event)
    return TuiInputResult()
```

When `on_input` is provided, it fully owns event handling. Call `context.tui.handle_input(event)` explicitly when you want default focus and surface routing.

## Request Renders From Async Work

If an async task changes visible state while the runner is waiting for input, call `context.request_render(kind)`.

```python
async def refresh(context, view):
    view.status = "Refreshing"
    context.request_render("stream")
```

The request goes through the render scheduler and wakes the input wait loop.

## Use Surfaces For Temporary UI

Use `tui.show_overlay()` for dialogs, selectors, command palettes, and other temporary UI. If the renderable is focusable, it can receive input while the surface is active.

```python
handle = tui.show_overlay(dialog, focus_target=dialog, presentation="modal", anchor="center")
```

Close the returned handle when the surface is no longer needed.

## Examples

- [examples/tui/40_runner_basic.py](../../../examples/tui/40_runner_basic.py): small interactive counter using `TuiRunner`.
- [TUI Runner reference](../reference/tui-runner.md): lifecycle API details.

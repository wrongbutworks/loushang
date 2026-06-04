# TUI Runner

English | [中文](../../zh-CN/reference/tui-runner.md)

`TuiRunner` is the public lifecycle entry point for `loushang.tui`. It wires together terminal mode setup, input parsing, render scheduling, terminal output, and cleanup while keeping the lower-level `Tui`, `TuiRuntime`, `RenderLoop`, `InputReader`, and `TerminalSession` APIs available for advanced use.

## Minimal Usage

```python
import asyncio

from loushang.tui import RenderConstraints, RenderLine, RenderResult, Tui, TuiRunner


class App:
    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine("Hello from loushang.tui")], constraints=constraints)


async def main() -> int:
    tui = Tui()
    tui.add_child(App())
    return await TuiRunner(tui).run()


raise SystemExit(asyncio.run(main()))
```

## Input Handling

If `on_input` is omitted, the runner routes parsed app events through `tui.handle_input(event)`.

If `on_input` is provided, it fully owns event handling. Call `context.tui.handle_input(event)` from the handler when you want the default TUI focus and surface routing path.

```python
from loushang.tui import InputEvent, TuiInputResult


async def on_input(event: InputEvent, context) -> TuiInputResult:
    if event.kind == "text" and "q" in event.text:
        return context.stop(0)
    context.tui.handle_input(event)
    return TuiInputResult(render_requested=True)
```

`TuiInputResult(render_requested=False)` keeps the current frame when an event does not change visible state. `context.stop(code)` returns a result that exits the runner with that code.

## Render Requests

Use `context.request_render(kind)` when an async task changes visible state while the runner is waiting for input. It requests a render through `TuiRuntime` and wakes the input wait loop.

```python
async def refresh_later(context, model):
    model.status = "Refreshing"
    context.request_render("stream")
```

## Terminal Session Customization

Pass `terminal_session_factory` to customize terminal capabilities, raw mode setup, or tests:

```python
from loushang.tui import TerminalSession, TuiRunner


runner = TuiRunner(
    tui,
    terminal_session_factory=lambda stdin, stdout: TerminalSession(stdin=stdin, stdout=stdout),
)
```

The factory receives the active `stdin` and `stdout` and must return a context manager. Capability detection, mode factories, alternate screen behavior, and platform-specific setup are the factory's responsibility.

## Lifecycle Notes

During `run()`, `TuiRunner` temporarily owns `tui.terminal`, `tui._runtime`, `tui.terminal_context`, and the progress reporter. It restores their previous values before returning or re-raising an exception.

Do not run the same `TuiRunner` concurrently. Reentrant `run()` calls raise `RuntimeError`.

See [examples/tui/40_runner_basic.py](../../../examples/tui/40_runner_basic.py) for a small interactive example.

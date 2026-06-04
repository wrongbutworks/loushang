# TUI Runner

[English](../../en/reference/tui-runner.md) | 中文

`TuiRunner` 是 `loushang.tui` 的公共生命周期入口。它负责把终端模式、输入解析、渲染调度、终端输出和退出清理串起来，同时保留底层的 `Tui`、`TuiRuntime`、`RenderLoop`、`InputReader`、`TerminalSession` 供高级场景直接使用。

面向任务的使用说明见 [构建 TUI 应用](../user-guide/tui.md)。

## 最小用法

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

## 输入处理

不传 `on_input` 时，runner 会把解析后的 app event 交给 `tui.handle_input(event)`。

传入 `on_input` 后，handler 完全接管事件处理。如果还想使用默认的 focus 和 surface 路由，需要在 handler 里显式调用 `context.tui.handle_input(event)`。

```python
from loushang.tui import InputEvent, TuiInputResult


async def on_input(event: InputEvent, context) -> TuiInputResult:
    if event.kind == "text" and "q" in event.text:
        return context.stop(0)
    context.tui.handle_input(event)
    return TuiInputResult(render_requested=True)
```

`TuiInputResult(render_requested=False)` 表示事件没有改变可见状态，可以保留当前帧。`context.stop(code)` 会返回一个让 runner 用指定退出码退出的结果。

## 请求渲染

当异步任务在 runner 等待输入时改变了可见状态，使用 `context.request_render(kind)`。它会通过 `TuiRuntime` 请求渲染，并唤醒输入等待循环。

```python
async def refresh_later(context, model):
    model.status = "Refreshing"
    context.request_render("stream")
```

## 自定义 Terminal Session

可以通过 `terminal_session_factory` 自定义终端 capabilities、raw mode 或测试环境：

```python
from loushang.tui import TerminalSession, TuiRunner


runner = TuiRunner(
    tui,
    terminal_session_factory=lambda stdin, stdout: TerminalSession(stdin=stdin, stdout=stdout),
)
```

factory 会收到当前 `stdin` 和 `stdout`，并且必须返回一个 context manager。capabilities、mode factory、alternate screen 和平台相关设置由 factory 内部负责。

## 生命周期说明

`run()` 期间，`TuiRunner` 会临时接管 `tui.terminal`、`tui._runtime`、`tui.terminal_context` 和 progress reporter。正常返回或异常抛出前，它都会恢复这些字段原来的值。

不要并发运行同一个 `TuiRunner`。重入调用 `run()` 会抛出 `RuntimeError`。

小型交互示例见 [examples/tui/40_runner_basic.py](../../../examples/tui/40_runner_basic.py)。

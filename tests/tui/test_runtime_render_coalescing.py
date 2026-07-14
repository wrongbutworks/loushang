from __future__ import annotations

from loushang.tui import (
    FakeTerminalPort,
    RenderConstraints,
    RenderLine,
    RenderLoop,
    RenderResult,
    TerminalSize,
    TuiRuntime,
    delete_kitty_image,
)


class StaticRoot:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self.lines = lines

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine(line) for line in self.lines], constraints=constraints)


def test_runtime_coalesces_pending_stream_render_until_frame_deadline() -> None:
    now = [100]
    root = StaticRoot(("one",))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        now_ms=lambda: now[0],
    )
    runtime.render_now()

    now[0] = 105
    decision = runtime.request_render("stream")
    pending = runtime.request_next_animation_frame()

    assert decision.render_now is False
    assert decision.delay_ms == 45
    assert pending.render_now is False
    assert pending.delay_ms == 45
    assert pending.coalesced is True

    now[0] = 130
    repeated = runtime.request_render("stream")
    still_pending = runtime.request_next_animation_frame()

    assert repeated.render_now is False
    assert repeated.delay_ms == 20
    assert still_pending.render_now is False
    assert still_pending.delay_ms == 20

    now[0] = 150
    due = runtime.request_next_animation_frame()

    assert due.render_now is True
    assert due.delay_ms == 0
    assert due.coalesced is False


def test_runtime_keeps_input_render_requests_immediate() -> None:
    now = [100]
    root = StaticRoot(("one",))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        now_ms=lambda: now[0],
    )
    runtime.render_now()

    now[0] = 105
    runtime.request_render("stream")
    now[0] = 106
    decision = runtime.request_render("input")
    pending = runtime.request_next_animation_frame()

    assert decision.render_now is True
    assert decision.delay_ms == 0
    assert pending.render_now is True
    assert pending.delay_ms == 0


def test_runtime_product_request_preempts_pending_stream_deadline() -> None:
    now = [100]
    root = StaticRoot(("one",))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        now_ms=lambda: now[0],
    )
    runtime.render_now()

    now[0] = 105
    runtime.request_render("stream")
    product = runtime.request_render("product")
    pending = runtime.request_next_animation_frame()

    assert product.render_now is False
    assert product.delay_ms == 11
    assert pending.render_now is False
    assert pending.delay_ms == 11


def test_runtime_coalesced_stream_renders_latest_root_at_deadline() -> None:
    now = [100]
    root = StaticRoot(("initial",))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        now_ms=lambda: now[0],
    )
    runtime.render_now()

    now[0] = 105
    root.lines = ("intermediate",)
    runtime.request_render("stream")
    now[0] = 130
    root.lines = ("latest",)
    runtime.request_render("stream")

    assert runtime.request_next_animation_frame().render_now is False

    now[0] = 150
    assert runtime.request_next_animation_frame().render_now is True
    step = runtime.render_now()

    assert step.diagnostics.current_logical_lines == ("latest",)


def test_runtime_deletes_replaced_kitty_image_once() -> None:
    root = StaticRoot(("\x1b_Ga=T,f=100,t=d,i=77;YWJj\x1b\\",))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=40, rows=5)),
    )

    runtime.render_now()
    root.lines = ("plain",)
    replaced = runtime.render_now()
    unchanged = runtime.render_now()

    assert delete_kitty_image(77) in replaced.frame.serialized_output
    assert delete_kitty_image(77) not in unchanged.frame.serialized_output

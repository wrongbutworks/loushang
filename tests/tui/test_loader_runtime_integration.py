from __future__ import annotations

from collections.abc import Sequence

from loushang.tui import (
    Container,
    FakeTerminalPort,
    Loader,
    RenderLoop,
    RenderScheduler,
    ScreenRoot,
    TerminalFrame,
    TerminalOperation,
    TerminalSize,
    Text,
    TuiRuntime,
)


def test_runtime_collects_nested_loader_animation_sources_and_schedules_next_frame() -> None:
    now = [0]
    loader = Loader(
        message="Working",
        frames=("a", "b"),
        interval_ms=80,
        now_ms=lambda: now[0],
        leading_spacer=False,
    )
    runtime = TuiRuntime(
        render_loop=RenderLoop(ScreenRoot(base=Container([Text("stable", padding_x=0, padding_y=0), loader]))),
        terminal=FakeTerminalPort(size=TerminalSize(columns=16, rows=5)),
        now_ms=lambda: now[0],
    )

    runtime.render_now()
    now[0] = 40
    early = runtime.request_next_animation_frame()
    now[0] = 80
    due = runtime.request_next_animation_frame()

    assert tuple(runtime.animation_sources()) == (loader,)
    assert early.render_now is False
    assert early.delay_ms == 40
    assert due.render_now is True


def test_runtime_marks_scheduler_after_render_and_loader_tick_diffs_only_loader_line() -> None:
    now = [0]
    loader = Loader(
        message="Working",
        frames=("a", "b"),
        interval_ms=80,
        now_ms=lambda: now[0],
        leading_spacer=False,
    )
    root = ScreenRoot(base=Container([Text("stable", padding_x=0, padding_y=0), loader]))
    scheduler = RenderScheduler()
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=16, rows=5)),
        scheduler=scheduler,
        now_ms=lambda: now[0],
    )

    runtime.render_now()
    assert scheduler.last_rendered_at_ms == 0

    now[0] = 80
    decision = runtime.request_animation_frame(loader)
    step = runtime.render_now()

    assert decision.render_now is True
    step.assert_operation_class("changed_range_update")
    assert step.diagnostics.changed_line_range == (1, 1)
    assert step.diagnostics.current_logical_lines == (
        "stable",
        " b Working     ",
    )
    assert scheduler.last_rendered_at_ms == 80


class _SlowFlushTerminal:
    def __init__(self, inner: FakeTerminalPort, *, now: list[int], advance_ms: int) -> None:
        self.inner = inner
        self.now = now
        self.advance_ms = advance_ms

    def size(self) -> TerminalSize:
        return self.inner.size()

    def flush(self, operations: Sequence[TerminalOperation]) -> TerminalFrame:
        frame = self.inner.flush(operations)
        self.now[0] += self.advance_ms
        return frame


def test_runtime_marks_scheduler_after_slow_flush_finishes() -> None:
    now = [0]
    scheduler = RenderScheduler()
    runtime = TuiRuntime(
        render_loop=RenderLoop(ScreenRoot(base=Text("stable", padding_x=0, padding_y=0))),
        terminal=_SlowFlushTerminal(
            FakeTerminalPort(size=TerminalSize(columns=16, rows=5)),
            now=now,
            advance_ms=125,
        ),
        scheduler=scheduler,
        now_ms=lambda: now[0],
    )

    runtime.render_now()

    assert scheduler.last_rendered_at_ms == 125

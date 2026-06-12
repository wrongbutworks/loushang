from __future__ import annotations

import runpy
from dataclasses import dataclass

from loushang.tui import (
    FakeTerminalPort,
    InputEvent,
    RenderLoop,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)


@dataclass(frozen=True, slots=True)
class ExampleFrame:
    label: str
    lines: tuple[str, ...]
    cursor: tuple[int, int]
    operation_class: str | None


def play_example(
    path: str,
    *,
    events: tuple[tuple[str, InputEvent], ...] = (),
    width: int = 80,
    height: int = 20,
) -> tuple[ExampleFrame, ...]:
    namespace = runpy.run_path(path, run_name="__test__")
    tui = namespace["build_app"]()
    port = FakeTerminalPort(size=TerminalSize(columns=width, rows=height))
    runtime = TuiRuntime(render_loop=RenderLoop(tui._screen_root), terminal=port)
    frames = [_render_frame("initial", runtime)]
    for label, event in events:
        tui.handle_input(event)
        frames.append(_render_frame(label, runtime))
    return tuple(frames)


def _render_frame(label: str, runtime: TuiRuntime) -> ExampleFrame:
    step = runtime.render_now()
    return ExampleFrame(
        label=label,
        lines=tuple(
            strip_control_sequences(line).rstrip()
            for line in step.diagnostics.current_logical_lines
        ),
        cursor=(
            step.diagnostics.logical_cursor_row,
            step.diagnostics.logical_cursor_column,
        ),
        operation_class=step.diagnostics.operation_class,
    )

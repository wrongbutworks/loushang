from __future__ import annotations

from typing import TextIO

from loushang.tui.input import InputEvent, InputReader
from loushang.tui.runtime import TuiRuntime
from loushang.tui.scheduler import RenderRequestKind
from loushang.tui.terminal import TerminalOperation


def request_runtime_render(runtime: TuiRuntime, kind: RenderRequestKind) -> None:
    decision = runtime.request_render(kind)
    if decision.render_now:
        runtime.render_now()


def input_events_for_chunk(
    reader: InputReader,
    data: str,
    *,
    terminal_context: object | None = None,
) -> tuple[InputEvent, ...]:
    data = normalize_terminal_input(data, terminal_context=terminal_context)
    batch = reader.feed_batch(data)
    consume_terminal_control_events(batch.control_events, terminal_context=terminal_context)
    return batch.app_events


def flush_pending_input(
    reader: InputReader,
    *,
    terminal_context: object | None = None,
) -> tuple[InputEvent, ...]:
    pending = reader.flush_pending_batch()
    consume_terminal_control_events(pending.control_events, terminal_context=terminal_context)
    return pending.app_events


def consume_terminal_control_events(events: tuple[InputEvent, ...], *, terminal_context: object | None = None) -> None:
    if not events:
        return
    consumer = getattr(terminal_context, "consume_control_events", None)
    if callable(consumer):
        consumer(events)


def terminal_runtime_wakeup_ms(terminal_context: object | None) -> int | None:
    wakeup = getattr(terminal_context, "next_wakeup_delay_ms", None)
    if not callable(wakeup):
        return None
    delay = wakeup()
    return delay if isinstance(delay, int) else None


def poll_terminal_runtime(terminal_context: object | None) -> bool:
    poll = getattr(terminal_context, "flush_keyboard_protocol_fallback_if_due", None)
    if not callable(poll):
        return False
    return bool(poll())


def normalize_terminal_input(data: str, *, terminal_context: object | None = None) -> str:
    normalizer = getattr(terminal_context, "normalize_input_chunk", None)
    if not callable(normalizer):
        return data
    normalized = normalizer(data)
    return normalized if isinstance(normalized, str) else data


def configure_runtime_for_terminal_context(runtime: TuiRuntime, terminal_context: object) -> None:
    capabilities = getattr(terminal_context, "capabilities", None)
    runtime.render_loop.termux_session = bool(getattr(capabilities, "termux_session", False))


def finish_tui_exit(*, runtime: TuiRuntime, stdout: TextIO, exit_code: int) -> int:
    if clear_runtime_bottom_frame_for_exit(runtime):
        return exit_code
    stdout.write("\r\x1b[2K\n")
    stdout.flush()
    return exit_code


def clear_runtime_bottom_frame_for_exit(runtime: TuiRuntime) -> bool:
    render_loop = runtime.render_loop
    current_lines = render_loop.previous_rendered_lines
    if not current_lines:
        return False

    cursor_row = render_loop.previous_cursor_row
    viewport_top = render_loop.previous_viewport_top
    if cursor_row < viewport_top or cursor_row >= len(current_lines):
        return False

    screen_row = cursor_row - viewport_top
    terminal_rows = runtime.terminal.size().rows
    clear_count = min(len(current_lines) - cursor_row, terminal_rows - screen_row)
    if clear_count <= 0:
        return False

    runtime.terminal.flush(exit_bottom_frame_cleanup_operations(clear_count))
    return True


def exit_bottom_frame_cleanup_operations(line_count: int) -> tuple[TerminalOperation, ...]:
    line_count = max(1, line_count)
    operations: list[TerminalOperation] = [
        TerminalOperation.hide_cursor(),
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.carriage_return(),
    ]
    for index in range(line_count):
        operations.append(TerminalOperation.clear_line())
        if index < line_count - 1:
            operations.append(TerminalOperation.newline())
    if line_count > 1:
        operations.append(TerminalOperation.move_relative(lines=-(line_count - 1)))
    operations.extend(
        (
            TerminalOperation.carriage_return(),
            TerminalOperation.end_synchronized_update(),
            TerminalOperation.show_cursor(),
        )
    )
    return tuple(operations)


__all__ = [
    "clear_runtime_bottom_frame_for_exit",
    "configure_runtime_for_terminal_context",
    "consume_terminal_control_events",
    "exit_bottom_frame_cleanup_operations",
    "finish_tui_exit",
    "flush_pending_input",
    "input_events_for_chunk",
    "normalize_terminal_input",
    "poll_terminal_runtime",
    "request_runtime_render",
    "terminal_runtime_wakeup_ms",
]

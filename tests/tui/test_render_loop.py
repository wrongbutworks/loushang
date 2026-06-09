from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from loushang.observability import configure_debug_logging, reset_observability
from loushang.tui import (
    CURSOR_MARKER,
    CursorDeclaration,
    FakeTerminalPort,
    ProcessTerminalPort,
    RenderConstraints,
    RenderLine,
    RenderLoop,
    RenderResult,
    TerminalOperation,
    TerminalPort,
    TerminalProgressReporter,
    TerminalSize,
    TuiRuntime,
    delete_kitty_image,
    wrap_tmux_passthrough,
)


class StaticRoot:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self.lines = lines

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine(line) for line in self.lines], constraints=constraints)


class TextRoot:
    def __init__(self, text: str) -> None:
        self.text = text

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_text(self.text, constraints=constraints)


class RecordingDebugSink:
    def __init__(self) -> None:
        self.events = []

    def write_log(self, **_kwargs) -> None:
        return None

    def write_problem(self, _record) -> None:
        return None

    def write_debug_event(self, record) -> None:
        self.events.append(record)


def test_first_render_flushes_full_logical_lines_without_clearing_scrollback() -> None:
    runtime = TuiRuntime(
        render_loop=RenderLoop(StaticRoot(("hello", "status"))),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
    )

    step = runtime.render_now()

    assert step.diagnostics.operation_class == "first_render"
    assert step.diagnostics.current_logical_lines == ("hello", "status")
    assert step.diagnostics.previous_rendered_lines == ()
    assert step.diagnostics.clear_scrollback_emitted is False
    assert step.frame is not None
    assert step.frame.serialized_output == "\x1b[?2026hhello\r\nstatus\x1b[?2026l"
    assert step.frame.screen_after.visible_lines[:2] == ("hello", "status")


def test_runtime_render_now_emits_tui_render_frame_diagnostics() -> None:
    sink = RecordingDebugSink()
    reset_observability()
    configure_debug_logging(debug_sink=sink, debug_scopes=("tui",))
    try:
        runtime = TuiRuntime(
            render_loop=RenderLoop(StaticRoot(("hello", "status"))),
            terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        )

        runtime.render_now()
    finally:
        reset_observability()

    event = next(event for event in sink.events if event.scope == "tui" and event.name == "render.frame")
    assert event.data["operation_class"] == "first_render"
    assert event.data["logical_line_count"] == 2
    assert event.data["operation_count"] > 0
    assert event.data["plan_ms"] >= 0
    assert event.data["flush_ms"] >= 0
    assert event.data["total_ms"] >= 0


def test_render_plan_context_carries_cursor_and_diff_facts() -> None:
    root = StaticRoot(("alpha",))
    loop = RenderLoop(root)
    size = TerminalSize(columns=20, rows=5)
    first = loop.plan(size)
    loop.commit(first, size=size)

    root.lines = ("alpha", "beta" + CURSOR_MARKER)
    context = loop._build_plan_context(size)

    assert context.raw_current_lines == ("alpha", "beta")
    assert context.current_lines == ("alpha", "beta")
    assert context.declared_cursor == CursorDeclaration(row=1, column=4)
    assert context.cursor == CursorDeclaration(row=1, column=4)
    assert context.changed_range == (1, 1)
    assert context.first_changed == 1
    assert context.last_changed == 1
    assert context.appended_lines == 1
    assert context.append_start == 1


def test_runtime_render_now_does_not_emit_tui_render_frame_when_scope_is_disabled() -> None:
    sink = RecordingDebugSink()
    reset_observability()
    try:
        configure_debug_logging(debug_sink=sink, debug_scopes=set())
        runtime = TuiRuntime(
            render_loop=RenderLoop(StaticRoot(("hello", "status"))),
            terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
        )

        runtime.render_now()

        assert not sink.events

        configure_debug_logging(debug_sink=sink, debug_scopes={"tui"})
        runtime.render_now()
        assert any(event.scope == "tui" and event.name == "render.frame" for event in sink.events)
    finally:
        reset_observability()


def test_fake_terminal_port_implements_terminal_port_boundary() -> None:
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))

    assert isinstance(port, TerminalPort)


def test_append_update_writes_only_appended_lines_and_preserves_previous_snapshot() -> None:
    root = StaticRoot(("one",))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    root.lines = ("one", "two")

    step = runtime.render_now()

    step.assert_operation_class("append_update")
    assert step.diagnostics.previous_rendered_lines == ("one",)
    assert step.diagnostics.changed_line_range == (1, 1)
    assert step.diagnostics.append_start == 1
    assert step.diagnostics.appended_lines == 1
    assert step.diagnostics.operations == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.newline(),
        TerminalOperation.write("two"),
        TerminalOperation.end_synchronized_update(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[:2] == ("one", "two")


def test_append_update_scrolls_below_visible_viewport_without_repaint() -> None:
    root = StaticRoot(tuple(f"line {index}" for index in range(5)))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=3)))
    first = runtime.render_now()
    root.lines = (*root.lines, "line 5")

    step = runtime.render_now()

    assert first.diagnostics.viewport_top == 2
    step.assert_operation_class("append_update")
    assert step.diagnostics.previous_viewport_top == 2
    assert step.diagnostics.viewport_top == 3
    assert step.diagnostics.operations == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.newline(),
        TerminalOperation.write("line 5"),
        TerminalOperation.end_synchronized_update(),
    )
    assert TerminalOperation.clear_screen() not in step.diagnostics.operations
    assert TerminalOperation.clear_scrollback() not in step.diagnostics.operations
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines == ("line 3", "line 4", "line 5")


def test_protected_append_update_scrolls_above_cursor_suffix() -> None:
    previous_lines = (
        "line 1",
        "line 2",
        "",
        "working 1.00s",
        "",
        f"› {CURSOR_MARKER}",
        "",
        "status running",
    )
    current_lines = (
        "line 1",
        "line 2",
        "line 3",
        "line 4",
        "",
        "working 1.10s",
        "",
        f"› {CURSOR_MARKER}",
        "",
        "status running",
    )
    root = TextRoot("\n".join(previous_lines))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=30, rows=8)))
    runtime.render_now()
    root.text = "\n".join(current_lines)

    step = runtime.render_now()

    step.assert_operation_class("protected_append_update")
    assert TerminalOperation.set_scroll_region(top=0, bottom=1) in step.diagnostics.operations
    assert TerminalOperation.reset_scroll_region() in step.diagnostics.operations
    assert step.diagnostics.append_start == 2
    assert step.diagnostics.appended_lines == 2
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines == (
        "line 3",
        "line 4",
        "",
        "working 1.10s",
        "",
        "›",
        "",
        "status running",
    )
    assert step.frame.screen_after.cursor_row == 5
    assert step.frame.screen_after.cursor_column == 2


def test_protected_append_update_waits_until_logical_screen_is_full() -> None:
    previous_lines = (
        "line 1",
        "line 2",
        "",
        "working 1.00s",
        "",
        f"› {CURSOR_MARKER}",
        "",
        "status running",
    )
    current_lines = (
        "line 1",
        "line 2",
        "line 3",
        "line 4",
        "",
        "working 1.10s",
        "",
        f"› {CURSOR_MARKER}",
        "",
        "status running",
    )
    root = TextRoot("\n".join(previous_lines))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=30, rows=12)))
    runtime.render_now()
    root.text = "\n".join(current_lines)

    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert all(operation.kind != "set_scroll_region" for operation in step.diagnostics.operations)


def test_changed_range_update_rewrites_only_visible_changed_rows() -> None:
    root = StaticRoot(("one", "two", "three"))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    root.lines = ("one", "TWO", "three")

    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.diagnostics.changed_line_range == (1, 1)
    assert step.diagnostics.operations == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.move_relative(lines=-1),
        TerminalOperation.carriage_return(),
        TerminalOperation.clear_line(),
        TerminalOperation.write("TWO"),
        TerminalOperation.end_synchronized_update(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[:3] == ("one", "TWO", "three")


def test_changed_range_update_without_declared_cursor_reports_actual_hardware_cursor() -> None:
    root = StaticRoot(("one", "two", "three"))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    root.lines = ("one", "TWO", "three")

    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.frame is not None
    assert step.frame.screen_after.cursor_row == 1
    assert step.frame.screen_after.cursor_column == 3
    assert step.diagnostics.hardware_cursor_row == 1
    assert step.diagnostics.hardware_cursor_column == 3


def test_changed_range_update_uses_pi_style_relative_cursor_movement_inside_viewport() -> None:
    root = StaticRoot(("one", "two", "three", "four", "five"))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=3)))
    first = runtime.render_now()
    root.lines = ("one", "two", "three", "FOUR", "five")

    step = runtime.render_now()

    assert first.diagnostics.viewport_top == 2
    assert first.diagnostics.hardware_cursor_row == 4
    step.assert_operation_class("changed_range_update")
    assert step.diagnostics.previous_viewport_top == 2
    assert step.diagnostics.operations[:4] == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.move_relative(lines=-1),
        TerminalOperation.carriage_return(),
        TerminalOperation.clear_line(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines == ("three", "FOUR", "five")


def test_changed_range_shrink_rewrites_viewport_when_anchor_would_move_up() -> None:
    previous_lines = tuple(f"line {index}" for index in range(36)) + (f"› draft{CURSOR_MARKER}", "", "status running")
    root = TextRoot("\n".join(previous_lines))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=40, rows=28)))
    first = runtime.render_now()
    current_lines = (
        *tuple(f"line {index}" for index in range(31)),
        "assistant final",
        "",
        "worked divider",
        "",
        f"› draft{CURSOR_MARKER}",
        "",
        "status idle",
    )

    root.text = "\n".join(current_lines)
    step = runtime.render_now()

    assert first.diagnostics.viewport_top == 11
    step.assert_operation_class("managed_viewport_repaint")
    assert step.diagnostics.repaint_reason == "viewport_top_decreased_after_shrink"
    assert step.diagnostics.viewport_top == 10
    step.assert_no_clear_scrollback()
    assert TerminalOperation.clear_screen() not in step.diagnostics.operations
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[-4:] == ("", "› draft", "", "status idle")
    assert step.frame.screen_after.cursor_row == 25
    assert step.frame.screen_after.cursor_column == 7


def test_shrinking_content_clears_stale_rows_without_scrolling() -> None:
    root = StaticRoot(("one", "two", "three"))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    root.lines = ("one",)

    step = runtime.render_now()

    step.assert_operation_class("shrink_clear")
    assert step.diagnostics.changed_line_range == (1, 2)
    assert step.diagnostics.operations == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.move_relative(lines=-2),
        TerminalOperation.carriage_return(),
        TerminalOperation.newline(),
        TerminalOperation.clear_line(),
        TerminalOperation.newline(),
        TerminalOperation.clear_line(),
        TerminalOperation.move_relative(lines=-2),
        TerminalOperation.end_synchronized_update(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[:3] == ("one", "", "")


def test_changed_range_shrink_keeps_hardware_cursor_in_sync_after_clearing_stale_rows() -> None:
    previous_lines = (
        "› 你好",
        "",
        "• 你好！有什么我可以帮你的吗？",
        "",
        "─ Worked for 1.93s ─",
        "",
        f"› /{CURSOR_MARKER}",
        "",
        "  /help  Show help",
        "  /quit  Quit",
    )
    root = TextRoot("\n".join(previous_lines))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=40, rows=12)))
    runtime.render_now()
    current_lines = (
        "› 你好",
        "",
        "• 你好！有什么我可以帮你的吗？",
        "",
        "─ Worked for 1.93s ─",
        "",
        f"› {CURSOR_MARKER}",
        "",
        "moonshot/kimi | repo | main | idle",
    )

    root.text = "\n".join(current_lines)
    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[:10] == (
        "› 你好",
        "",
        "• 你好！有什么我可以帮你的吗？",
        "",
        "─ Worked for 1.93s ─",
        "",
        "›",
        "",
        "moonshot/kimi | repo | main | idle",
        "",
    )
    assert step.frame.screen_after.cursor_row == 6
    assert step.frame.screen_after.cursor_column == 2
    assert step.diagnostics.hardware_cursor_row == 6
    assert step.diagnostics.hardware_cursor_column == 2


def test_cursor_marker_is_stripped_and_positions_hardware_cursor() -> None:
    root = TextRoot(f"ab{CURSOR_MARKER}c")
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))

    step = runtime.render_now()

    assert step.diagnostics.current_logical_lines == ("abc",)
    assert step.diagnostics.logical_cursor_row == 0
    assert step.diagnostics.logical_cursor_column == 2
    assert CURSOR_MARKER not in step.frame.serialized_output if step.frame is not None else False
    assert step.diagnostics.operations == (
        TerminalOperation.hide_cursor(),
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.write("abc"),
        TerminalOperation.end_synchronized_update(),
        TerminalOperation.move_column(column=2),
        TerminalOperation.show_cursor(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.cursor_row == 0
    assert step.frame.screen_after.cursor_column == 2


def test_cursor_marker_in_render_lines_is_stripped_and_positions_hardware_cursor() -> None:
    root = StaticRoot((f"ab{CURSOR_MARKER}c",))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))

    step = runtime.render_now()

    assert step.diagnostics.current_logical_lines == ("abc",)
    assert step.diagnostics.logical_cursor_row == 0
    assert step.diagnostics.logical_cursor_column == 2
    assert step.frame is not None
    assert CURSOR_MARKER not in step.frame.serialized_output
    assert step.frame.screen_after.cursor_row == 0
    assert step.frame.screen_after.cursor_column == 2


def test_render_finalization_adds_reset_and_osc8_close_after_styled_lines() -> None:
    root = StaticRoot(("\x1b[31mred", "plain"))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))

    step = runtime.render_now()

    assert step.diagnostics.current_logical_lines == ("\x1b[31mred\x1b[0m\x1b]8;;\x07", "plain")
    assert step.frame is not None
    assert step.frame.serialized_output == "\x1b[?2026h\x1b[31mred\x1b[0m\x1b]8;;\x07\r\nplain\x1b[?2026l"
    assert step.frame.screen_after.cell_style(row=1, column=0).foreground is None


def test_render_finalization_preserves_terminal_image_lines_without_reset_suffix() -> None:
    image_line = "\x1b_Gi=1;AAAA\x1b\\"
    root = StaticRoot((image_line,))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=80, rows=5)))

    step = runtime.render_now()

    assert step.diagnostics.current_logical_lines == (image_line,)
    assert step.frame is not None
    assert step.frame.serialized_output == f"\x1b[?2026h{image_line}\x1b[?2026l"


def test_changed_range_update_deletes_previous_kitty_image_id_before_replacing_line() -> None:
    image_line = "\x1b_Ga=T,f=100,t=d,i=42;AAAA\x1b\\"
    root = StaticRoot((image_line,))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=80, rows=5)))
    runtime.render_now()
    root.lines = ("plain",)

    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.frame is not None
    assert delete_kitty_image(42) in step.frame.serialized_output
    assert step.frame.serialized_output.index(delete_kitty_image(42)) < step.frame.serialized_output.index("plain")


def test_changed_range_update_wraps_kitty_delete_for_tmux_passthrough_image() -> None:
    image_line = wrap_tmux_passthrough("\x1b_Ga=T,f=100,t=d,i=42;AAAA\x1b\\")
    root = StaticRoot((image_line,))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=80, rows=5)))
    runtime.render_now()
    root.lines = ("plain",)

    step = runtime.render_now()

    expected_delete = wrap_tmux_passthrough(delete_kitty_image(42))
    step.assert_operation_class("changed_range_update")
    assert step.frame is not None
    assert expected_delete in step.frame.serialized_output
    assert delete_kitty_image(42) not in step.frame.serialized_output.replace(expected_delete, "")


def test_changed_range_expands_to_unchanged_kitty_images_below_first_change() -> None:
    image_line = "\x1b_Ga=T,f=100,t=d,i=43;BBBB\x1b\\"
    root = StaticRoot(("top", image_line))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=80, rows=5)))
    runtime.render_now()
    root.lines = ("changed", image_line)

    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.diagnostics.changed_line_range == (0, 1)
    assert step.frame is not None
    assert delete_kitty_image(43) in step.frame.serialized_output
    assert image_line in step.frame.serialized_output


def test_resize_repaint_deletes_previous_kitty_image_ids_before_clearing_screen() -> None:
    image_line = "\x1b_Ga=T,f=100,t=d,i=44;CCCC\x1b\\"
    port = FakeTerminalPort(size=TerminalSize(columns=80, rows=5))
    root = StaticRoot((image_line,))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=port)
    runtime.render_now()
    port.resize(TerminalSize(columns=40, rows=5))

    step = runtime.render_now()

    step.assert_operation_class("resize_repaint")
    assert step.frame is not None
    assert delete_kitty_image(44) in step.frame.serialized_output
    assert step.frame.serialized_output.index(delete_kitty_image(44)) < step.frame.serialized_output.index("\x1b[2J")


def test_noop_with_cursor_change_moves_only_hardware_cursor() -> None:
    root = TextRoot(f"a{CURSOR_MARKER}bc")
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    root.text = f"ab{CURSOR_MARKER}c"

    step = runtime.render_now()

    step.assert_operation_class("cursor_update")
    assert step.diagnostics.changed_line_range is None
    assert step.diagnostics.current_logical_lines == ("abc",)
    assert step.diagnostics.operations == (
        TerminalOperation.hide_cursor(),
        TerminalOperation.move_column(column=2),
        TerminalOperation.show_cursor(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[0] == "abc"
    assert step.frame.screen_after.cursor_column == 2


def test_cursor_position_uses_pi_style_relative_row_inside_visible_viewport() -> None:
    root = TextRoot(f"one\ntwo\nthree\nfour\nfi{CURSOR_MARKER}ve")
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=3)))

    step = runtime.render_now()

    assert step.diagnostics.viewport_top == 2
    assert step.diagnostics.operations[-2:] == (
        TerminalOperation.move_column(column=2),
        TerminalOperation.show_cursor(),
    )
    assert step.frame is not None
    assert step.frame.screen_after.cursor_row == 2
    assert step.frame.screen_after.cursor_column == 2


def test_first_render_positions_cursor_relative_to_content_when_terminal_not_home() -> None:
    root = TextRoot(f"one\ntwo\nthr{CURSOR_MARKER}ee\nfour")
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=10))
    port.screen = port.screen.apply((TerminalOperation.move_cursor(row=4, column=0),))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=port)

    step = runtime.render_now()

    assert step.frame is not None
    assert step.frame.screen_after.visible_lines[4:8] == ("one", "two", "three", "four")
    assert step.frame.screen_after.cursor_row == 6
    assert step.frame.screen_after.cursor_column == 3


def test_width_or_height_change_uses_pi_style_resize_repaint_with_clear_scrollback() -> None:
    root = StaticRoot(("one", "two"))
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))
    runtime = TuiRuntime(render_loop=RenderLoop(root), terminal=port)
    runtime.render_now()
    port.resize(TerminalSize(columns=30, rows=6))

    step = runtime.render_now()

    step.assert_operation_class("resize_repaint")
    step.assert_has_clear_scrollback()
    assert step.diagnostics.width_changed is True
    assert step.diagnostics.height_changed is True
    assert step.diagnostics.repaint_kind == "resize"
    assert step.diagnostics.operations[:3] == (
        TerminalOperation.begin_synchronized_update(),
        TerminalOperation.clear_screen(),
        TerminalOperation.clear_scrollback(),
    )


def test_termux_height_only_resize_does_not_force_resize_repaint() -> None:
    root = StaticRoot(("one", "two"))
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))
    runtime = TuiRuntime(render_loop=RenderLoop(root, termux_session=True), terminal=port)
    runtime.render_now()
    port.resize(TerminalSize(columns=20, rows=4))

    step = runtime.render_now()

    step.assert_operation_class("noop")
    step.assert_no_clear_scrollback()
    assert step.diagnostics.width_changed is False
    assert step.diagnostics.height_changed is True


def test_termux_width_resize_still_forces_resize_repaint() -> None:
    root = StaticRoot(("one", "two"))
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))
    runtime = TuiRuntime(render_loop=RenderLoop(root, termux_session=True), terminal=port)
    runtime.render_now()
    port.resize(TerminalSize(columns=21, rows=5))

    step = runtime.render_now()

    step.assert_operation_class("resize_repaint")
    assert step.diagnostics.width_changed is True
    assert step.diagnostics.height_changed is False


def test_disabled_clear_scrollback_policy_can_preserve_scrollback_on_resize_repaint() -> None:
    root = StaticRoot(("one",))
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))
    runtime = TuiRuntime(render_loop=RenderLoop(root, clear_scrollback_policy="disabled"), terminal=port)
    runtime.render_now()
    port.resize(TerminalSize(columns=21, rows=5))

    step = runtime.render_now()

    step.assert_operation_class("resize_repaint")
    step.assert_no_clear_scrollback()
    assert TerminalOperation.clear_scrollback() not in step.diagnostics.operations


def test_unsafe_viewport_forces_recovery_repaint_instead_of_changed_range_update() -> None:
    root = StaticRoot(("one", "two"))
    render_loop = RenderLoop(root)
    runtime = TuiRuntime(render_loop=render_loop, terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)))
    runtime.render_now()
    render_loop.mark_viewport_unsafe("external_stdout")
    root.lines = ("one", "TWO")

    step = runtime.render_now()

    step.assert_operation_class("recovery_repaint")
    step.assert_no_clear_scrollback()
    assert step.diagnostics.repaint_kind == "recovery"
    assert step.diagnostics.repaint_reason == "external_stdout"
    assert step.diagnostics.changed_line_range == (1, 1)


def test_changed_range_above_viewport_rewrites_managed_viewport_without_clearing_screen() -> None:
    root = StaticRoot(tuple(f"line {index}" for index in range(20)))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root, clear_scrollback_policy="disabled"),
        terminal=FakeTerminalPort(size=TerminalSize(columns=20, rows=5)),
    )
    runtime.render_now()
    root.lines = ("LINE 0", *tuple(f"line {index}" for index in range(1, 20)))

    step = runtime.render_now()

    step.assert_operation_class("managed_viewport_repaint")
    step.assert_no_clear_scrollback()
    assert TerminalOperation.clear_screen() not in step.diagnostics.operations
    assert step.diagnostics.repaint_reason == "changed_range_above_viewport"


def test_baseline_reset_repaints_active_screen_without_diffing_against_old_lines() -> None:
    root = StaticRoot(("old transcript", "status"))
    render_loop = RenderLoop(root, clear_scrollback_policy="disabled")
    runtime = TuiRuntime(render_loop=render_loop, terminal=FakeTerminalPort(size=TerminalSize(columns=30, rows=5)))
    runtime.render_now()

    root.lines = ("compacted summary", "recent suffix", "status")
    render_loop.reset_baseline("transcript_window_replaced")
    step = runtime.render_now()

    step.assert_operation_class("baseline_repaint")
    step.assert_no_clear_scrollback()
    assert step.diagnostics.repaint_kind == "recovery"
    assert step.diagnostics.repaint_reason == "transcript_window_replaced"
    assert step.diagnostics.previous_rendered_lines == ("old transcript", "status")
    assert step.diagnostics.current_logical_lines == ("compacted summary", "recent suffix", "status")


def test_failed_runtime_flush_does_not_advance_render_loop_snapshot() -> None:
    root = StaticRoot(("first",))
    port = FakeTerminalPort(size=TerminalSize(columns=20, rows=5))
    render_loop = RenderLoop(root)
    runtime = TuiRuntime(render_loop=render_loop, terminal=port)
    runtime.render_now()
    root.lines = ("second",)
    port.fail_next_flush(RuntimeError("write failed"))

    with pytest.raises(RuntimeError, match="write failed"):
        runtime.render_now()

    root.lines = ("third",)
    step = runtime.render_now()

    assert step.diagnostics.previous_rendered_lines == ("first",)
    assert step.diagnostics.changed_line_range == (0, 0)


def test_process_terminal_port_writes_serialized_frame_to_output() -> None:
    output = StringIO()
    port = ProcessTerminalPort(output=output, size_provider=lambda: TerminalSize(columns=20, rows=5))

    frame = port.flush(
        (
            TerminalOperation.begin_synchronized_update(),
            TerminalOperation.write("hello"),
            TerminalOperation.end_synchronized_update(),
        )
    )

    assert output.getvalue() == "\x1b[?2026hhello\x1b[?2026l"
    assert frame.serialized_output == output.getvalue()
    assert frame.screen_after.visible_lines[0] == "hello"
    assert port.frames == (frame,)

    second = port.flush((TerminalOperation.write("!"),))

    assert port.frames == (second,)


def test_process_terminal_port_can_skip_screen_tracking_for_live_output() -> None:
    output = StringIO()
    port = ProcessTerminalPort(
        output=output,
        size_provider=lambda: TerminalSize(columns=20, rows=5),
        track_screen=False,
    )

    frame = port.flush((TerminalOperation.write("hello"), TerminalOperation.newline(), TerminalOperation.write("world")))

    assert output.getvalue() == "hello\r\nworld"
    assert frame.serialized_output == output.getvalue()
    assert frame.screen_before is frame.screen_after
    assert port.screen.visible_lines == ("", "", "", "", "")
    assert port.frames == (frame,)


def test_process_terminal_port_can_write_serialized_output_to_log(tmp_path: Path) -> None:
    output = StringIO()
    log_path = tmp_path / "tui.log"
    port = ProcessTerminalPort(
        output=output,
        size_provider=lambda: TerminalSize(columns=20, rows=5),
        write_log_path=log_path,
    )

    port.flush((TerminalOperation.write("hello"),))
    port.flush((TerminalOperation.newline(), TerminalOperation.write("world")))

    assert log_path.read_bytes() == b"hello\r\nworld"


def test_terminal_progress_reporter_sends_keepalive_frames() -> None:
    now = 0

    def now_ms() -> int:
        return now

    port = FakeTerminalPort(frame_history_limit=None)
    reporter = TerminalProgressReporter(port, now_ms=now_ms)

    assert reporter.set_active(True) is True
    assert reporter.keepalive() is False

    now = 1_000

    assert reporter.keepalive() is True
    assert reporter.stop() is True
    assert port.flushes == (
        (TerminalOperation.set_progress(True),),
        (TerminalOperation.set_progress(True),),
        (TerminalOperation.set_progress(False),),
    )


def test_process_terminal_port_uses_environment_size_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv("COLUMNS", "132")
    monkeypatch.setenv("LINES", "43")

    def unavailable_size() -> TerminalSize:
        raise OSError("not a tty")

    port = ProcessTerminalPort(output=output, size_provider=unavailable_size)

    assert port.size() == TerminalSize(columns=132, rows=43)
    assert port.screen.size == TerminalSize(columns=132, rows=43)


def test_process_terminal_port_defaults_size_when_provider_and_environment_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = StringIO()
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("LINES", raising=False)

    def unavailable_size() -> TerminalSize:
        raise OSError("not a tty")

    port = ProcessTerminalPort(output=output, size_provider=unavailable_size)

    assert port.size() == TerminalSize(columns=80, rows=24)

from __future__ import annotations

from io import StringIO

from loushang.coding.ui.native_app import NativeCodingTuiApp
from loushang.coding.ui.native_input import NativeInputRouter
from loushang.coding.ui.native_loop import _finish_tui_exit
from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import NativeTuiScenario
from loushang.tui import (
    CompletionItem,
    CompletionProvider,
    FakeTerminalPort,
    InputEvent,
    RenderLoop,
    TerminalOperation,
    TerminalRuntimeCapabilities,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)
from loushang.tui.theme import ThemeResolver


def test_native_coding_tui_streaming_uses_differential_updates_without_clearing_screen() -> None:
    app = _app()
    runtime, _port = _runtime(app, height=18)

    app.start_prompt("long answer", started_at=0.0)
    first = runtime.render_now()

    app.begin_assistant()
    streaming_steps = []
    for index in range(14):
        app.append_assistant_chunk(f"line {index}\n")
        streaming_steps.append(runtime.render_now())

    assert first.diagnostics.operation_class == "first_render"
    assert all(step.diagnostics.operation_class != "recovery_repaint" for step in streaming_steps)
    assert all(TerminalOperation.clear_screen() not in step.diagnostics.operations for step in streaming_steps)
    assert all(TerminalOperation.clear_scrollback() not in step.diagnostics.operations for step in streaming_steps)


def test_native_coding_tui_overlay_host_preserves_composer_cursor() -> None:
    app = _app()
    runtime, port = _runtime(app, height=10)
    app.surface_host = runtime.overlay_host()

    first = runtime.render_now()

    assert first.diagnostics.logical_cursor_row == 1
    assert first.diagnostics.logical_cursor_column == 2
    assert first.frame is not None
    assert first.frame.screen_after.cursor_row == 1
    assert first.frame.screen_after.cursor_column == 2


def test_native_coding_tui_exit_cleanup_clears_bottom_frame_status() -> None:
    app = _app()
    runtime, port = _runtime(app, width=80, height=12)

    app.start_prompt("hello", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("done")
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    runtime.render_now()

    before = tuple(strip_control_sequences(line).rstrip() for line in port.screen.visible_lines)
    assert "kimi | repo | main | abcd | idle" in before

    exit_code = _finish_tui_exit(runtime=runtime, stdout=StringIO(), exit_code=0)

    after = tuple(strip_control_sequences(line).rstrip() for line in port.screen.visible_lines)
    assert exit_code == 0
    assert any("Worked for 1.00s" in line for line in after)
    assert "kimi | repo | main | abcd | idle" not in after
    assert "›" not in after
    assert port.screen.cursor_column == 0


def test_native_coding_tui_transcript_uses_runtime_hyperlink_capability() -> None:
    app = _app()
    app.transcript_theme = ThemeResolver(
        defaults={
            "markdown.link": {"hyperlink": True, "color": "blue"},
            "markdown.linkUrl": {"color": "bright_black"},
        }
    )
    app.terminal_capabilities = TerminalRuntimeCapabilities(hyperlinks=False, truecolor=True)
    runtime, _port = _runtime(app, width=100, height=12)

    app.start_prompt("show docs", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("See [docs](https://example.com).")
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    step = runtime.render_now()

    output = "\n".join(step.diagnostics.current_logical_lines)
    plain = strip_control_sequences(output)
    assert "\x1b]8;;https://example.com" not in output
    assert "docs (https://example.com)" in plain


def test_native_coding_tui_long_stream_keeps_pi_style_diff_without_recovery_repaints() -> None:
    app = _app()
    runtime, _port = _runtime(app, width=100, height=18)

    app.start_prompt("long answer", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    streaming_steps = []
    for index in range(120):
        app.append_assistant_chunk(f"- line {index}\n")
        if index % 10 == 0:
            streaming_steps.append(runtime.render_now())

    assert streaming_steps
    assert all(step.diagnostics.operation_class != "recovery_repaint" for step in streaming_steps)
    assert all(step.diagnostics.operation_class != "baseline_repaint" for step in streaming_steps)


def test_native_coding_tui_long_stream_uses_protected_bottom_frame_append() -> None:
    app = _app()
    runtime, port = _runtime(app, width=100, height=18)

    app.start_prompt("long answer", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    protected_steps = []
    for index in range(80):
        app.append_assistant_chunk(f"- line {index}\n")
        if index % 10 == 0:
            step = runtime.render_now()
            if step.diagnostics.operation_class == "protected_append_update":
                protected_steps.append(step)

    assert protected_steps
    assert all("Working" in _visible_text(port) for _step in protected_steps)
    assert all(TerminalOperation.set_scroll_region(top=0, bottom=11) in step.diagnostics.operations for step in protected_steps[-1:])
    assert all(TerminalOperation.clear_screen() not in step.diagnostics.operations for step in protected_steps)


def test_native_coding_tui_completion_close_keeps_footer_height_and_cursor_anchor() -> None:
    app = _app()
    app.composer.set_completion_provider(
        CompletionProvider(
            (
                CompletionItem(value="/help", label="/help", description="Show help"),
                CompletionItem(value="/quit", label="/quit", description="Quit"),
            )
        )
    )
    app.start_prompt("previous", started_at=0.0)
    app.begin_assistant()
    app.append_assistant_chunk("done")
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    router = NativeInputRouter(app, should_exit=lambda text: text == "/quit", is_local_command=lambda text: text.startswith("/"))
    runtime, port = _runtime(app, width=80, height=18)

    runtime.render_now()
    router.handle(InputEvent(kind="text", text="/"))
    expanded = runtime.render_now()
    router.handle(InputEvent(kind="key", key="backspace"))
    collapsed = runtime.render_now()
    router.handle(InputEvent(kind="key", key="up"))
    recalled = runtime.render_now()

    visible = tuple(strip_control_sequences(line).rstrip() for line in port.screen.visible_lines)

    assert len(collapsed.diagnostics.current_logical_lines) == len(expanded.diagnostics.current_logical_lines)
    assert collapsed.frame is not None
    assert collapsed.frame.screen_after.cursor_row == collapsed.diagnostics.hardware_cursor_row
    assert recalled.frame is not None
    assert recalled.frame.screen_after.cursor_row == recalled.diagnostics.hardware_cursor_row
    assert visible.count("kimi | repo | main | abcd | idle") == 1


def test_native_coding_tui_active_window_trim_rewrites_viewport_without_clearing_screen() -> None:
    app = NativeCodingTuiApp(
        model_label="kimi",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        now=lambda: 3.0,
        active_transcript_line_budget=30,
    )
    runtime, _port = _runtime(app, width=100, height=18)

    for turn in range(3):
        app.start_prompt(f"turn {turn}", started_at=0.0)
        runtime.render_now()
        app.begin_assistant()
        app.append_assistant_chunk("\n".join(f"turn {turn} line {index}" for index in range(20)))
        runtime.render_now()
        app.end_assistant()
        app.complete_run(elapsed_seconds=1.0)
    app.trim_active_transcript_window()
    step = runtime.render_now()

    assert step.diagnostics.operation_class == "managed_viewport_repaint"
    assert TerminalOperation.clear_screen() not in step.diagnostics.operations
    assert TerminalOperation.clear_scrollback() not in step.diagnostics.operations


def test_native_coding_tui_complete_run_does_not_repaint_for_active_window_trim() -> None:
    app = NativeCodingTuiApp(
        model_label="kimi",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        now=lambda: 3.0,
        active_transcript_line_budget=30,
    )
    runtime, _port = _runtime(app, width=100, height=18)

    app.start_prompt("long answer", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("\n".join(f"line {index}" for index in range(120)))
    runtime.render_now()
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    step = runtime.render_now()

    assert step.diagnostics.operation_class != "managed_viewport_repaint"
    assert step.diagnostics.repaint_reason != "transcript_window_trimmed:active_line_budget"
    assert app.state.evicted_prefix_record_count == 0


def test_native_coding_tui_markdown_assistant_commit_does_not_rewrite_streamed_body() -> None:
    app = _app()
    runtime, _port = _runtime(app, width=100, height=18)

    app.start_prompt("markdown stream", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    for index in range(40):
        app.append_assistant_chunk(f"- **Line {index}**: markdown `code-{index}` with [link {index}](https://example.com/{index}).\n")
    runtime.render_now()
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    step = runtime.render_now()

    assert step.diagnostics.operation_class != "managed_viewport_repaint"
    assert step.diagnostics.changed_line_range is not None
    assert step.diagnostics.changed_line_range[0] > 35


def test_native_coding_tui_completion_replaces_working_with_one_worked_divider() -> None:
    app = _app()
    runtime, port = _runtime(app)

    app.start_prompt("hello", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("hello back")
    runtime.render_now()
    app.end_assistant()
    app.complete_run(elapsed_seconds=2.32)
    step = runtime.render_now()

    visible = _visible_text(port)
    worked_index = visible.rfind("Worked for 2.32s")
    assert worked_index != -1
    assert visible.count("Worked for 2.32s") == 1
    assert "Working" not in visible[worked_index:]
    assert sum("Worked for 2.32s" in line for line in step.diagnostics.current_logical_lines) == 1


def test_native_coding_tui_keeps_unsubmitted_draft_in_live_composer_only() -> None:
    app = _app()
    runtime, port = _runtime(app)

    app.start_prompt("first prompt", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("response")
    runtime.render_now()
    app.composer.set_text("你")
    runtime.render_now()
    app.end_assistant()
    app.complete_run(elapsed_seconds=1.0)
    runtime.render_now()
    app.composer.set_text("你好")
    runtime.render_now()

    visible_lines = tuple(line.rstrip() for line in port.screen.visible_lines)
    assert "› first prompt" in visible_lines
    assert "› 你好" in visible_lines
    assert "› 你" not in visible_lines


def test_native_coding_tui_resize_repaints_without_replaying_working_or_composer_duplicates() -> None:
    app = _app()
    runtime, port = _runtime(app, width=60, height=16)

    app.start_prompt("resize me", started_at=0.0)
    runtime.render_now()
    app.begin_assistant()
    app.append_assistant_chunk("one two three four five six seven eight nine ten")
    runtime.render_now()
    port.resize(TerminalSize(columns=44, rows=12))
    resize_step = runtime.render_now()

    visible = _visible_text(port)
    assert resize_step.diagnostics.operation_class == "resize_repaint"
    assert visible.count("› resize me") == 1
    assert visible.count("Working") == 1


def test_native_coding_tui_starts_below_existing_shell_output() -> None:
    app = _app()
    runtime, port = _runtime(app, height=10)
    port.screen = port.screen.apply(
        (
            TerminalOperation.move_cursor(row=4, column=0),
            TerminalOperation.write("shell command output"),
            TerminalOperation.newline(),
        )
    )

    step = runtime.render_now()

    assert step.diagnostics.operation_class == "first_render"
    assert port.screen.visible_lines[4] == "shell command output"
    assert "›" in port.screen.visible_lines[6]
    assert "kimi | repo | main | abcd | idle" in port.screen.visible_lines[8]


def test_native_coding_tui_renders_pending_steer_and_followup_below_working_line() -> None:
    scenario = NativeTuiScenario(width=140, height=16, now=3.0)
    app = scenario.app

    app.start_prompt("current task", started_at=0.0)
    app.queue_steer("steer now")
    app.queue_followup("next prompt")
    scenario.render()

    visible_lines = tuple(line.rstrip() for line in scenario.port.screen.visible_lines)
    working_index = next(index for index, line in enumerate(visible_lines) if "Working" in line)
    steer_index = visible_lines.index("• Messages to be submitted after next tool call (press esc to interrupt and send immediately)")
    followup_index = visible_lines.index("• Queued follow-up inputs")
    composer_index = visible_lines.index("›")

    assert working_index < steer_index < followup_index < composer_index
    assert "  ↳ steer now" in visible_lines
    assert "  ↳ next prompt" in visible_lines
    assert "    alt + ↑ edit last queued message" in visible_lines


def test_native_coding_tui_resumed_long_transcript_input_echo_uses_bounded_fake_terminal_update() -> None:
    scenario = NativeTuiScenario(width=100, height=30, now=3.0)
    app = scenario.app
    app.replace_transcript_window(
        build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400),
        reason="resume",
    )
    app.trim_active_transcript_window()

    first = scenario.render()
    step = scenario.type_text("x").render()

    assert len(first.diagnostics.current_logical_lines) <= 380
    assert len(step.diagnostics.current_logical_lines) <= 380
    scenario.assert_operation_class(step, "changed_range_update")
    scenario.assert_no_clear(step)
    scenario.assert_visible_contains("› x")


def test_native_coding_tui_resumed_long_transcript_working_timer_uses_bounded_fake_terminal_update() -> None:
    scenario = NativeTuiScenario(width=100, height=30, now=0.0)
    app = scenario.app
    app.replace_transcript_window(
        build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400),
        reason="resume",
    )
    app.trim_active_transcript_window()
    app.begin_run(started_at=0.0)

    first = scenario.render()
    step = scenario.advance_time(0.2).render()

    assert len(first.diagnostics.current_logical_lines) <= 380
    assert len(step.diagnostics.current_logical_lines) <= 380
    scenario.assert_operation_class(step, "changed_range_update")
    scenario.assert_no_clear(step)
    scenario.assert_visible_contains("Working 0.20s")


def test_native_coding_tui_resumed_long_transcript_input_and_timer_share_bounded_update_path() -> None:
    scenario = NativeTuiScenario(width=100, height=30, now=0.0)
    app = scenario.app
    app.replace_transcript_window(
        build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400),
        reason="resume",
    )
    app.trim_active_transcript_window()
    app.begin_run(started_at=0.0)

    startup = scenario.render()
    assert len(startup.diagnostics.current_logical_lines) <= 380

    timer_first = scenario.advance_time(0.2).render()
    timer_second = scenario.advance_time(0.2).render()
    input_step = scenario.type_text("x").render()
    timer_third = scenario.advance_time(0.2).render()

    for step in (timer_first, timer_second, input_step, timer_third):
        assert len(step.diagnostics.current_logical_lines) <= 380
        scenario.assert_operation_class(step, "changed_range_update")
        scenario.assert_no_clear(step)

    assert all("Working" in scenario.visible_text() for _ in (1, 3))
    scenario.assert_visible_contains("› x")


def _app() -> NativeCodingTuiApp:
    return NativeCodingTuiApp(
        model_label="kimi",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        now=lambda: 3.0,
    )


def _runtime(
    app: NativeCodingTuiApp, *, width: int = 80, height: int = 24
) -> tuple[TuiRuntime, FakeTerminalPort]:
    port = FakeTerminalPort(size=TerminalSize(columns=width, rows=height))
    runtime = TuiRuntime(render_loop=RenderLoop(app), terminal=port)
    return runtime, port


def _visible_text(port: FakeTerminalPort) -> str:
    return strip_control_sequences("\n".join(port.screen.visible_lines))

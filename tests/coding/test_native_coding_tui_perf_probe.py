from __future__ import annotations

from loushang.coding.ui.native_app import NativeCodingTuiApp
from loushang.coding.ui.perf_probe import (
    build_synthetic_long_transcript_records,
    characterize_long_transcript_rendering,
)
from loushang.tui import RenderLoop


def test_long_transcript_probe_shows_render_loop_plans_beyond_visible_height() -> None:
    records = build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400)
    app = NativeCodingTuiApp(
        model_label="fake-model",
        cwd="/repo",
        branch="main",
        session_label="perf",
    )
    app.replace_transcript_window(records, reason="test")
    render_loop = RenderLoop(screen_root=app)

    first_metrics = characterize_long_transcript_rendering(
        app,
        width=100,
        height=30,
        render_loop=render_loop,
        commit_plan=True,
    )
    second_metrics = characterize_long_transcript_rendering(
        app,
        width=100,
        height=30,
        composer_text="hello",
        render_loop=render_loop,
        commit_plan=True,
    )

    assert first_metrics.visible_render_line_count <= 30
    assert first_metrics.render_loop_logical_line_count > 30
    assert first_metrics.render_loop_logical_line_count > first_metrics.visible_render_line_count
    assert second_metrics.render_loop_logical_line_count == first_metrics.render_loop_logical_line_count
    assert second_metrics.render_loop_operation_class != "first_render"

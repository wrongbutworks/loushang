from __future__ import annotations

import pytest

from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.harnesstui.testing.performance import (
    build_synthetic_long_transcript_records,
    characterize_long_transcript_rendering,
)
from loushang.tui import RenderLoop


@pytest.mark.tui_render_contract
def test_long_transcript_probe_shows_render_loop_plans_beyond_visible_height() -> None:
    records = build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400)
    app = ScreenCodingTuiApp(
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


def test_long_transcript_probe_stays_bounded_after_active_window_trim() -> None:
    records = build_synthetic_long_transcript_records(turns=180, tail_tool_output_lines=2400)
    app = ScreenCodingTuiApp(
        model_label="fake-model",
        cwd="/repo",
        branch="main",
        session_label="perf",
    )
    app.replace_transcript_window(records, reason="test")
    app.trim_active_transcript_window()
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

    assert app.state.evicted_prefix_record_count > 0
    assert first_metrics.render_loop_plan_ms < 1_000
    assert first_metrics.visible_render_ms < 1_000
    assert second_metrics.render_loop_plan_ms < 1_000
    assert second_metrics.visible_render_ms < 1_000
    assert first_metrics.render_loop_logical_line_count <= app.active_transcript_line_budget + 60
    assert second_metrics.render_loop_logical_line_count <= app.active_transcript_line_budget + 60
    assert second_metrics.render_loop_logical_line_count == first_metrics.render_loop_logical_line_count
    assert second_metrics.render_loop_operation_class == "changed_range_update"
    assert second_metrics.changed_line_range is not None

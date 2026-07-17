from __future__ import annotations

from loushang.coding.ui import status_line as coding_status_line
from loushang.harnesstui.status import line as shared_status_line
from loushang.harnesstui.status.line import (
    StatusLinePreviewSnapshot,
    StatusLineSettings,
    status_line_fields,
    status_line_separator,
    status_line_style_mode,
)
from loushang.tui import RenderConstraints, StatusBar


def test_coding_status_line_compatibility_aliases_are_identical() -> None:
    assert coding_status_line.__all__ == shared_status_line.__all__
    for name in shared_status_line.__all__:
        assert getattr(coding_status_line, name) is getattr(shared_status_line, name)


def test_screen_app_statusline_preview_snapshot_includes_live_queue_and_message_state() -> None:
    from loushang.coding.ui.screen_app import ScreenCodingTuiApp

    app = ScreenCodingTuiApp(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label="abcd",
    )
    app.queue_followup("next prompt")
    app.queue_steer("interrupt")
    app.set_status("Saved")

    assert app.statusline_preview_snapshot() == StatusLinePreviewSnapshot(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        running=False,
        pending_followups=1,
        pending_steers=1,
        status_message="Saved",
    )


def test_screen_app_real_status_bar_uses_shared_status_line_builder() -> None:
    from loushang.coding.ui.screen_app import ScreenCodingTuiApp

    app = ScreenCodingTuiApp(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label="abcd",
    )
    settings = StatusLineSettings(queue="true", message="true", separator="dot", style="plain")
    app.set_statusline_settings(settings)

    expected = StatusBar(
        status_line_fields(app.statusline_preview_snapshot(), settings),
        separator=status_line_separator(settings),
        style_mode=status_line_style_mode(settings),
    ).render(RenderConstraints(width=100, max_height=1))
    actual = app._status_bar().render(RenderConstraints(width=100, max_height=1))

    assert actual.lines[0].text == expected.lines[0].text
    assert actual.lines[0].text == "moonshot/kimi-for-coding · repo · main · abcd · idle · queued=0 steer=0 · no status"

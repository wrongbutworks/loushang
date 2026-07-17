from __future__ import annotations

from loushang.harnesstui.status import settings as shared_settings
from loushang.harnesstui.status.line import (
    StatusLinePreviewSnapshot,
    StatusLineSettings,
)
from loushang.tui import RenderConstraints


def test_statusline_rows_are_product_neutral_view_data() -> None:
    rows = shared_settings.statusline_rows(
        StatusLineSettings(enabled=False, queue="true", separator="dot", style="plain")
    )

    assert [(row.id, row.value) for row in rows] == [
        ("statusline.enabled", "false"),
        ("statusline.field.model", "true"),
        ("statusline.field.workspace", "true"),
        ("statusline.field.branch", "true"),
        ("statusline.field.session", "true"),
        ("statusline.field.runtime", "true"),
        ("statusline.field.queue", "true"),
        ("statusline.field.message", "auto"),
        ("statusline.separator", "dot"),
        ("statusline.style", "plain"),
    ]


def test_next_statusline_value_preserves_existing_cycles() -> None:
    assert shared_settings.next_statusline_value("statusline.enabled", "true") == "false"
    assert shared_settings.next_statusline_value("statusline.field.queue", "auto") == "true"
    assert shared_settings.next_statusline_value("statusline.field.queue", "true") == "false"
    assert shared_settings.next_statusline_value("statusline.field.queue", "false") == "auto"
    assert shared_settings.next_statusline_value("statusline.separator", "pipe") == "dot"
    assert shared_settings.next_statusline_value("statusline.style", "plain") == "codex-like"


def test_statusline_page_keeps_preview_layout() -> None:
    page = shared_settings.StatusLineSettingsPage(
        statusline_settings=StatusLineSettings(),
        statusline_preview=lambda: StatusLinePreviewSnapshot(
            model_label="model",
            cwd="/workspace/repo",
            branch="main",
            session_label="session",
            running=False,
        ),
    )

    result = page.render(RenderConstraints(width=80, max_height=20))

    assert "Preview" in [line.text for line in result.lines]
    assert any("model" in line.text and "repo" in line.text for line in result.lines)

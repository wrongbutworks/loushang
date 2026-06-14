from __future__ import annotations

from loushang.tui import RenderConstraints, StatusBar, StatusField, visible_width
from loushang.tui.theme import ThemeResolver


def rendered_text(status: StatusBar, *, width: int = 40) -> str:
    result = status.render(RenderConstraints(width=width, max_height=1))
    return result.lines[0].text


def test_status_bar_default_output_is_unchanged() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("running", priority=80),
        ]
    )

    assert rendered_text(status, width=30) == "model | running"


def test_status_bar_accepts_optional_field_token() -> None:
    field = StatusField("model", priority=100, token="model")

    assert field.text == "model"
    assert field.priority == 100
    assert field.token == "model"


def test_status_bar_custom_separator_changes_joined_text() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("running", priority=80),
        ],
        separator=" · ",
    )

    assert rendered_text(status, width=30) == "model · running"


def test_status_bar_priority_fitting_uses_custom_separator() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("very-long-branch-name", priority=10),
            StatusField("running", priority=80),
        ],
        separator=" · ",
    )

    line = rendered_text(status, width=16)

    assert line == "model · running"
    assert visible_width(line) == 15


def test_status_bar_plain_mode_ignores_theme_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "statusBar.model": {"foreground": "red"},
            "statusBar.field": {"foreground": "green"},
            "statusBar.separator": {"foreground": "yellow"},
        }
    )
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("running", priority=80, token="runtime.running"),
        ],
        theme=theme,
        style_mode="plain",
    )

    assert rendered_text(status, width=30) == "model | running"

from __future__ import annotations

from loushang.tui import RenderConstraints, StatusBar, StatusField, visible_width
from loushang.tui import StatusBar as PublicStatusBar
from loushang.tui import StatusField as PublicStatusField
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.status import StatusBar as ModuleStatusBar
from loushang.tui.ui_parts.status import StatusField as ModuleStatusField


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


def test_status_bar_codex_like_mode_applies_builtin_field_styles_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("idle", priority=80, token="runtime.idle"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[36mmodel\x1b[39m" in line
    assert "\x1b[2midle\x1b[22m" in line


def test_status_bar_codex_like_mode_styles_separator_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("branch", priority=80, token="branch"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[2m | \x1b[22m" in line


def test_status_bar_muted_mode_applies_builtin_styles_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("branch", priority=80, token="branch"),
        ],
        style_mode="muted",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[2mmodel\x1b[22m" in line
    assert "\x1b[2m | \x1b[22m" in line


def test_status_bar_theme_override_beats_builtin_style() -> None:
    theme = ThemeResolver(defaults={"statusBar.codexLike.model": {"foreground": "red"}})
    status = StatusBar(
        [StatusField("model", priority=100, token="model")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[31mmodel\x1b[39m"


def test_status_bar_width_fitting_ignores_ansi_sequences() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("very-long-branch-name", priority=10, token="branch"),
            StatusField("running", priority=80, token="runtime.running"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=16)

    assert "very-long-branch-name" not in line
    assert visible_width(line) == 15
    assert "model" in line
    assert "running" in line


def test_status_bar_unknown_token_falls_back_to_generic_field_style() -> None:
    theme = ThemeResolver(defaults={"statusBar.field": {"foreground": "blue"}})
    status = StatusBar(
        [StatusField("custom", priority=100, token="unknown")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[34mcustom\x1b[39m"


def test_status_bar_fully_qualified_token_behaves_like_semantic_token() -> None:
    status = StatusBar(
        [StatusField("model", priority=100, token="statusBar.model")],
        style_mode="codex-like",
    )

    assert rendered_text(status, width=20) == "\x1b[36mmodel\x1b[39m"


def test_status_bar_mode_qualified_token_resolves_exact_token_first() -> None:
    theme = ThemeResolver(defaults={"statusBar.codexLike.model": {"foreground": "red"}})
    status = StatusBar(
        [StatusField("model", priority=100, token="statusBar.codexLike.model")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[31mmodel\x1b[39m"


def test_status_bar_public_exports_are_updated_classes() -> None:
    assert PublicStatusBar is ModuleStatusBar
    assert PublicStatusField is ModuleStatusField
    assert PublicStatusField("x", token="model").token == "model"

from __future__ import annotations

import runpy
from typing import Any

from loushang.tui import (
    Badge,
    InputEvent,
    KeyValueItem,
    KeyValueList,
    ProgressBar,
    RenderConstraints,
    StatusPill,
    ThemeResolver,
    Toolbar,
    ToolbarAction,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Badge as UiBadge
from loushang.tui.ui_parts.widgets import Badge as WidgetBadge
from tests.tui.widget_example_playback import ExampleFrame, play_example


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_small_controls_are_reexported_from_public_modules() -> None:
    assert Badge is UiBadge
    assert Badge is WidgetBadge
    assert KeyValueItem("model", "kimi").key == "model"


def test_badge_and_status_pill_render_plain_and_themed_text() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.badge.info": {"color": "cyan"},
            "widget.status.success": {"color": "green", "bold": True},
        }
    )

    badge = Badge("beta", kind="info", theme=theme)
    status = StatusPill("ready", status="success", theme=theme)

    badge_raw = render_lines(badge, width=20)
    status_raw = render_lines(status, width=20)

    assert badge_raw[0].startswith("\x1b[36m")
    assert status_raw[0].startswith("\x1b[1;32m")
    assert strip_control_sequences(badge_raw[0]) == "[beta]"
    assert strip_control_sequences(status_raw[0]) == "(ready)"
    assert plain_lines(Badge("beta")) == ("[beta]",)
    assert plain_lines(StatusPill("ready")) == ("(ready)",)


def test_display_controls_respect_narrow_and_short_constraints() -> None:
    controls = [
        Badge("very-long-badge"),
        StatusPill("very-long-status"),
        ProgressBar(value=4, total=10, label="Very long progress", width=10),
        KeyValueList([("Very long key", "Very long value")]),
    ]

    for control in controls:
        lines = render_lines(control, width=4, height=1)
        assert len(lines) <= 1
        assert_widths_within(lines, 4)


def test_progress_bar_renders_ratio_clamping_percent_and_theme_segments() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.progress.fill": {"color": "green"},
            "widget.progress.track": {"color": "bright_black"},
            "widget.progress.label": {"bold": True},
        }
    )

    progress = ProgressBar(value=4, total=10, label="Indexing", width=10, theme=theme)

    raw = render_lines(progress, width=40)[0]

    assert strip_control_sequences(raw) == "Indexing [####------] 40%"
    assert "\x1b[32m####\x1b[39m" in raw
    assert "\x1b[90m------\x1b[39m" in raw

    assert plain_lines(ProgressBar(value=120, total=100, width=5), width=20) == ("[#####] 100%",)
    assert plain_lines(ProgressBar(value=-1, total=100, width=5), width=20) == ("[-----] 0%",)
    assert plain_lines(ProgressBar(value=1, total=0, width=5), width=20) == ("[-----] 0%",)


def test_progress_bar_can_hide_percent_and_still_fit() -> None:
    progress = ProgressBar(value=1, total=4, label="Build", width=8, show_percent=False)

    assert plain_lines(progress, width=20) == ("Build [##------]",)
    assert_widths_within(render_lines(progress, width=6), 6)


def test_key_value_list_renders_tuples_items_descriptions_and_themes() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.keyValue.key": {"color": "cyan"},
            "widget.keyValue.value": {"color": "white"},
        }
    )
    details = KeyValueList(
        [
            ("Model", "Kimi"),
            KeyValueItem("Mode", "safe", description="current"),
        ],
        theme=theme,
    )

    raw = render_lines(details, width=40, height=4)

    assert raw[0].startswith("\x1b[36mModel")
    assert tuple(strip_control_sequences(line) for line in raw) == (
        "Model: Kimi",
        "Mode : safe  current",
    )


def test_key_value_list_honors_key_width_height_and_truncation() -> None:
    details = KeyValueList(
        [
            ("LongKey", "LongValue"),
            ("Other", "Second"),
        ],
        key_width=3,
    )

    lines = plain_lines(details, width=10, height=1)

    assert lines == ("Lon: Long",)


def test_toolbar_focus_navigation_and_activation_callback_results() -> None:
    calls: list[str] = []
    toolbar = Toolbar(
        [
            ToolbarAction("Save", on_press=lambda: calls.append("save")),
            ToolbarAction("Delete", disabled=True, value="delete"),
            ToolbarAction("Cancel", value="cancel"),
            ToolbarAction("Preview", on_press=lambda: "preview"),
        ]
    )

    toolbar.focus()

    assert plain_lines(toolbar, width=60) == ("> [Save]  [Delete]  [Cancel]  [Preview]",)
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "cancel"
    assert plain_lines(toolbar, width=60) == ("[Save]  [Delete]  > [Cancel]  [Preview]",)
    assert toolbar.handle_input(InputEvent(kind="key", key="enter")) == "cancel"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "Preview"
    assert toolbar.handle_input(InputEvent(kind="key", key="enter")) == "preview"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "Save"
    assert toolbar.handle_input(InputEvent(kind="text", text=" ")) is True
    assert toolbar.handle_input(InputEvent(kind="key", key="space")) is True
    toolbar.blur()
    assert plain_lines(toolbar, width=60) == ("[Save]  [Delete]  [Cancel]  [Preview]",)
    assert calls == ["save", "save"]


def test_toolbar_wrap_false_boundaries_empty_and_all_disabled_semantics() -> None:
    toolbar = Toolbar([ToolbarAction("One"), ToolbarAction("Two")], wrap=False)
    toolbar.focus()

    assert toolbar.handle_input(InputEvent(kind="key", key="left")) is False
    assert toolbar.handle_input(InputEvent(kind="key", key="end")) is True
    assert toolbar.active_value == "Two"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is False
    assert toolbar.handle_input(InputEvent(kind="key", key="end")) is False

    assert Toolbar([]).render(RenderConstraints(width=20, max_height=1)).lines == ()
    assert Toolbar([]).handle_input(InputEvent(kind="key", key="right")) is None
    disabled = Toolbar([ToolbarAction("No", disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="right")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None


def test_toolbar_applies_theme_tokens_and_respects_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.toolbar.action": {"color": "white"},
            "widget.toolbar.focus": {"bold": True, "color": "cyan"},
            "widget.toolbar.disabled": {"dim": True},
        }
    )
    toolbar = Toolbar(
        [ToolbarAction("Save"), ToolbarAction("Delete", disabled=True)],
        theme=theme,
    )
    toolbar.focus()

    raw = render_lines(toolbar, width=40)[0]

    assert raw.startswith("\x1b[1;36m> [Save]")
    assert "\x1b[2m[Delete]" in raw
    assert strip_control_sequences(raw) == "> [Save]  [Delete]"
    assert_widths_within(render_lines(toolbar, width=5), 5)


def test_widgets_small_controls_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/44_widgets_small_controls.py", run_name="__test__")

    build_app = namespace["build_app"]
    assert callable(build_app)
    app = build_app()
    result = app.render(RenderConstraints(width=80, max_height=20))
    assert result.lines


def test_widgets_small_controls_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/44_widgets_small_controls.py",
        events=(
            ("right", InputEvent(kind="key", key="right")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert [frame.label for frame in frames] == ["initial", "right", "enter"]
    assert all(isinstance(frame, ExampleFrame) for frame in frames)
    assert frames[0].lines[:11] == (
        "Indexing Job  [beta]  (ready)",
        "",
        "Progress      Indexing [#####-------] 42%",
        "",
        "Details",
        "Model         Kimi",
        "Mode          safe  current",
        "Queue         3 pending",
        "",
        "Actions       > [Refresh]  [Cancel]",
        "Status        Ready",
    )
    assert "Actions       [Refresh]  > [Cancel]" in frames[1].lines
    assert "Status        Cancelled" in frames[2].lines

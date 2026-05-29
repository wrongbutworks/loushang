from __future__ import annotations

from typing import Any

from loushang.tui import (
    Box,
    Container,
    FakeTerminalPort,
    Loader,
    RenderConstraints,
    RenderLoop,
    Rule,
    ScreenRoot,
    TerminalCapabilities,
    TerminalSize,
    Text,
    ThemeResolver,
    TruncatedText,
    TuiRuntime,
    strip_control_sequences,
    visible_width,
)


def rendered_text(part: Any, *, width: int = 20, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_theme_style_helper_applies_resolved_ansi_without_changing_visible_width() -> None:
    from loushang.tui import apply_theme_style

    styled = apply_theme_style("hello", {"color": "red", "background": "blue", "bold": True})

    assert styled == "\x1b[1;31;44mhello\x1b[22;39;49m"
    assert strip_control_sequences(styled) == "hello"
    assert visible_width(styled) == 5


def test_theme_style_helper_uses_specific_resets_for_foreground_background_and_attrs() -> None:
    from loushang.tui import apply_theme_style

    assert apply_theme_style("fg", {"color": "red"}) == "\x1b[31mfg\x1b[39m"
    assert apply_theme_style("bg", {"background": "blue"}) == "\x1b[44mbg\x1b[49m"
    assert apply_theme_style("strong", {"bold": True, "underline": True}) == "\x1b[1;4mstrong\x1b[22;24m"


def test_theme_style_helper_supports_pi_style_256_color_values() -> None:
    from loushang.tui import apply_theme_style

    styled = apply_theme_style("indexed", {"color": 196, "background": 27})

    assert styled == "\x1b[38;5;196;48;5;27mindexed\x1b[39;49m"
    assert strip_control_sequences(styled) == "indexed"


def test_theme_resolver_degrades_truecolor_hex_to_256_color_like_pi() -> None:
    theme = ThemeResolver(defaults={"accent": {"color": "#ff0000", "background": "#0000ff"}})

    resolved = theme.resolve("accent", TerminalCapabilities(truecolor=False))

    assert resolved["color"] == 196
    assert resolved["background"] == 21


def test_theme_style_helper_reapplies_outer_style_after_inner_full_reset() -> None:
    from loushang.tui import apply_theme_style

    styled = apply_theme_style("before \x1b[31mred\x1b[0m after", {"background": "blue"})

    assert styled == "\x1b[44mbefore \x1b[31mred\x1b[0m\x1b[44m after\x1b[49m"
    assert strip_control_sequences(styled) == "before red after"
    assert visible_width(styled) == 16


def test_theme_style_helper_reapplies_outer_style_after_specific_inner_resets() -> None:
    from loushang.tui import apply_theme_style

    styled = apply_theme_style("before \x1b[31mred\x1b[39m after", {"color": "cyan", "underline": True})

    assert styled == "\x1b[4;36mbefore \x1b[31mred\x1b[39m\x1b[4;36m after\x1b[24;39m"
    assert strip_control_sequences(styled) == "before red after"


def test_text_truncated_text_and_box_resolve_theme_tokens_and_invalidate_by_theme_version() -> None:
    theme = ThemeResolver(
        defaults={
            "basic.text": {"color": "red"},
            "basic.truncated": {"color": "green"},
            "basic.box": {"background": "blue"},
        }
    )
    text = Text("hello", padding_x=0, padding_y=0, theme=theme, theme_token="basic.text")
    truncated = TruncatedText("abcdef", padding_x=0, padding_y=0, theme=theme, theme_token="basic.truncated")
    box = Box(padding_x=1, padding_y=1, theme=theme, theme_token="basic.box")
    box.add_child(Text("inside", padding_x=0, padding_y=0))

    first_text = rendered_text(text, width=10)[0]
    first_truncated = rendered_text(truncated, width=5)[0]
    first_box = rendered_text(box, width=10)

    assert first_text.startswith("\x1b[31m")
    assert first_truncated.startswith("\x1b[32m")
    assert all(line.startswith("\x1b[44m") for line in first_box)
    assert tuple(strip_control_sequences(line) for line in first_box) == (
        "         ",
        " inside  ",
        "         ",
    )

    theme.update_overrides(
        {
            "basic.text": {"color": "blue"},
            "basic.truncated": {"color": "yellow"},
            "basic.box": {"background": "magenta"},
        }
    )

    assert rendered_text(text, width=10)[0].startswith("\x1b[34m")
    assert rendered_text(truncated, width=5)[0].startswith("\x1b[33m")
    assert all(line.startswith("\x1b[45m") for line in rendered_text(box, width=10))


def test_rule_loader_and_worked_divider_resolve_theme_tokens() -> None:
    from loushang.tui import DynamicBorder, WorkedDivider

    theme = ThemeResolver(
        defaults={
            "basic.rule": {"color": "cyan"},
            "basic.loader.indicator": {"color": "yellow"},
            "basic.loader.message": {"color": "bright_black"},
            "basic.worked": {"dim": True},
        }
    )
    loader = Loader(
        message="Working",
        frames=("*",),
        now_ms=lambda: 0,
        theme=theme,
        indicator_theme_token="basic.loader.indicator",
        message_theme_token="basic.loader.message",
    )

    rule_line = rendered_text(Rule(theme=theme, theme_token="basic.rule"), width=4, height=1)[0]
    dynamic_border_line = rendered_text(DynamicBorder(theme=theme, theme_token="basic.rule"), width=3, height=1)[0]
    loader_line = rendered_text(loader, width=18, height=2)[1]
    worked_line = rendered_text(WorkedDivider(3.01, theme=theme, theme_token="basic.worked"), width=24, height=1)[0]

    assert rule_line == "\x1b[36m───\x1b[39m"
    assert dynamic_border_line == "\x1b[36m──\x1b[39m"
    assert loader_line.startswith(" \x1b[33m*\x1b[39m \x1b[90mWorking\x1b[39m")
    assert strip_control_sequences(loader_line) == " * Working       "
    assert worked_line.startswith("\x1b[2m─ Worked for 3.01s ")
    assert worked_line.endswith("\x1b[22m")
    assert visible_width(worked_line) == 23


def test_basic_theme_change_is_line_level_diff_in_render_loop() -> None:
    theme = ThemeResolver(defaults={"basic.text": {"color": "red"}})
    text = Text("alpha", padding_x=0, padding_y=0, theme=theme, theme_token="basic.text")
    root = ScreenRoot(base=Container([text, Text("stable", padding_x=0, padding_y=0)]))
    runtime = TuiRuntime(
        render_loop=RenderLoop(root),
        terminal=FakeTerminalPort(size=TerminalSize(columns=12, rows=5)),
    )
    runtime.render_now()

    theme.update_overrides({"basic.text": {"color": "blue"}})
    step = runtime.render_now()

    step.assert_operation_class("changed_range_update")
    assert step.diagnostics.changed_line_range == (0, 0)
    assert tuple(strip_control_sequences(line) for line in step.diagnostics.current_logical_lines) == (
        "alpha",
        "stable",
    )

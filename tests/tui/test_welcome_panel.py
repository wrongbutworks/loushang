from __future__ import annotations

from loushang.tui import (
    LOUSHANG_GUANQUE_TOWER_LOGO,
    LoushangWelcomePanel,
    RenderConstraints,
    ThemeResolver,
    visible_width,
)


def _lines(panel: LoushangWelcomePanel, *, width: int = 80, height: int = 24) -> tuple[str, ...]:
    result = panel.render(RenderConstraints(width=width, max_height=height, visible_height=height))
    return tuple(line.text for line in result.lines)


def test_loushang_guanque_tower_logo_is_fixed_width_ascii() -> None:
    widths = {visible_width(line) for line in LOUSHANG_GUANQUE_TOWER_LOGO}

    assert widths == {18}
    assert all(line.isascii() for line in LOUSHANG_GUANQUE_TOWER_LOGO)


def test_loushang_welcome_panel_renders_single_column_card() -> None:
    panel = LoushangWelcomePanel(
        directory="~/workspace/loushang/.worktrees/loushang-tui-features",
        session="0c1c62ee-0d2c-49f3-9997-3a6550bfb7a8",
        provider="Kimi",
        model="kimi-for-coding",
    )

    lines = _lines(panel, width=80, height=24)
    rendered = "\n".join(lines)

    assert lines[0].startswith("╭── Loushang ")
    assert lines[-1].startswith("╰")
    assert "LOUSHANG" in rendered
    assert "Welcome to Loushang CLI" in rendered
    assert "欲穷千里目，更上一层楼" in rendered
    assert "From Loushang's height, farther horizons unfold." in rendered
    assert "Directory: " in rendered
    assert "Model:     " in rendered
    assert "more to see, one level higher" in rendered
    assert "\x1b[" not in rendered
    assert all(visible_width(line) == 79 for line in lines)


def test_loushang_welcome_panel_can_style_title_separately_from_border() -> None:
    panel = LoushangWelcomePanel(
        directory="~/workspace/loushang",
        model="kimi-for-coding",
        theme=ThemeResolver(
            defaults={
                "welcome.border": {"color": "bright_black"},
                "welcome.title": {"color": "cyan", "bold": True},
            }
        ),
    )

    top = _lines(panel, width=80, height=24)[0]

    assert top.startswith("\x1b[90m╭──\x1b[39m")
    assert "\x1b[1;36m Loushang \x1b[22;39m" in top


def test_loushang_welcome_panel_uses_banner_logo_on_wide_width() -> None:
    panel = LoushangWelcomePanel(
        directory="~/workspace/loushang/.worktrees/loushang-tui-features",
        model="kimi-for-coding",
    )

    lines = _lines(panel, width=96, height=28)
    rendered = "\n".join(lines)

    assert "   o" in rendered
    assert "  /|\\" in rendered
    assert "▀██▀" in rendered
    assert "████████▄▀███▀" in rendered
    assert all(visible_width(line) == 95 for line in lines)


def test_loushang_welcome_panel_uses_compact_logo_when_banner_would_not_fit() -> None:
    panel = LoushangWelcomePanel(
        directory="~/workspace/loushang/.worktrees/loushang-tui-features",
        model="kimi-for-coding",
    )

    lines = _lines(panel, width=96, height=20)
    rendered = "\n".join(lines)

    assert lines[-1].startswith("╰")
    assert "LOUSHANG" in rendered
    assert "▀██▀" not in rendered
    assert "From Loushang's height, farther horizons unfold." in rendered
    assert all(visible_width(line) == 95 for line in lines)


def test_loushang_welcome_panel_hides_logo_on_narrow_width() -> None:
    panel = LoushangWelcomePanel(directory="~/workspace/loushang", model="kimi-for-coding")

    lines = _lines(panel, width=44, height=20)
    rendered = "\n".join(lines)

    assert "LOUSHANG" not in rendered
    assert "Welcome to Loushang CLI" in rendered
    assert "Model:" in rendered
    assert all(visible_width(line) == 43 for line in lines)


def test_loushang_welcome_panel_respects_height_budget() -> None:
    panel = LoushangWelcomePanel(directory="~/workspace/loushang", model="kimi-for-coding")

    lines = _lines(panel, width=80, height=5)

    assert len(lines) == 5
    assert all(visible_width(line) == 79 for line in lines)

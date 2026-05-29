from __future__ import annotations

from typing import Any

from loushang.tui import RenderConstraints, visible_width


def rendered_text(part: Any, *, width: int = 20, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_text_omits_empty_or_whitespace_only_content() -> None:
    from loushang.tui import Text

    assert rendered_text(Text("")) == ()
    assert rendered_text(Text("   \n\t")) == ()


def test_ordinary_basic_parts_do_not_pad_to_terminal_width_by_default() -> None:
    from loushang.tui import Box, Text, TruncatedText

    assert rendered_text(Text("one", padding_x=0, padding_y=0), width=8, height=1) == ("one",)
    assert rendered_text(TruncatedText("one", padding_x=0, padding_y=0), width=8, height=1) == ("one",)
    assert all(visible_width(line) <= 7 for line in rendered_text(Text("12345678", padding_x=0, padding_y=0), width=8))
    assert all(visible_width(line) <= 7 for line in rendered_text(TruncatedText("12345678"), width=8))

    box = Box(padding_x=1, padding_y=0)
    box.add_child(Text("one", padding_x=0, padding_y=0))

    assert rendered_text(box, width=8, height=1) == (" one",)
    assert all(visible_width(line) <= 7 for line in rendered_text(box, width=8, height=1))


def test_text_wraps_by_cell_width_with_padding_and_tabs() -> None:
    from loushang.tui import Text

    text = Text("ab\t中cd", padding_x=1, padding_y=1)

    assert rendered_text(text, width=8, height=10) == (
        "",
        " ab ",
        " 中cd ",
        "",
    )


def test_text_preserves_ansi_styles_while_wrapping_and_padding() -> None:
    from loushang.tui import Text, strip_control_sequences

    lines = rendered_text(Text("\x1b[31mred blue\x1b[0m", padding_x=1, padding_y=0), width=7)

    assert tuple(strip_control_sequences(line) for line in lines) == (" red ", " blue ")
    assert all(visible_width(line) < 7 for line in lines)
    assert lines[0].startswith(" \x1b[31m")
    assert lines[1].startswith(" \x1b[31m")


def test_text_preserves_osc8_hyperlinks_across_wrapped_lines() -> None:
    from loushang.tui import Text, strip_control_sequences

    url = "https://example.com"
    open_link = f"\x1b]8;;{url}\x1b\\"
    close_link = "\x1b]8;;\x1b\\"
    lines = rendered_text(Text(f"{open_link}0123456789{close_link}", padding_x=0, padding_y=0), width=6)

    assert tuple(strip_control_sequences(line) for line in lines) == ("01234", "56789")
    assert all(line.startswith(open_link) for line in lines)
    assert lines[0].endswith(close_link)


def test_text_cache_invalidates_when_text_or_background_changes() -> None:
    from loushang.tui import Text

    text = Text("one", padding_x=0, padding_y=0)
    assert rendered_text(text, width=8) == ("one",)

    text.set_text("two")
    assert rendered_text(text, width=8) == ("two",)

    text.set_background(lambda line: f"\x1b[7m{line}\x1b[0m")
    rendered = rendered_text(text, width=8)
    assert rendered == ("\x1b[7mtwo    \x1b[0m",)
    assert visible_width(rendered[0]) == 7


def test_spacer_renders_empty_lines_up_to_height_budget() -> None:
    from loushang.tui import Spacer

    spacer = Spacer(3)

    assert rendered_text(spacer, width=5, height=5) == ("", "", "")
    assert rendered_text(spacer, width=5, height=2) == ("", "")

    spacer.set_lines(1)
    assert rendered_text(spacer, width=5, height=5) == ("",)


def test_truncated_text_uses_first_line_and_cell_width_with_padding() -> None:
    from loushang.tui import TruncatedText

    text = TruncatedText("ab中cd\nignored", padding_x=1, padding_y=1)

    assert rendered_text(text, width=7, height=5) == (
        "",
        " a\x1b[0m...\x1b[0m ",
        "",
    )


def test_truncated_text_resets_styled_prefix_before_ellipsis() -> None:
    from loushang.tui import TruncatedText

    line = rendered_text(TruncatedText("\x1b[31mThis is a very long red text\x1b[0m"), width=14, height=1)[0]

    assert visible_width(line) == 13
    assert line.startswith("\x1b[31m")
    assert "\x1b[0m..." in line


def test_truncated_text_handles_empty_and_exact_fit_without_ellipsis() -> None:
    from loushang.tui import TruncatedText

    assert rendered_text(TruncatedText("", padding_x=1, padding_y=0), width=8, height=1) == ("  ",)

    exact = rendered_text(TruncatedText("Hello", padding_x=1, padding_y=0), width=7, height=1)[0]

    assert visible_width(exact) == 6
    assert "..." in exact
    assert exact == " H\x1b[0m...\x1b[0m "


def test_box_composes_children_with_padding_background_and_cache_invalidation() -> None:
    from loushang.tui import Box, Text, strip_control_sequences

    child = Text("alpha", padding_x=0, padding_y=0)
    box = Box(padding_x=1, padding_y=1, background=lambda line: f"\x1b[44m{line}\x1b[0m")
    box.add_child(child)

    rendered = rendered_text(box, width=10, height=10)
    assert tuple(strip_control_sequences(line) for line in rendered) == (
        "         ",
        " alpha   ",
        "         ",
    )
    assert all(visible_width(line) == 9 for line in rendered)

    child.set_text("beta")
    child.invalidate()
    box.invalidate()

    assert tuple(strip_control_sequences(line) for line in rendered_text(box, width=10)) == (
        "         ",
        " beta    ",
        "         ",
    )


def test_box_omits_empty_children_and_caps_to_height_budget() -> None:
    from loushang.tui import Box, Spacer, Text

    empty = Box()
    assert rendered_text(empty, width=8, height=5) == ()

    box = Box(padding_x=0, padding_y=1)
    box.add_child(Text("one\ntwo", padding_x=0, padding_y=0))
    box.add_child(Spacer(1))
    box.add_child(Text("three", padding_x=0, padding_y=0))

    result = box.render(RenderConstraints(width=8, max_height=4))

    assert tuple(line.text for line in result.lines) == (
        "",
        "one",
        "two",
        "",
    )

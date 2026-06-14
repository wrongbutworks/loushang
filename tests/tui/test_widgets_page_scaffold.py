from __future__ import annotations

import runpy
from dataclasses import dataclass
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    strip_control_sequences,
)
from loushang.tui.ui_parts.widgets.page_scaffold import PageScaffold
from tests.tui.widget_example_playback import play_example


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


@dataclass(slots=True)
class StaticPart:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines(
            [RenderLine(line[: constraints.width]) for line in self.lines[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class CursorPart(StaticPart):
    cursor: CursorDeclaration | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        result = StaticPart.render(self, constraints)
        return RenderResult.from_lines(result.lines, constraints=constraints, cursor=self.cursor)


def test_page_scaffold_renders_body_only_page() -> None:
    scaffold = PageScaffold(body=StaticPart(("body",)))

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_ignores_non_renderable_optional_header() -> None:
    scaffold = PageScaffold(
        header=object(),
        body=StaticPart(("body",)),
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_renders_blank_line_for_non_renderable_body() -> None:
    scaffold = PageScaffold(body=object())

    assert plain_lines(scaffold, width=20, height=3) == ("",)


def test_page_scaffold_renders_header_separator_body_padding_and_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=12, height=5) == (
        "header",
        "------------",
        "body",
        "",
        "footer",
    )


def test_page_scaffold_themes_separator_and_footer_without_changing_plain_text() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.pageScaffold.separator": {"color": "bright_black"},
            "widget.pageScaffold.footer": {"dim": True},
        }
    )
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        separator_after_header=True,
        theme=theme,
    )

    raw = render_lines(scaffold, width=12, height=5)

    assert raw[1].startswith("\x1b[90m")
    assert raw[1].endswith("\x1b[39m")
    assert raw[-1].startswith("\x1b[2m")
    assert raw[-1].endswith("\x1b[22m")
    assert tuple(strip_control_sequences(line) for line in raw) == (
        "header",
        "------------",
        "body",
        "",
        "footer",
    )


def test_page_scaffold_themed_footer_truncates_to_visible_width() -> None:
    theme = ThemeResolver(defaults={"widget.pageScaffold.footer": {"color": "bright_black"}})
    scaffold = PageScaffold(
        body=StaticPart(("body",)),
        footer="very long footer",
        theme=theme,
    )

    raw = render_lines(scaffold, width=8, height=3)

    assert raw[-1].startswith("\x1b[90m")
    assert raw[-1].endswith("\x1b[39m")
    assert strip_control_sequences(raw[-1]) == "very lon"


def test_page_scaffold_reserves_footer_height_under_long_body_content() -> None:
    scaffold = PageScaffold(
        body=StaticPart(tuple(f"row {index}" for index in range(10))),
        footer="footer",
    )

    lines = plain_lines(scaffold, width=20, height=4)

    assert lines[-1] == "footer"
    assert "row 0" in lines
    assert "row 9" not in lines


def test_page_scaffold_renders_body_padding_inside_reserved_footer_area() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        separator_after_header=True,
        body_padding_top=1,
        body_padding_bottom=2,
    )

    assert plain_lines(scaffold, width=12, height=7) == (
        "header",
        "------------",
        "",
        "body",
        "",
        "",
        "footer",
    )


def test_page_scaffold_body_padding_yields_to_body_and_footer_when_height_is_tight() -> None:
    scaffold = PageScaffold(
        body=StaticPart(("body",)),
        footer="footer",
        body_padding_top=3,
        body_padding_bottom=3,
    )

    assert plain_lines(scaffold, width=20, height=2) == ("body", "footer")


def test_page_scaffold_body_padding_counts_against_body_viewport_budget() -> None:
    scaffold = PageScaffold(
        body=StaticPart(tuple(f"row {index}" for index in range(10))),
        footer="footer",
        body_padding_top=1,
        body_padding_bottom=1,
    )

    lines = plain_lines(scaffold, width=20, height=6)

    assert lines == ("", "row 0", "row 1", "row 2", "", "footer")
    assert "row 3" not in lines


def test_page_scaffold_uses_visible_height_for_footer_padding() -> None:
    scaffold = PageScaffold(
        body=StaticPart(tuple(f"row {index}" for index in range(10))),
        footer="footer",
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=1000, visible_height=4))
    lines = tuple(line.text for line in result.lines)

    assert len(lines) == 4
    assert lines[-1] == "footer"


def test_page_scaffold_tiny_heights_prioritize_header_body_then_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
    )

    assert plain_lines(scaffold, width=20, height=1) == ("header",)
    assert plain_lines(scaffold, width=20, height=2) == ("header", "body")


def test_page_scaffold_offsets_body_cursor_after_header_and_separator() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        footer="footer",
        focused=True,
        focus_region="body",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=5))

    assert result.cursor == CursorDeclaration(row=2, column=2)


def test_page_scaffold_offsets_body_cursor_after_body_top_padding() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=3)),
        footer="footer",
        focused=True,
        focus_region="body",
        separator_after_header=True,
        body_padding_top=2,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=7))

    assert result.cursor == CursorDeclaration(row=4, column=3)


def test_page_scaffold_uses_header_cursor_without_body_offset() -> None:
    scaffold = PageScaffold(
        header=CursorPart(("header",), CursorDeclaration(row=0, column=1)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        focused=True,
        focus_region="header",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=4))

    assert result.cursor == CursorDeclaration(row=0, column=1)


def test_page_scaffold_fallback_cursor_stays_in_focused_body_region() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        focused=True,
        focus_region="body",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=5))

    assert result.cursor == CursorDeclaration(row=2, column=0)


@dataclass(slots=True)
class FocusablePart(StaticPart):
    focused: bool = False
    blurred: bool = False
    handled_keys: tuple[str, ...] = ()
    editor_target: object | None = None

    def focus(self) -> None:
        self.focused = True
        self.blurred = False

    def blur(self) -> None:
        self.focused = False
        self.blurred = True

    def handle_input(self, event: object) -> object:
        key = getattr(event, "key", "")
        if key in self.handled_keys:
            return f"handled:{key}"
        return None

    def editor_input_target(self) -> object | None:
        return self.editor_target if self.focused else None


def test_page_scaffold_focus_and_blur_delegate_to_active_slot() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focus_region="body")

    scaffold.focus()
    assert scaffold.focused is True
    assert body.focused is True
    assert header.focused is False

    scaffold.blur()
    assert scaffold.focused is False
    assert body.blurred is True
    assert header.blurred is True


def test_page_scaffold_down_and_enter_from_header_focus_body_before_header_delegation() -> None:
    header = FocusablePart(("header",), handled_keys=("enter", "down"))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="header")
    scaffold.focus_header()

    assert scaffold.handle_input(InputEvent(kind="key", key="enter")) is True
    assert scaffold.focus_region == "body"
    assert body.focused is True
    assert header.focused is False


def test_page_scaffold_unhandled_up_and_shift_tab_from_body_focus_header() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")
    scaffold.focus_body()

    assert scaffold.handle_input(InputEvent(kind="key", key="up")) is True
    assert scaffold.focus_region == "header"
    assert header.focused is True
    assert body.focused is False

    assert scaffold.handle_input(InputEvent(kind="key", key="down")) is True
    assert scaffold.handle_input(InputEvent(kind="key", key="shift+tab")) is True
    assert scaffold.focus_region == "header"


def test_page_scaffold_does_not_steal_handled_body_input() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",), handled_keys=("up",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")
    scaffold.focus_body()

    assert scaffold.handle_input(InputEvent(kind="key", key="up")) == "handled:up"
    assert scaffold.focus_region == "body"


def test_page_scaffold_editor_target_delegates_to_current_focus_region() -> None:
    header_target = object()
    body_target = object()
    header = FocusablePart(("header",), editor_target=header_target)
    body = FocusablePart(("body",), editor_target=body_target)
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")

    scaffold.focus_body()
    assert scaffold.editor_input_target() is body_target

    scaffold.focus_header()
    assert scaffold.editor_input_target() is header_target


def test_page_scaffold_footer_callable_receives_focus_context() -> None:
    body = FocusablePart(("body",))
    header = FocusablePart(("header",))

    def footer(context: object) -> str:
        return (
            f"{context.focus_region}:"
            f"{context.header_focused}:"
            f"{context.body_focused}"
        )

    scaffold = PageScaffold(header=header, body=body, footer=footer, focused=True, focus_region="body")

    assert plain_lines(scaffold, width=40, height=4)[-1] == "body:False:True"
    scaffold.focus_header()
    assert plain_lines(scaffold, width=40, height=4)[-1] == "header:True:False"


def test_page_scaffold_missing_optional_methods_do_not_crash() -> None:
    scaffold = PageScaffold(header=object(), body=object(), footer="footer", focused=True)

    assert plain_lines(scaffold, width=20, height=3)[-1] == "footer"
    assert scaffold.handle_input(InputEvent(kind="key", key="up")) in {False, None}
    assert scaffold.editor_input_target() is None


def test_page_scaffold_public_exports() -> None:
    from loushang.tui import PageScaffold as PublicPageScaffold
    from loushang.tui import PageScaffoldContext as PublicPageScaffoldContext
    from loushang.tui import PageScaffoldFooter as PublicPageScaffoldFooter
    from loushang.tui.ui_parts import PageScaffold as UiPageScaffold
    from loushang.tui.ui_parts import PageScaffoldContext as UiPageScaffoldContext
    from loushang.tui.ui_parts import PageScaffoldFooter as UiPageScaffoldFooter
    from loushang.tui.ui_parts.widgets import PageScaffold as WidgetPageScaffold
    from loushang.tui.ui_parts.widgets import (
        PageScaffoldContext as WidgetPageScaffoldContext,
    )
    from loushang.tui.ui_parts.widgets import (
        PageScaffoldFooter as WidgetPageScaffoldFooter,
    )
    from loushang.tui.ui_parts.widgets.page_scaffold import (
        PageScaffoldContext,
        PageScaffoldFooter,
    )

    assert PublicPageScaffold is PageScaffold
    assert UiPageScaffold is PageScaffold
    assert WidgetPageScaffold is PageScaffold
    assert PublicPageScaffoldContext is PageScaffoldContext
    assert PublicPageScaffoldContext is WidgetPageScaffoldContext
    assert UiPageScaffoldContext is WidgetPageScaffoldContext
    assert PublicPageScaffoldFooter is PageScaffoldFooter
    assert PublicPageScaffoldFooter is WidgetPageScaffoldFooter
    assert UiPageScaffoldFooter is WidgetPageScaffoldFooter


def test_page_scaffold_example_imports_and_renders() -> None:
    namespace = runpy.run_path("examples/tui/53_widgets_page_scaffold.py", run_name="__test__")
    app = namespace["build_app"]()
    result = app.render(RenderConstraints(width=96, max_height=20))

    assert result.lines
    assert any("\x1b[" in line.text for line in result.lines)


def test_page_scaffold_example_playback_switches_focus_and_keeps_footer() -> None:
    frames = play_example(
        "examples/tui/53_widgets_page_scaffold.py",
        events=(
            ("up to header", InputEvent(kind="key", key="up")),
            ("right models", InputEvent(kind="key", key="right")),
            ("down to body", InputEvent(kind="key", key="down")),
            ("down list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pageDown")),
        ),
        width=96,
        height=20,
    )

    initial = frames[0].lines
    header = frames[1].lines
    models = frames[2].lines
    body = frames[3].lines
    scrolled = frames[-1].lines

    assert initial[0].startswith("*[Config]")
    assert initial[-1].startswith("Body |")
    assert header[0].startswith(">[Config]")
    assert header[-1].startswith("Header |")
    assert ">[Models]" in models[0]
    assert "*[Models]" in body[0]
    assert body[-1].startswith("Body |")
    assert scrolled[-1].startswith("Body |")
    assert any("more below" in line.lower() or "more above" in line.lower() for line in scrolled)
    assert frames[-1].cursor[0] < 19

from __future__ import annotations

from dataclasses import dataclass

from loushang.tui import (
    ExtensionHost,
    FooterField,
    FooterStatusLine,
    FooterView,
    PublicTuiApi,
    RenderConstraints,
    RenderLine,
    RenderResult,
    StatusField,
    visible_width,
)
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.status import _render_extension_statuses


@dataclass(slots=True)
class StaticRenderable:
    text: str

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine(self.text)], constraints=constraints)


def rendered_text(part: object, *, width: int = 40, height: int = 4) -> tuple[str, ...]:
    render = getattr(part, "render")
    result = render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_footer_status_line_right_aligns_right_fields_and_omits_low_priority_fields() -> None:
    line = FooterStatusLine(
        fields=(
            FooterField("weekly 72%", side="left", priority=100),
            FooterField("~/workspace/loushang", side="left", priority=10),
            FooterField("gpt-5 xhigh", side="right", priority=100),
        )
    )

    lines = rendered_text(line, width=32, height=1)

    assert lines == ("weekly 72%          gpt-5 xhigh",)
    assert visible_width(lines[0]) == 31


def test_footer_view_renders_primary_secondary_and_extension_status_lines() -> None:
    footer = FooterView(
        primary=FooterStatusLine(
            fields=(
                FooterField("↑12k", side="left", priority=100),
                FooterField("kimi-for-coding", side="right", priority=100),
            )
        ),
        secondary="~/workspace/loushang (feat/native)",
        extension_statuses=(
            StatusField("plan 2/5", priority=100),
            StatusField("bad\nstatus\ttext", priority=50),
        ),
    )

    assert rendered_text(footer, width=48, height=4) == (
        "↑12k                            kimi-for-coding",
        "~/workspace/loushang (feat/native)",
        "plan 2/5 | bad status text",
    )


def test_footer_view_prefers_primary_line_under_height_pressure() -> None:
    footer = FooterView(
        primary="primary",
        secondary="secondary",
        extension_statuses=(StatusField("extension", priority=100),),
    )

    assert rendered_text(footer, width=24, height=1) == ("primary",)


def test_footer_view_preserves_extension_status_tokens_when_sanitizing() -> None:
    theme = ThemeResolver(defaults={"statusBar.model": {"foreground": "red"}})
    lines = _render_extension_statuses(
        (
            StatusField("bad\nmodel\ttext", priority=100, token="model"),
        ),
        RenderConstraints(width=40, max_height=1),
        style_mode="codex-like",
        theme=theme,
    )

    assert lines == ["\x1b[31mbad model text\x1b[39m"]


def test_extension_api_can_replace_custom_footer_and_dispose_it() -> None:
    host = ExtensionHost()
    api = PublicTuiApi(extension_id="ext", host=host)

    handle = api.set_footer(StaticRenderable("custom footer"))

    assert host.footer() == StaticRenderable("custom footer")

    handle.dispose()

    assert host.footer() is None

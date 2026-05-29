from __future__ import annotations

from dataclasses import dataclass

import pytest

import loushang.tui.markdown.renderer as markdown_renderer_module
from loushang.tui import (
    MarkdownRenderer,
    RenderConstraints,
    TerminalCapabilities,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)


@dataclass(frozen=True, slots=True)
class MarkdownFixture:
    name: str
    markdown: str
    width: int
    plain_lines: tuple[str, ...]
    ansi_fragments: tuple[str, ...] = ()


PI_STYLE_THEME = ThemeResolver(
    defaults={
        "markdown.heading.level1": {"color": "cyan"},
        "markdown.heading.level2": {"color": "cyan"},
        "markdown.heading.level3": {"color": "cyan"},
        "markdown.strong": {"bold": True},
        "markdown.emphasis": {"italic": True},
        "markdown.strikethrough": {"strikethrough": True},
        "markdown.inline_code": {"color": "yellow"},
        "markdown.link": {"underline": True, "color": "blue", "hyperlink": True},
        "markdown.linkUrl": {"color": "bright_black"},
        "markdown.list.marker": {"color": "yellow"},
        "markdown.quote.marker": {"color": "green"},
        "markdown.quote.text": {"italic": True},
        "markdown.code.fence": {"color": "bright_black"},
        "markdown.code.text": {"color": 252},
        "markdown.table.header": {"bold": True},
        "markdown.hr": {"dim": True},
    }
)


PI_MARKDOWN_FIXTURES = (
    MarkdownFixture(
        name="headings_spacing_and_hr",
        markdown="# Title\nParagraph with **bold** and `code`.\n## Section\n### Detail\n---",
        width=46,
        plain_lines=(
            "Title",
            "",
            "Paragraph with bold and code.",
            "",
            "Section",
            "",
            "### Detail",
            "",
            "─────────────────────────────────────────────",
        ),
        ansi_fragments=(
            "\x1b[1;4;36mTitle\x1b[22;24;39m",
            "\x1b[1mbold\x1b[22m",
            "\x1b[33mcode\x1b[39m",
            "\x1b[2m─────────────────────────────────────────────\x1b[22m",
        ),
    ),
    MarkdownFixture(
        name="osc8_bare_links_email_and_strikethrough",
        markdown="Visit https://example.com/docs and [docs](https://example.com). "
        "Email user@example.com and ~~done~~.",
        width=46,
        plain_lines=(
            "Visit https://example.com/docs and docs.",
            "Email user@example.com and done.",
        ),
        ansi_fragments=(
            "\x1b]8;;https://example.com/docs\x1b\\",
            "\x1b]8;;mailto:user@example.com\x1b\\",
            "\x1b[9mdone\x1b[29m",
        ),
    ),
    MarkdownFixture(
        name="recursive_quote_list_and_table",
        markdown="> Quote with `code`\n"
        "> - first\n"
        "> - second item that wraps\n"
        ">\n"
        "> | A | B |\n"
        "> | --- | --- |\n"
        "> | one | two |",
        width=46,
        plain_lines=(
            "│ Quote with code",
            "│ - first",
            "│ - second item that wraps",
            "│ ┌─────┬─────┐",
            "│ │ A   │ B   │",
            "│ ├─────┼─────┤",
            "│ │ one │ two │",
            "│ └─────┴─────┘",
        ),
        ansi_fragments=(
            "\x1b[32m│ \x1b[39m",
            "\x1b[3mQuote with \x1b[33mcode\x1b[39m\x1b[23m",
            "\x1b[1mA  \x1b[22m",
        ),
    ),
    MarkdownFixture(
        name="loose_list_with_code_and_nested_child",
        markdown="- parent item\n\n"
        "  second paragraph\n\n"
        "  ```python\n"
        "  print('hi')\n"
        "  ```\n\n"
        "  - child `code`",
        width=46,
        plain_lines=(
            "- parent item",
            "",
            "  second paragraph",
            "",
            "  ```python",
            "    print('hi')",
            "  ```",
            "",
            "    - child code",
        ),
        ansi_fragments=(
            "\x1b[33m- \x1b[39mparent item",
            "\x1b[90m```python\x1b[39m",
            "\x1b[38;5;252m  print('hi')\x1b[39m",
            "\x1b[33mcode\x1b[39m",
        ),
    ),
    MarkdownFixture(
        name="html_hardbreak_and_narrow_table_fallback",
        markdown="Line with hard break\\\nnext\n\n"
        "<aside>\n"
        "raw html\n"
        "</aside>\n\n"
        "| ExtremelyLongHeader | B |\n"
        "| --- | --- |\n"
        "| value-without-natural-break | two |",
        width=8,
        plain_lines=(
            "Line",
            "with",
            "hard",
            "break",
            "next",
            "",
            "<aside>",
            "raw",
            "html",
            "</aside",
            ">",
            "",
            "|",
            "Extreme",
            "lyLongH",
            "eader |",
            "B |",
            "| --- |",
            "--- |",
            "|",
            "value-w",
            "ithout-",
            "natural",
            "-break",
            "| two |",
        ),
        ansi_fragments=(),
    ),
)


@pytest.mark.parametrize("fixture", PI_MARKDOWN_FIXTURES, ids=lambda fixture: fixture.name)
def test_markdown_renderer_matches_pi_style_fixture_output(fixture: MarkdownFixture) -> None:
    lines = MarkdownRenderer(
        fixture.markdown,
        theme=PI_STYLE_THEME,
        capabilities=TerminalCapabilities(hyperlinks=True),
    ).render(RenderConstraints(width=fixture.width, max_height=80)).lines
    raw_lines = tuple(line.text for line in lines)

    assert tuple(strip_control_sequences(line) for line in raw_lines) == fixture.plain_lines
    assert all(visible_width(line) <= fixture.width - 1 for line in raw_lines)
    joined = "\n".join(raw_lines)
    for fragment in fixture.ansi_fragments:
        assert fragment in joined


def test_markdown_renderer_has_no_legacy_parser_path() -> None:
    legacy_symbols = {
        "_parse_markdown_blocks_legacy",
        "_render_markdown_line",
        "_quote_blocks",
    }

    assert not any(hasattr(markdown_renderer_module, symbol) for symbol in legacy_symbols)

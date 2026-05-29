from __future__ import annotations

import re

from markdown_it.token import Token

from loushang.tui.markdown.style import _apply_markdown_style, _resolve_style
from loushang.tui.markdown.types import _InlineToken
from loushang.tui.theme import (
    TerminalCapabilities,
    ThemeResolver,
    ThemeStyle,
    apply_theme_style,
)

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BARE_LINK_RE = re.compile(
    r"(?<![\w@])("
    r"https?://[^\s<>()]+"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r")"
)
_TRAILING_LINK_PUNCTUATION = ".,;:!?"


def _inline_tokens_from_markdown_it(tokens: tuple[Token, ...] | list[Token]) -> tuple[_InlineToken, ...]:
    inline_tokens, _index = _inline_tokens_until(tokens, 0, stop_type=None)
    return tuple(inline_tokens)


def _inline_tokens_from_plain_text(text: str) -> tuple[_InlineToken, ...]:
    if text == "":
        return ()
    return (_InlineToken("text", text=text),)


def _inline_tokens_until(
    tokens: tuple[Token, ...] | list[Token],
    index: int,
    *,
    stop_type: str | None,
    linkify: bool = True,
) -> tuple[list[_InlineToken], int]:
    rendered: list[_InlineToken] = []
    while index < len(tokens):
        token = tokens[index]
        if token.type == stop_type:
            return rendered, index + 1
        if token.type == "text":
            if linkify:
                rendered.extend(_linkify_plain_text(token.content))
            else:
                rendered.append(_InlineToken("text", text=token.content))
            index += 1
            continue
        if token.type == "code_inline":
            rendered.append(_InlineToken("code", text=token.content))
            index += 1
            continue
        if token.type == "softbreak":
            rendered.append(_InlineToken("softbreak"))
            index += 1
            continue
        if token.type == "hardbreak":
            rendered.append(_InlineToken("hardbreak"))
            index += 1
            continue
        if token.type == "html_inline":
            rendered.append(_InlineToken("text", text=token.content))
            index += 1
            continue
        if token.type == "strong_open":
            children, index = _inline_tokens_until(tokens, index + 1, stop_type="strong_close", linkify=linkify)
            rendered.append(_InlineToken("strong", children=tuple(children)))
            continue
        if token.type == "em_open":
            children, index = _inline_tokens_until(tokens, index + 1, stop_type="em_close", linkify=linkify)
            rendered.append(_InlineToken("emphasis", children=tuple(children)))
            continue
        if token.type == "s_open":
            children, index = _inline_tokens_until(tokens, index + 1, stop_type="s_close", linkify=linkify)
            plain = _inline_tokens_to_plain_text(tuple(children), preserve_markup=False, softbreak=" ")
            if plain[:1].isspace() or plain[-1:].isspace():
                rendered.append(_InlineToken("text", text=f"~~{plain}~~"))
            else:
                rendered.append(_InlineToken("strikethrough", children=tuple(children)))
            continue
        if token.type == "link_open":
            children, index = _inline_tokens_until(tokens, index + 1, stop_type="link_close", linkify=False)
            href = str(token.attrs.get("href", "")) if token.attrs else ""
            rendered.append(_InlineToken("link", children=tuple(children), href=href))
            continue
        index += 1
    return rendered, index


def _linkify_plain_text(text: str) -> list[_InlineToken]:
    tokens: list[_InlineToken] = []
    cursor = 0
    for match in _BARE_LINK_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            tokens.append(_InlineToken("text", text=text[cursor:start]))

        link_text, trailing = _split_link_trailing_punctuation(match.group(0))
        href = link_text if link_text.startswith(("http://", "https://")) else f"mailto:{link_text}"
        tokens.append(_InlineToken("link", children=(_InlineToken("text", text=link_text),), href=href))
        if trailing:
            tokens.append(_InlineToken("text", text=trailing))
        cursor = end
    if cursor < len(text):
        tokens.append(_InlineToken("text", text=text[cursor:]))
    return tokens


def _split_link_trailing_punctuation(text: str) -> tuple[str, str]:
    link_text = text
    trailing = ""
    while link_text and link_text[-1] in _TRAILING_LINK_PUNCTUATION:
        trailing = link_text[-1] + trailing
        link_text = link_text[:-1]
    return link_text, trailing


def _inline_tokens_to_plain_text(
    tokens: tuple[_InlineToken, ...],
    *,
    preserve_markup: bool,
    softbreak: str,
) -> str:
    parts: list[str] = []
    for token in tokens:
        if token.kind == "text":
            parts.append(token.text)
        elif token.kind == "code":
            parts.append(f"`{token.text}`" if preserve_markup else token.text)
        elif token.kind == "strong":
            content = _inline_tokens_to_plain_text(token.children, preserve_markup=preserve_markup, softbreak=softbreak)
            parts.append(f"**{content}**" if preserve_markup else content)
        elif token.kind == "emphasis":
            content = _inline_tokens_to_plain_text(token.children, preserve_markup=preserve_markup, softbreak=softbreak)
            parts.append(f"*{content}*" if preserve_markup else content)
        elif token.kind == "strikethrough":
            content = _inline_tokens_to_plain_text(token.children, preserve_markup=preserve_markup, softbreak=softbreak)
            parts.append(f"~~{content}~~" if preserve_markup else content)
        elif token.kind == "link":
            content = _inline_tokens_to_plain_text(token.children, preserve_markup=preserve_markup, softbreak=softbreak)
            comparison_href = token.href[7:] if token.href.startswith("mailto:") else token.href
            parts.append(f"{content} ({token.href})" if token.href and content not in {token.href, comparison_href} else content)
        elif token.kind in {"softbreak", "hardbreak"}:
            parts.append(softbreak)
    return "".join(parts)


def _render_inline(
    text: str,
    *,
    theme: ThemeResolver | None = None,
    capabilities: TerminalCapabilities | None = None,
) -> str:
    if theme is None:
        return _LINK_RE.sub(lambda match: f"{match.group(1)} ({match.group(2)})", text)

    output: list[str] = []
    index = 0
    while index < len(text):
        link = _LINK_RE.match(text, index)
        if link is not None:
            output.append(
                _apply_markdown_style(
                    _render_inline(link.group(1), theme=theme, capabilities=capabilities),
                    "markdown.link",
                    theme,
                    capabilities,
                )
            )
            output.append(f" ({link.group(2)})")
            index = link.end()
            continue

        matched = False
        for marker, token in (
            ("`", "markdown.inline_code"),
            ("**", "markdown.strong"),
            ("~~", "markdown.strikethrough"),
            ("*", "markdown.emphasis"),
        ):
            if not text.startswith(marker, index):
                continue
            end = text.find(marker, index + len(marker))
            if end <= index + len(marker):
                continue
            content = text[index + len(marker) : end]
            output.append(
                _apply_markdown_style(
                    _render_inline(content, theme=theme, capabilities=capabilities),
                    token,
                    theme,
                    capabilities,
                )
            )
            index = end + len(marker)
            matched = True
            break
        if matched:
            continue

        output.append(text[index])
        index += 1
    return "".join(output)


def _render_inline_tokens(
    tokens: tuple[_InlineToken, ...],
    *,
    theme: ThemeResolver | None = None,
    capabilities: TerminalCapabilities | None = None,
    softbreak: str = "\n",
    text_token: str | None = None,
    default_style: ThemeStyle | None = None,
) -> str:
    if theme is None:
        return _inline_tokens_to_plain_text(tokens, preserve_markup=True, softbreak=softbreak)

    output: list[str] = []
    for token in tokens:
        if token.kind == "text":
            output.append(_apply_inline_text(token.text, text_token, default_style, theme, capabilities))
        elif token.kind == "code":
            output.append(_apply_markdown_style(token.text, "markdown.inline_code", theme, capabilities))
        elif token.kind == "strong":
            output.append(
                _apply_markdown_style(
                    _render_inline_tokens(
                        token.children,
                        theme=theme,
                        capabilities=capabilities,
                        softbreak=softbreak,
                        text_token=text_token,
                        default_style=default_style,
                    ),
                    "markdown.strong",
                    theme,
                    capabilities,
                )
            )
        elif token.kind == "emphasis":
            output.append(
                _apply_markdown_style(
                    _render_inline_tokens(
                        token.children,
                        theme=theme,
                        capabilities=capabilities,
                        softbreak=softbreak,
                        text_token=text_token,
                        default_style=default_style,
                    ),
                    "markdown.emphasis",
                    theme,
                    capabilities,
                )
            )
        elif token.kind == "strikethrough":
            output.append(
                _apply_markdown_style(
                    _render_inline_tokens(
                        token.children,
                        theme=theme,
                        capabilities=capabilities,
                        softbreak=softbreak,
                        text_token=text_token,
                        default_style=default_style,
                    ),
                    "markdown.strikethrough",
                    theme,
                    capabilities,
                )
            )
        elif token.kind == "link":
            label = _render_inline_tokens(
                token.children,
                theme=theme,
                capabilities=capabilities,
                softbreak=softbreak,
                text_token=text_token,
                default_style=None,
            )
            output.append(
                _render_link(
                    label,
                    _inline_tokens_to_plain_text(token.children, preserve_markup=False, softbreak=" "),
                    token.href,
                    theme,
                    capabilities,
                )
            )
        elif token.kind in {"softbreak", "hardbreak"}:
            output.append(softbreak)
    return "".join(output)


def _apply_inline_text(
    text: str,
    text_token: str | None,
    default_style: ThemeStyle | None,
    theme: ThemeResolver | None,
    capabilities: TerminalCapabilities | None,
) -> str:
    styled = _apply_markdown_style(text, text_token, theme, capabilities)
    return apply_theme_style(styled, default_style)


def _render_link(
    styled_label: str,
    plain_label: str,
    href: str,
    theme: ThemeResolver | None,
    capabilities: TerminalCapabilities | None,
) -> str:
    styled_link = _apply_markdown_style(styled_label, "markdown.link", theme, capabilities)
    if not href:
        return styled_link
    link_style = _resolve_style(theme, "markdown.link", capabilities)
    if link_style and link_style.get("hyperlink"):
        return _osc8_hyperlink(styled_link, href)
    comparison_href = href[7:] if href.startswith("mailto:") else href
    if plain_label == href or plain_label == comparison_href:
        return styled_link
    return styled_link + _apply_markdown_style(f" ({href})", "markdown.linkUrl", theme, capabilities)


def _osc8_hyperlink(text: str, href: str) -> str:
    return f"\x1b]8;;{href}\x1b\\{text}\x1b]8;;\x1b\\"

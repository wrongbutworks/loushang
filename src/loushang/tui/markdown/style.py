from __future__ import annotations

from loushang.tui.theme import (
    TerminalCapabilities,
    ThemeResolver,
    ThemeStyle,
    apply_theme_style,
)

_MARKDOWN_TOKEN_ALIASES = {
    "markdown.heading.level1": ("markdown.heading.1", "markdown.heading"),
    "markdown.heading.level2": ("markdown.heading.2", "markdown.heading"),
    "markdown.heading.level3": ("markdown.heading.3", "markdown.heading"),
    "markdown.heading.level4": ("markdown.heading.4", "markdown.heading"),
    "markdown.heading.level5": ("markdown.heading.5", "markdown.heading"),
    "markdown.heading.level6": ("markdown.heading.6", "markdown.heading"),
    "markdown.inline_code": ("markdown.code.inline", "markdown.code"),
    "markdown.code.fence": ("markdown.code.block.border",),
    "markdown.code.text": ("markdown.code.block",),
    "markdown.quote.marker": ("markdown.quote.border",),
    "markdown.quote": ("markdown.quote.text",),
    "markdown.list.marker": ("markdown.list.bullet",),
    "markdown.linkUrl": ("markdown.link.url",),
    "markdown.strong": ("markdown.bold",),
    "markdown.emphasis": ("markdown.italic",),
}


def _has_background_style(style: ThemeStyle | None) -> bool:
    return bool(style and (style.get("background") is not None or style.get("bg") is not None))


def _apply_markdown_style(
    text: str,
    token: str | None,
    theme: ThemeResolver | None,
    capabilities: TerminalCapabilities | None,
) -> str:
    style = _resolve_style(theme, token, capabilities)
    return apply_theme_style(text, style)


def _resolve_style(
    theme: ThemeResolver | None,
    token: str | None,
    capabilities: TerminalCapabilities | None,
) -> ThemeStyle | None:
    if theme is None or not token:
        return None
    resolved = theme.resolve(token, capabilities)
    if resolved:
        return resolved
    for alias in _MARKDOWN_TOKEN_ALIASES.get(token, ()):
        resolved = theme.resolve(alias, capabilities)
        if resolved:
            return resolved
    return resolved

from __future__ import annotations

from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style


def is_activation_event(event: object) -> bool:
    return (
        getattr(event, "kind", "") == "key"
        and getattr(event, "key", "") in {"enter", "space"}
        or getattr(event, "kind", "") == "text"
        and getattr(event, "text", "") == " "
    )


def callback_result(result: object) -> object:
    return True if result is None else result


def merge_theme_styles(*styles: ThemeStyle | None) -> ThemeStyle | None:
    merged: ThemeStyle = {}
    for style in styles:
        if style:
            merged.update(style)
    return merged or None


def resolve_theme_style(theme: ThemeResolver | None, token: str | None) -> ThemeStyle | None:
    if theme is None or not token:
        return None
    return theme.resolve(token)


def style_text(text: str, theme: ThemeResolver | None, *tokens: str | None) -> str:
    style = merge_theme_styles(*(resolve_theme_style(theme, token) for token in tokens))
    return apply_theme_style(text, style)

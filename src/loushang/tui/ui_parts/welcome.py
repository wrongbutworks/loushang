from __future__ import annotations

from dataclasses import dataclass, field

from loushang.tui.cell_width import (
    autowrap_safe_width,
    strip_control_sequences,
    truncate_to_width,
    visible_width,
    wrap_cells,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style

LOUSHANG_GUANQUE_TOWER_LOGO: tuple[str, ...] = (
    "        /\\        ",
    "    ___/  \\___    ",
    "   /          \\   ",
    "  /  LOUSHANG  \\  ",
    "  |     ||     |  ",
    "  |____/  \\____|  ",
)

LOUSHANG_BANNER_LOGO: tuple[str, ...] = (
    "   o",
    "  /|\\",
    "  / \\",
    "  ▄▄▄",
    "   ▀██▀                       █▄",
    "    ██                        ██          ▄        ▄▄",
    "    ██      ▄███▄ ██ ██ ▄██▀█ ████▄ ▄▀▀█▄ ████▄ ▄████",
    "    ██      ██ ██ ██ ██ ▀███▄ ██ ██ ▄█▀██ ██ ██ ██ ██",
    "   ████████▄▀███▀▄▀██▀██▄▄██▀▄██ ██▄▀█▄██▄██ ▀█▄▀████",
    "                                                   ██",
    "                                                 ▀▀▀",
)

_LOGO_WIDTH = 18
_BANNER_LOGO_MIN_WIDTH = 88
_WIDE_LOGO_MIN_WIDTH = 62
_MIN_PANEL_WIDTH = 12
_PERSON_LOGO_LINES = 3
_ROOF_LOGO_LINE = 3


def loushang_welcome_theme() -> ThemeResolver:
    return ThemeResolver(
        defaults={
            "welcome.border": {"color": "bright_black"},
            "welcome.title": {"color": "cyan", "bold": True},
            "welcome.logo.person": {"color": "black", "bold": True},
            "welcome.logo.roof": {"color": "yellow", "bold": True},
            "welcome.logo": {"color": "cyan"},
            "welcome.quote": {"color": "black", "bold": True},
            "welcome.quote.translation": {"color": "bright_blue"},
            "welcome.text": {"color": "black", "bold": True},
            "welcome.dim": {"color": "bright_black"},
            "welcome.field.label": {"color": "bright_black"},
            "welcome.value": {"color": "white"},
            "welcome.tip.label": {"color": "green", "bold": True},
            "welcome.tip": {"color": "bright_black"},
        }
    )


@dataclass(slots=True)
class LoushangWelcomePanel:
    title: str = "Loushang"
    subtitle: str = "Welcome to Loushang CLI"
    description: str = "Build, inspect, and steer coding agents from your terminal."
    directory: str = ""
    session: str = ""
    provider: str = ""
    model: str = ""
    api_key_label: str = ""
    quote: str = "欲穷千里目，更上一层楼"
    quote_translation: str = "From Loushang's height, farther horizons unfold."
    tip: str = "Ascend for more to see, one level higher."
    logo: tuple[str, ...] = LOUSHANG_GUANQUE_TOWER_LOGO
    banner_logo: tuple[str, ...] = LOUSHANG_BANNER_LOGO
    theme: ThemeResolver | None = None
    _logo_width: int = field(default=_LOGO_WIDTH, init=False, repr=False)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        width = max(_MIN_PANEL_WIDTH, autowrap_safe_width(constraints.width))
        body_width = max(1, width - 2)
        if constraints.max_height == 1:
            return RenderResult.from_lines([RenderLine(self._top_border(width))], constraints=constraints)
        body_height = max(0, constraints.max_height - 2)
        lines = [self._top_border(width)]
        lines.extend(self._body_lines(body_width, body_height=body_height))
        lines.append(self._bottom_border(width))
        return RenderResult.from_lines([RenderLine(line) for line in lines], constraints=constraints)

    def _body_lines(self, body_width: int, *, body_height: int) -> list[str]:
        candidates: list[list[str]] = []
        if body_width >= _BANNER_LOGO_MIN_WIDTH and self.banner_logo:
            candidates.append(self._banner_body_lines(body_width))
        if body_width >= _WIDE_LOGO_MIN_WIDTH and self.logo:
            candidates.append(self._wide_body_lines(body_width))
        candidates.append(self._compact_body_lines(body_width))
        content = candidates[-1]
        for candidate in candidates:
            if len(candidate) <= body_height:
                content = candidate
                break
        return [self._frame_body_line(line, body_width) for line in content[:body_height]]

    def _banner_body_lines(self, body_width: int) -> list[str]:
        rows = [""]
        logo_width = max(1, body_width - 2)
        for index, line in enumerate(self.banner_logo):
            if index < _PERSON_LOGO_LINES:
                token = "welcome.logo.person"
            elif index == _ROOF_LOGO_LINE:
                token = "welcome.logo.roof"
            else:
                token = "welcome.logo"
            rows.append("  " + self._fit(line, logo_width, token=token))
        rows.append("")
        rows.extend(self._quote_lines(body_width))
        rows.append("")
        rows.append("  " + self._fit(self.subtitle, max(1, body_width - 2), token="welcome.text"))
        rows.append("  " + self._fit(self.description, max(1, body_width - 2), token="welcome.dim"))
        rows.append("")
        rows.extend(self._field_lines(body_width))
        rows.append("")
        rows.extend(self._tip_lines(body_width))
        rows.append("")
        return rows

    def _wide_body_lines(self, body_width: int) -> list[str]:
        left_pad = 3
        gap = 4
        text_width = max(1, body_width - left_pad - self._logo_width - gap)
        logo_lines = _fixed_width_logo(self.logo, width=self._logo_width)
        text_lines = (
            self.subtitle,
            self.description,
            "",
            "/help for commands · @ for files",
            "",
            "",
        )
        rows = [""]
        for logo_line, text_line in zip(logo_lines, text_lines, strict=False):
            rows.append(
                (" " * left_pad)
                + self._style(logo_line, "welcome.logo")
                + (" " * gap)
                + self._fit(text_line, text_width, token="welcome.text")
            )
        rows.append("")
        rows.extend(self._quote_lines(body_width))
        rows.append("")
        rows.extend(self._field_lines(body_width))
        rows.append("")
        rows.extend(self._tip_lines(body_width))
        rows.append("")
        return rows

    def _compact_body_lines(self, body_width: int) -> list[str]:
        rows = [
            "",
            self._fit(self.subtitle, body_width, token="welcome.text"),
            self._fit(self.description, body_width, token="welcome.dim"),
            "",
        ]
        rows.extend(self._quote_lines(body_width))
        rows.append("")
        rows.extend(self._field_lines(body_width))
        rows.append("")
        rows.extend(self._tip_lines(body_width))
        rows.append("")
        return rows

    def _field_lines(self, body_width: int) -> list[str]:
        fields = (
            ("Directory", self.directory),
            ("Session", self.session),
            ("Provider", self.provider),
            ("API Key", self.api_key_label),
            ("Model", self.model),
        )
        rows: list[str] = []
        label_width = 11
        value_width = max(1, body_width - 2 - label_width)
        for label, value in fields:
            if not value:
                continue
            prefix = self._style(f"  {label + ':':<{label_width}}", "welcome.field.label")
            rows.append(prefix + self._fit(value, value_width, token="welcome.value"))
        return rows

    def _quote_lines(self, body_width: int) -> list[str]:
        rows: list[str] = []
        quote_width = max(1, body_width - 2)
        if self.quote:
            rows.append("  " + self._fit(self.quote, quote_width, token="welcome.quote"))
        if self.quote_translation:
            rows.append("  " + self._fit(self.quote_translation, quote_width, token="welcome.quote.translation"))
        return rows

    def _tip_lines(self, body_width: int) -> list[str]:
        if not self.tip:
            return []
        prefix = "  Tip: "
        first_width = max(1, body_width - visible_width(prefix))
        next_prefix = " " * visible_width(prefix)
        next_width = max(1, body_width - visible_width(next_prefix))
        wrapped: list[str] = []
        for index, chunk in enumerate(wrap_cells(self.tip, width=first_width)):
            line_prefix = self._style(prefix, "welcome.tip.label") if index == 0 else next_prefix
            available = first_width if index == 0 else next_width
            wrapped.append(line_prefix + self._fit(chunk, available, token="welcome.tip"))
        return wrapped

    def _top_border(self, width: int) -> str:
        label = f" {self.title} " if self.title else ""
        prefix = self._style("╭──", "welcome.border") + self._style(label, "welcome.title")
        suffix = "╮"
        filler_width = max(0, width - visible_width(prefix) - visible_width(suffix))
        return prefix + self._style(("─" * filler_width) + suffix, "welcome.border")

    def _bottom_border(self, width: int) -> str:
        return self._style("╰" + ("─" * max(0, width - 2)) + "╯", "welcome.border")

    def _frame_body_line(self, text: str, body_width: int) -> str:
        body = truncate_to_width(text, max_width=body_width, ellipsis="", pad=True)
        return self._style("│", "welcome.border") + body + self._style("│", "welcome.border")

    def _fit(self, text: str, width: int, *, token: str | None = None) -> str:
        fitted = truncate_to_width(text, max_width=max(1, width), ellipsis="...")
        return self._style(fitted, token)

    def _style(self, text: str, token: str | None) -> str:
        style = _resolve_style(self.theme, token)
        if style is None:
            return strip_control_sequences(text)
        return apply_theme_style(text, style)


def _fixed_width_logo(logo: tuple[str, ...], *, width: int) -> tuple[str, ...]:
    return tuple(truncate_to_width(line, max_width=width, ellipsis="", pad=True) for line in logo)


def _resolve_style(theme: ThemeResolver | None, token: str | None) -> ThemeStyle | None:
    if theme is None or not token:
        return None
    return theme.resolve(token)

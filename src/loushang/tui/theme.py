from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loushang.tui.terminal_capabilities import TerminalRuntimeCapabilities

ThemeStyle = dict[str, Any]

_FOREGROUND_CODES = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "default": "39",
    "bright_black": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
    "bright_white": "97",
}
_BACKGROUND_CODES = {
    "black": "40",
    "red": "41",
    "green": "42",
    "yellow": "43",
    "blue": "44",
    "magenta": "45",
    "cyan": "46",
    "white": "47",
    "default": "49",
    "bright_black": "100",
    "bright_red": "101",
    "bright_green": "102",
    "bright_yellow": "103",
    "bright_blue": "104",
    "bright_magenta": "105",
    "bright_cyan": "106",
    "bright_white": "107",
}


@dataclass(frozen=True, slots=True)
class TerminalCapabilities:
    truecolor: bool = True
    hyperlinks: bool = True


def theme_capabilities_from_runtime(runtime: TerminalRuntimeCapabilities) -> TerminalCapabilities:
    return TerminalCapabilities(truecolor=runtime.truecolor, hyperlinks=runtime.hyperlinks)


@dataclass(slots=True)
class ThemeResolver:
    defaults: dict[str, ThemeStyle] = field(default_factory=dict)
    overrides: dict[str, ThemeStyle] = field(default_factory=dict)
    version: int = 0

    def resolve(self, token: str, capabilities: TerminalCapabilities | None = None) -> ThemeStyle:
        capabilities = capabilities or TerminalCapabilities()
        merged = {**self.defaults.get(token, {}), **self.overrides.get(token, {})}
        return _degrade(merged, capabilities)

    def update_overrides(self, overrides: dict[str, ThemeStyle]) -> None:
        self.overrides = overrides
        self.version += 1


def apply_theme_style(text: str, style: ThemeStyle | None) -> str:
    if not style:
        return text
    codes = _style_codes(style)
    if not codes:
        return text
    active_code = f"\x1b[{';'.join(codes)}m"
    reset_codes = _style_reset_codes(style)
    reset_code = f"\x1b[{';'.join(reset_codes)}m"
    return f"{active_code}{_reapply_after_resetting_sgr(text, active_code, reset_codes)}{reset_code}"


def theme_signature(
    theme: ThemeResolver | None,
    token: str | None,
    capabilities: TerminalCapabilities | None = None,
) -> tuple[int, str, tuple[tuple[str, str], ...]] | None:
    if theme is None or not token:
        return None
    resolved = theme.resolve(token, capabilities)
    return theme.version, token, tuple(sorted((str(key), repr(value)) for key, value in resolved.items()))


def _degrade(style: ThemeStyle, capabilities: TerminalCapabilities) -> ThemeStyle:
    degraded = dict(style)
    if not capabilities.truecolor and isinstance(degraded.get("color"), str):
        degraded["color"] = _degrade_color(degraded["color"])
    if not capabilities.truecolor and isinstance(degraded.get("foreground"), str):
        degraded["foreground"] = _degrade_color(degraded["foreground"])
    if not capabilities.truecolor and isinstance(degraded.get("background"), str):
        degraded["background"] = _degrade_color(degraded["background"])
    if not capabilities.truecolor and isinstance(degraded.get("bg"), str):
        degraded["bg"] = _degrade_color(degraded["bg"])
    if not capabilities.hyperlinks and "hyperlink" in degraded:
        degraded["hyperlink"] = False
    return degraded


def _degrade_color(color: str) -> str | int:
    normalized = color.lower().replace("-", "_")
    if normalized in _FOREGROUND_CODES:
        return normalized
    mapping = {
        "#000000": 16,
        "#ff0000": 196,
        "#00ff00": 46,
        "#0000ff": 21,
        "#ffff00": 226,
        "#ff00ff": 201,
        "#00ffff": 51,
        "#ffffff": 231,
    }
    if normalized in mapping:
        return mapping[normalized]
    if normalized.startswith("#") and len(normalized) == 7:
        try:
            red = int(normalized[1:3], 16)
            green = int(normalized[3:5], 16)
            blue = int(normalized[5:7], 16)
        except ValueError:
            return "default"
        return _rgb_to_256(red, green, blue)
    return "default"


def _style_codes(style: ThemeStyle) -> list[str]:
    codes: list[str] = []
    if style.get("bold"):
        codes.append("1")
    if style.get("dim"):
        codes.append("2")
    if style.get("italic"):
        codes.append("3")
    if style.get("underline"):
        codes.append("4")
    if style.get("strikethrough"):
        codes.append("9")
    if style.get("reverse"):
        codes.append("7")
    if style.get("blink"):
        codes.append("5")
    if style.get("hidden"):
        codes.append("8")
    foreground = style.get("foreground", style.get("color"))
    background = style.get("background", style.get("bg"))
    foreground_code = _color_code(foreground, background=False)
    background_code = _color_code(background, background=True)
    if foreground_code is not None:
        codes.append(foreground_code)
    if background_code is not None:
        codes.append(background_code)
    return codes


def _style_reset_codes(style: ThemeStyle) -> list[str]:
    codes: list[str] = []
    if style.get("bold") or style.get("dim"):
        codes.append("22")
    if style.get("italic"):
        codes.append("23")
    if style.get("underline"):
        codes.append("24")
    if style.get("blink"):
        codes.append("25")
    if style.get("reverse"):
        codes.append("27")
    if style.get("hidden"):
        codes.append("28")
    if style.get("strikethrough"):
        codes.append("29")
    if _has_foreground(style):
        codes.append("39")
    if _has_background(style):
        codes.append("49")
    return codes or ["0"]


def _has_foreground(style: ThemeStyle) -> bool:
    return bool(style.get("foreground", style.get("color")) is not None)


def _has_background(style: ThemeStyle) -> bool:
    return bool(style.get("background", style.get("bg")) is not None)


def _reapply_after_resetting_sgr(text: str, active_code: str, reset_codes: list[str]) -> str:
    if "\x1b" not in text:
        return text
    reset_set = {int(code) for code in reset_codes if code.isdigit()}
    output: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("\x1b[", index):
            end = text.find("m", index + 2)
            if end != -1:
                code = text[index : end + 1]
                output.append(code)
                if _sgr_resets_active_style(code, reset_set):
                    output.append(active_code)
                index = end + 1
                continue
        output.append(text[index])
        index += 1
    return "".join(output)


def _sgr_resets_active_style(code: str, reset_codes: set[int]) -> bool:
    params = code[2:-1]
    if params == "":
        return True
    values: list[int] = []
    for part in params.split(";"):
        try:
            values.append(int(part or "0"))
        except ValueError:
            continue
    return 0 in values or any(value in reset_codes for value in values)


def _color_code(value: object, *, background: bool) -> str | None:
    if isinstance(value, int):
        if not 0 <= value <= 255:
            return None
        prefix = "48" if background else "38"
        return f"{prefix};5;{value}"
    if not isinstance(value, str):
        return None
    if value == "":
        return "49" if background else "39"
    normalized = value.lower().replace("-", "_")
    mapping = _BACKGROUND_CODES if background else _FOREGROUND_CODES
    if normalized in mapping:
        return mapping[normalized]
    if normalized.startswith("#") and len(normalized) == 7:
        try:
            red = int(normalized[1:3], 16)
            green = int(normalized[3:5], 16)
            blue = int(normalized[5:7], 16)
        except ValueError:
            return None
        prefix = "48" if background else "38"
        return f"{prefix};2;{red};{green};{blue}"
    return None


_CUBE_VALUES = (0, 95, 135, 175, 215, 255)
_GRAY_VALUES = tuple(8 + index * 10 for index in range(24))


def _rgb_to_256(red: int, green: int, blue: int) -> int:
    red_index = _closest_index(red, _CUBE_VALUES)
    green_index = _closest_index(green, _CUBE_VALUES)
    blue_index = _closest_index(blue, _CUBE_VALUES)
    cube_red = _CUBE_VALUES[red_index]
    cube_green = _CUBE_VALUES[green_index]
    cube_blue = _CUBE_VALUES[blue_index]
    cube_index = 16 + (36 * red_index) + (6 * green_index) + blue_index
    cube_distance = _color_distance(red, green, blue, cube_red, cube_green, cube_blue)

    gray = round((0.299 * red) + (0.587 * green) + (0.114 * blue))
    gray_index = _closest_index(gray, _GRAY_VALUES)
    gray_value = _GRAY_VALUES[gray_index]
    ansi_gray_index = 232 + gray_index
    gray_distance = _color_distance(red, green, blue, gray_value, gray_value, gray_value)

    if max(red, green, blue) - min(red, green, blue) < 10 and gray_distance < cube_distance:
        return ansi_gray_index
    return cube_index


def _closest_index(value: int, candidates: tuple[int, ...]) -> int:
    return min(range(len(candidates)), key=lambda index: abs(value - candidates[index]))


def _color_distance(red_a: int, green_a: int, blue_a: int, red_b: int, green_b: int, blue_b: int) -> float:
    red_delta = red_a - red_b
    green_delta = green_a - green_b
    blue_delta = blue_a - blue_b
    return (red_delta * red_delta * 0.299) + (green_delta * green_delta * 0.587) + (
        blue_delta * blue_delta * 0.114
    )

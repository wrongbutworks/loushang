from __future__ import annotations

import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

TAB_WIDTH = 3
AMBIGUOUS_WIDTH_ENV = "LOUSHANG_TUI_AMBIGUOUS_WIDTH"
_THAI_LAO_AM_TRANSLATION = str.maketrans({"\u0e33": "\u0e4d\u0e32", "\u0eb3": "\u0ecd\u0eb2"})
_VISIBLE_WIDTH_CACHE_SIZE = 16_384
_CLUSTER_WIDTH_CACHE_SIZE = 16_384
_CHAR_WIDTH_CACHE_SIZE = 4_096
AmbiguousWidth = Literal[1, 2]
_AMBIGUOUS_WIDTH: AmbiguousWidth = 1


@dataclass(frozen=True, slots=True)
class ColumnSlice:
    text: str
    width: int


def strip_control_sequences(text: str) -> str:
    """Remove terminal control sequences that do not occupy cells."""

    if "\x1b" not in text:
        return text

    output: list[str] = []
    index = 0
    while index < len(text):
        control = _extract_control_sequence(text, index)
        if control is not None:
            index += control.length
            continue
        output.append(text[index])
        index += 1
    return "".join(output)


def visible_width(text: str) -> int:
    return _visible_width_cached(text)


def ambiguous_width() -> AmbiguousWidth:
    return _AMBIGUOUS_WIDTH


def set_ambiguous_width(width: AmbiguousWidth) -> None:
    global _AMBIGUOUS_WIDTH
    if width not in (1, 2):
        raise ValueError("ambiguous width must be 1 or 2")
    if _AMBIGUOUS_WIDTH == width:
        return
    _AMBIGUOUS_WIDTH = width
    _visible_width_cached.cache_clear()
    _cluster_width.cache_clear()
    _char_width.cache_clear()


def configure_cell_width_from_environment(env: Mapping[str, str] | None = None) -> None:
    source = os.environ if env is None else env
    set_ambiguous_width(_parse_ambiguous_width(source.get(AMBIGUOUS_WIDTH_ENV)))


def normalize_box_drawing_diagram(lines: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = list(lines)
    index = 0
    while index < len(normalized):
        start = _box_top_inner_width(normalized[index])
        if start is None:
            index += 1
            continue

        indent, inner_width = start
        end_index = _find_box_bottom(normalized, index + 1, indent=indent)
        if end_index is None:
            index += 1
            continue

        for line_index in range(index + 1, end_index):
            normalized[line_index] = _normalize_box_content_line(
                normalized[line_index],
                indent=indent,
                inner_width=inner_width,
            )
        index = end_index + 1
    return tuple(normalized)


def normalize_terminal_output(text: str) -> str:
    return text.translate(_THAI_LAO_AM_TRANSLATION)


def grapheme_clusters(text: str) -> tuple[str, ...]:
    return tuple(_grapheme_clusters(text))


def wrap_cells(text: str, *, width: int) -> list[str]:
    if width <= 0:
        raise ValueError("width must be positive")

    wrapped: list[str] = []
    for logical_line in strip_control_sequences(text).split("\n"):
        current = ""
        current_width = 0
        for cluster in _grapheme_clusters(logical_line):
            cluster_width = _cluster_width(cluster)
            if current and current_width + cluster_width > width:
                wrapped.append(current)
                current = ""
                current_width = 0
            current += cluster
            current_width += cluster_width
        wrapped.append(current)
    return wrapped


def wrap_ansi(text: str, *, width: int) -> list[str]:
    if width <= 0:
        raise ValueError("width must be positive")
    if text == "":
        return [""]

    wrapped: list[str] = []
    tracker = _StyleTracker()
    for input_line in text.split("\n"):
        current = tracker.active_codes()
        current_width = 0
        tokens = _ansi_tokens(input_line)
        if not tokens:
            wrapped.append(current.rstrip(" "))
            continue

        for token in tokens:
            token_width = visible_width(token)
            is_whitespace = strip_control_sequences(token).strip() == ""

            if token_width > width and not is_whitespace:
                if current_width > 0:
                    wrapped.append(_close_line(current.rstrip(" "), tracker))
                    current = tracker.active_codes()
                    current_width = 0
                broken = _break_long_ansi_token(token, width=width, tracker=tracker)
                wrapped.extend(broken[:-1])
                current = broken[-1]
                current_width = visible_width(current)
                continue

            if current_width > 0 and current_width + token_width > width:
                wrapped.append(_close_line(current.rstrip(" "), tracker))
                current = tracker.active_codes()
                current_width = 0
                if is_whitespace:
                    _process_control_sequences(token, tracker)
                    continue

            current += token
            current_width += token_width
            _process_control_sequences(token, tracker)

        wrapped.append(current.rstrip(" "))
    return wrapped or [""]


def slice_by_column(text: str, *, start: int, length: int, strict: bool = True) -> ColumnSlice:
    if start < 0:
        raise ValueError("start must be non-negative")
    if length <= 0:
        return ColumnSlice("", 0)

    end = start + length
    result = ""
    pending_controls = ""
    width = 0
    column = 0
    index = 0
    while index < len(text):
        control = _extract_control_sequence(text, index)
        if control is not None:
            if column < start:
                pending_controls += control.code
            elif column < end:
                result += control.code
            index += control.length
            continue

        cluster = _next_cluster(text, index)
        cluster_width = _cluster_width(cluster)
        cluster_start = column
        cluster_end = column + cluster_width
        include = cluster_start >= start and cluster_end <= end
        if not strict:
            include = cluster_start < end and cluster_end > start
        if include:
            if pending_controls:
                result += pending_controls
                pending_controls = ""
            result += cluster
            width += cluster_width
        column = cluster_end
        index += len(cluster)

    return ColumnSlice(result, width)


def slice_with_width(text: str, *, start: int, length: int, strict: bool = True) -> ColumnSlice:
    return slice_by_column(text, start=start, length=length, strict=strict)


def truncate_to_width(text: str, *, max_width: int, ellipsis: str = "...", pad: bool = False) -> str:
    if max_width <= 0:
        return ""
    ascii_text_width = _plain_ascii_width(text)
    ascii_ellipsis_width = _plain_ascii_width(ellipsis)
    if ascii_text_width is not None and ascii_ellipsis_width is not None:
        return _truncate_plain_ascii(
            text,
            text_width=ascii_text_width,
            max_width=max_width,
            ellipsis=ellipsis,
            ellipsis_width=ascii_ellipsis_width,
            pad=pad,
        )

    text_width = visible_width(text)
    if text_width <= max_width:
        return text + (" " * max(0, max_width - text_width) if pad else "")

    ellipsis_width = visible_width(ellipsis)
    if ellipsis_width >= max_width:
        clipped_ellipsis = slice_by_column(ellipsis, start=0, length=max_width).text
        clipped_width = visible_width(clipped_ellipsis)
        if clipped_width == 0:
            return " " * max_width if pad else ""
        return _finalize_truncated_result(
            "",
            prefix_width=0,
            ellipsis=clipped_ellipsis,
            ellipsis_width=clipped_width,
            max_width=max_width,
            pad=pad,
        )

    prefix = slice_by_column(text, start=0, length=max_width - ellipsis_width)
    return _finalize_truncated_result(
        prefix.text,
        prefix_width=prefix.width,
        ellipsis=ellipsis,
        ellipsis_width=ellipsis_width,
        max_width=max_width,
        pad=pad,
    )


def autowrap_safe_width(width: int) -> int:
    if width <= 0:
        return 0
    return max(1, width - 1)


def _finalize_truncated_result(
    prefix: str,
    *,
    prefix_width: int,
    ellipsis: str,
    ellipsis_width: int,
    max_width: int,
    pad: bool,
) -> str:
    if ellipsis:
        result = f"{prefix}\x1b[0m{ellipsis}\x1b[0m"
        result_width = prefix_width + ellipsis_width
    else:
        result = f"{prefix}\x1b[0m"
        result_width = prefix_width
    return result + (" " * max(0, max_width - result_width) if pad else "")


@lru_cache(maxsize=_VISIBLE_WIDTH_CACHE_SIZE)
def _visible_width_cached(text: str) -> int:
    plain_ascii_width = _plain_ascii_width(text)
    if plain_ascii_width is not None:
        return plain_ascii_width
    return sum(_cluster_width(cluster) for cluster in _grapheme_clusters(strip_control_sequences(text)))


def _plain_ascii_width(text: str) -> int | None:
    if not text.isascii():
        return None
    for char in text:
        if not (" " <= char <= "~"):
            return None
    return len(text)


def _parse_ambiguous_width(value: str | None) -> AmbiguousWidth:
    normalized = (value or "1").strip().lower()
    if normalized in {"", "1", "narrow", "single"}:
        return 1
    if normalized in {"2", "wide", "double"}:
        return 2
    raise ValueError(f"{AMBIGUOUS_WIDTH_ENV} must be 1 or 2")


def _box_top_inner_width(line: str) -> tuple[str, int] | None:
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    if not stripped.startswith("┌") or not stripped.endswith("┐"):
        return None
    inner = stripped[1:-1]
    if not inner or any(char != "─" for char in inner):
        return None
    return indent, visible_width(inner)


def _find_box_bottom(lines: list[str], start: int, *, indent: str) -> int | None:
    for index in range(start, len(lines)):
        stripped = lines[index].lstrip(" ")
        current_indent = lines[index][: len(lines[index]) - len(stripped)]
        if current_indent != indent:
            continue
        if stripped.startswith("└") and stripped.endswith("┘") and stripped[1:-1] and all(char == "─" for char in stripped[1:-1]):
            return index
    return None


def _normalize_box_content_line(line: str, *, indent: str, inner_width: int) -> str:
    if not line.startswith(indent):
        return line
    rest = line[len(indent) :]
    if not rest.startswith("│"):
        return line
    right_border_index = rest.find("│", 1)
    if right_border_index < 0:
        return line
    body = rest[1:right_border_index].rstrip(" ")
    suffix = rest[right_border_index + 1 :]
    if visible_width(body) > inner_width:
        return line
    return indent + "│" + body + (" " * (inner_width - visible_width(body))) + "│" + suffix


def _truncate_plain_ascii(
    text: str,
    *,
    text_width: int,
    max_width: int,
    ellipsis: str,
    ellipsis_width: int,
    pad: bool,
) -> str:
    if text_width <= max_width:
        return text + (" " * max(0, max_width - text_width) if pad else "")

    if ellipsis_width >= max_width:
        clipped_ellipsis = ellipsis[:max_width]
        clipped_width = len(clipped_ellipsis)
        if clipped_width == 0:
            return " " * max_width if pad else ""
        return _finalize_truncated_result(
            "",
            prefix_width=0,
            ellipsis=clipped_ellipsis,
            ellipsis_width=clipped_width,
            max_width=max_width,
            pad=pad,
        )

    prefix_width = max_width - ellipsis_width
    return _finalize_truncated_result(
        text[:prefix_width],
        prefix_width=prefix_width,
        ellipsis=ellipsis,
        ellipsis_width=ellipsis_width,
        max_width=max_width,
        pad=pad,
    )


@dataclass(frozen=True, slots=True)
class _ControlSequence:
    code: str
    length: int


@dataclass(frozen=True, slots=True)
class _ActiveHyperlink:
    params: str
    url: str
    terminator: str


def _extract_control_sequence(text: str, start: int) -> _ControlSequence | None:
    if start >= len(text) or text[start] != "\x1b":
        return None
    index = start + 1
    if index >= len(text):
        return _ControlSequence(text[start:], len(text) - start)

    introducer = text[index]
    if introducer == "[":
        index += 1
        while index < len(text):
            if "@" <= text[index] <= "~":
                return _ControlSequence(text[start : index + 1], index + 1 - start)
            index += 1
        return _ControlSequence(text[start:], len(text) - start)

    if introducer in {"]", "_"}:
        index += 1
        while index < len(text):
            if text[index] == "\x07":
                return _ControlSequence(text[start : index + 1], index + 1 - start)
            if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "\\":
                return _ControlSequence(text[start : index + 2], index + 2 - start)
            index += 1
        return _ControlSequence(text[start:], len(text) - start)

    return _ControlSequence(text[start : start + 2], min(2, len(text) - start))


def _ansi_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current = ""
    current_kind: str | None = None
    pending_controls = ""
    index = 0
    while index < len(text):
        control = _extract_control_sequence(text, index)
        if control is not None:
            pending_controls += control.code
            index += control.length
            continue

        cluster = _next_cluster(text, index)
        kind = "space" if cluster.isspace() else "word"
        if current and current_kind is not None and current_kind != kind:
            tokens.append(current)
            current = ""
        if pending_controls:
            current += pending_controls
            pending_controls = ""
        current += cluster
        current_kind = kind
        index += len(cluster)
    if pending_controls:
        current += pending_controls
    if current:
        tokens.append(current)
    return tokens


def _process_control_sequences(text: str, tracker: _StyleTracker) -> None:
    index = 0
    while index < len(text):
        control = _extract_control_sequence(text, index)
        if control is not None:
            tracker.process(control.code)
            index += control.length
            continue
        index += len(_next_cluster(text, index))


def _break_long_ansi_token(token: str, *, width: int, tracker: _StyleTracker) -> list[str]:
    lines: list[str] = []
    current = tracker.active_codes()
    current_width = 0
    index = 0
    while index < len(token):
        control = _extract_control_sequence(token, index)
        if control is not None:
            current += control.code
            tracker.process(control.code)
            index += control.length
            continue

        cluster = _next_cluster(token, index)
        cluster_width = _cluster_width(cluster)
        if current_width > 0 and current_width + cluster_width > width:
            lines.append(_close_line(current.rstrip(" "), tracker))
            current = tracker.active_codes()
            current_width = 0
            if cluster.isspace():
                index += len(cluster)
                continue
        current += cluster
        current_width += cluster_width
        index += len(cluster)
    lines.append(current.rstrip(" "))
    return lines


def _grapheme_clusters(text: str) -> list[str]:
    clusters: list[str] = []
    index = 0
    while index < len(text):
        cluster = _next_cluster(text, index)
        clusters.append(cluster)
        index += len(cluster)
    return clusters


def _next_cluster(text: str, index: int) -> str:
    cluster = text[index]
    index += 1

    if _is_regional_indicator(cluster) and index < len(text) and _is_regional_indicator(text[index]):
        cluster += text[index]
        index += 1
        return cluster

    while index < len(text) and _is_cluster_suffix(text[index]):
        cluster += text[index]
        index += 1

    while index < len(text) and text[index] == "\u200d":
        cluster += text[index]
        index += 1
        if index < len(text):
            cluster += text[index]
            index += 1
        while index < len(text) and _is_cluster_suffix(text[index]):
            cluster += text[index]
            index += 1

    return cluster


def _is_cluster_suffix(char: str) -> bool:
    return (
        unicodedata.combining(char) != 0
        or "\ufe00" <= char <= "\ufe0f"
        or "\U0001f3fb" <= char <= "\U0001f3ff"
    )


@lru_cache(maxsize=_CLUSTER_WIDTH_CACHE_SIZE)
def _cluster_width(cluster: str) -> int:
    if not cluster:
        return 0
    if all(_char_width(char) == 0 for char in cluster):
        return 0
    if "\ufe0f" in cluster:
        return 2
    if "\u200d" in cluster:
        return 2
    if any(_is_emoji_width(char) or _is_regional_indicator(char) for char in cluster):
        return 2
    if any(_char_width(char) == 2 for char in cluster):
        return 2
    return sum(_char_width(char) for char in cluster)


@lru_cache(maxsize=_CHAR_WIDTH_CACHE_SIZE)
def _char_width(char: str) -> int:
    if char == "\t":
        return TAB_WIDTH
    if unicodedata.combining(char) != 0:
        return 0
    if char in {"\u0e4d", "\u0ecd"}:
        return 0
    if char == "\u200d" or "\ufe00" <= char <= "\ufe0f":
        return 0
    if "\U0001f3fb" <= char <= "\U0001f3ff":
        return 0
    if unicodedata.category(char) in {"Cc", "Cf"}:
        return 0
    east_asian_width = unicodedata.east_asian_width(char)
    if east_asian_width in {"F", "W"}:
        return 2
    if east_asian_width == "A":
        return _AMBIGUOUS_WIDTH
    return 1


configure_cell_width_from_environment()


def _is_regional_indicator(char: str) -> bool:
    return "\U0001f1e6" <= char <= "\U0001f1ff"


def _is_emoji_width(char: str) -> bool:
    codepoint = ord(char)
    return 0x1F000 <= codepoint <= 0x1FBFF


class _StyleTracker:
    def __init__(self) -> None:
        self._bold = False
        self._dim = False
        self._italic = False
        self._underline = False
        self._blink = False
        self._inverse = False
        self._hidden = False
        self._strikethrough = False
        self._fg_color: str | None = None
        self._bg_color: str | None = None
        self._active_hyperlink: _ActiveHyperlink | None = None

    def process(self, control: str) -> None:
        hyperlink = _parse_osc8_hyperlink(control)
        if hyperlink is not None:
            self._active_hyperlink = hyperlink
            return
        if _is_osc8_close(control):
            self._active_hyperlink = None
            return
        if not control.startswith("\x1b[") or not control.endswith("m"):
            return
        params = control[2:-1]
        if params in {"", "0"}:
            self._reset_sgr()
            return
        parts = params.split(";")
        index = 0
        while index < len(parts):
            try:
                code = int(parts[index] or "0")
            except ValueError:
                index += 1
                continue

            if code in {38, 48}:
                consumed = self._process_color(code, parts[index:])
                index += consumed
                continue

            self._process_sgr_code(code)
            index += 1

    def active_codes(self) -> str:
        codes: list[str] = []
        if self._bold:
            codes.append("1")
        if self._dim:
            codes.append("2")
        if self._italic:
            codes.append("3")
        if self._underline:
            codes.append("4")
        if self._blink:
            codes.append("5")
        if self._inverse:
            codes.append("7")
        if self._hidden:
            codes.append("8")
        if self._strikethrough:
            codes.append("9")
        if self._fg_color is not None:
            codes.append(self._fg_color)
        if self._bg_color is not None:
            codes.append(self._bg_color)
        sgr = f"\x1b[{';'.join(codes)}m" if codes else ""
        if self._active_hyperlink is not None:
            return f"{sgr}{_format_osc8_hyperlink(self._active_hyperlink)}"
        return sgr

    def line_end_reset(self) -> str:
        reset = ""
        if self._underline:
            reset += "\x1b[24m"
        if self._active_hyperlink is not None:
            reset += _format_osc8_close(self._active_hyperlink.terminator)
        return reset

    def _process_color(self, code: int, parts: list[str]) -> int:
        if len(parts) >= 3 and parts[1] == "5":
            color = ";".join(parts[:3])
            if code == 38:
                self._fg_color = color
            else:
                self._bg_color = color
            return 3
        if len(parts) >= 5 and parts[1] == "2":
            color = ";".join(parts[:5])
            if code == 38:
                self._fg_color = color
            else:
                self._bg_color = color
            return 5
        return 1

    def _process_sgr_code(self, code: int) -> None:
        if code == 0:
            self._reset_sgr()
        elif code == 1:
            self._bold = True
        elif code == 2:
            self._dim = True
        elif code == 3:
            self._italic = True
        elif code == 4:
            self._underline = True
        elif code == 5:
            self._blink = True
        elif code == 7:
            self._inverse = True
        elif code == 8:
            self._hidden = True
        elif code == 9:
            self._strikethrough = True
        elif code == 21:
            self._bold = False
        elif code == 22:
            self._bold = False
            self._dim = False
        elif code == 23:
            self._italic = False
        elif code == 24:
            self._underline = False
        elif code == 25:
            self._blink = False
        elif code == 27:
            self._inverse = False
        elif code == 28:
            self._hidden = False
        elif code == 29:
            self._strikethrough = False
        elif code == 39:
            self._fg_color = None
        elif code == 49:
            self._bg_color = None
        elif 30 <= code <= 37 or 90 <= code <= 97:
            self._fg_color = str(code)
        elif 40 <= code <= 47 or 100 <= code <= 107:
            self._bg_color = str(code)

    def _reset_sgr(self) -> None:
        self._bold = False
        self._dim = False
        self._italic = False
        self._underline = False
        self._blink = False
        self._inverse = False
        self._hidden = False
        self._strikethrough = False
        self._fg_color = None
        self._bg_color = None


def _close_line(line: str, tracker: _StyleTracker) -> str:
    if not line:
        return line
    return f"{line}{tracker.line_end_reset()}"


def _parse_osc8_hyperlink(control: str) -> _ActiveHyperlink | None:
    if not control.startswith("\x1b]8;"):
        return None
    terminator = _osc_terminator(control)
    if terminator is None:
        return None
    body = control[4 : -len(terminator)]
    separator = body.find(";")
    if separator < 0:
        return None
    params = body[:separator]
    url = body[separator + 1 :]
    if not url:
        return None
    return _ActiveHyperlink(params=params, url=url, terminator=terminator)


def _is_osc8_close(control: str) -> bool:
    if not control.startswith("\x1b]8;"):
        return False
    terminator = _osc_terminator(control)
    if terminator is None:
        return False
    body = control[4 : -len(terminator)]
    separator = body.find(";")
    return separator >= 0 and body[separator + 1 :] == ""


def _osc_terminator(control: str) -> str | None:
    if control.endswith("\x07"):
        return "\x07"
    if control.endswith("\x1b\\"):
        return "\x1b\\"
    return None


def _format_osc8_hyperlink(hyperlink: _ActiveHyperlink) -> str:
    return f"\x1b]8;{hyperlink.params};{hyperlink.url}{hyperlink.terminator}"


def _format_osc8_close(terminator: str) -> str:
    return f"\x1b]8;;{terminator}"

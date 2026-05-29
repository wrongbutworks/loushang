from __future__ import annotations

import json
import re
from typing import Any

_VALID_JSON_ESCAPES = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}


def parse_streaming_json(value: str | None) -> dict[str, Any]:
    if not value or not value.strip():
        return {}

    parsed = _parse_json_object_with_repair(value)
    if parsed is not None:
        return parsed

    repaired = _repair_partial_json(value)
    if repaired is None:
        return {}

    parsed = _parse_json_object_with_repair(repaired)
    return parsed if parsed is not None else {}


def repair_json(value: str) -> str:
    repaired: list[str] = []
    in_string = False
    index = 0

    while index < len(value):
        char = value[index]

        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue

        if char == '"':
            repaired.append(char)
            in_string = False
            index += 1
            continue

        if char == "\\":
            next_char = value[index + 1] if index + 1 < len(value) else None
            if next_char is None:
                repaired.append("\\\\")
                index += 1
                continue

            if next_char == "u":
                unicode_digits = value[index + 2 : index + 6]
                if re.fullmatch(r"[0-9a-fA-F]{4}", unicode_digits):
                    repaired.append(f"\\u{unicode_digits}")
                    index += 6
                    continue

            if next_char in _VALID_JSON_ESCAPES:
                repaired.append(f"\\{next_char}")
                index += 2
                continue

            repaired.append("\\\\")
            index += 1
            continue

        repaired.append(_escape_control_character(char) if _is_control_character(char) else char)
        index += 1

    return "".join(repaired)


def _parse_json_object_with_repair(value: str) -> dict[str, Any] | None:
    parsed = _parse_json_object(value)
    if parsed is not None:
        return parsed

    repaired = repair_json(value)
    if repaired == value:
        return None
    return _parse_json_object(repaired)


def _parse_json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value, strict=False)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_control_character(char: str) -> bool:
    return ord(char) <= 0x1F


def _escape_control_character(char: str) -> str:
    if char == "\b":
        return "\\b"
    if char == "\f":
        return "\\f"
    if char == "\n":
        return "\\n"
    if char == "\r":
        return "\\r"
    if char == "\t":
        return "\\t"
    return f"\\u{ord(char):04x}"


def _repair_partial_json(value: str) -> str | None:
    trimmed = value.strip()
    if not trimmed.startswith("{"):
        return None

    stack: list[str] = []
    in_string = False
    escaped = False

    for char in trimmed:
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in {"}", "]"}:
            if stack and stack[-1] == char:
                stack.pop()

    repaired = trimmed
    if in_string:
        repaired += '"'

    repaired = repaired.rstrip()
    if repaired.endswith(":"):
        return None
    if repaired.endswith(","):
        repaired = repaired[:-1]

    repaired += "".join(reversed(stack))
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired

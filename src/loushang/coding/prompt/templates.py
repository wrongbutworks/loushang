from __future__ import annotations

import re


_PLACEHOLDER_PATTERN = re.compile(r"\$\{@:(\d+)(?::(\d+))?\}|\$ARGUMENTS|\$@|\$(\d+)")


def parse_prompt_template_args(args_string: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    in_quote: str | None = None

    for char in args_string:
        if in_quote is not None:
            if char == in_quote:
                in_quote = None
            else:
                current.append(char)
            continue
        if char in {"'", '"'}:
            in_quote = char
            continue
        if char in {" ", "\t"}:
            if current:
                args.append("".join(current))
                current = []
            continue
        current.append(char)

    if current:
        args.append("".join(current))
    return args


def prompt_template_has_args(content: str) -> bool:
    return _PLACEHOLDER_PATTERN.search(content) is not None


def substitute_prompt_template_args(content: str, args: list[str]) -> str:
    all_args = " ".join(args)

    def replace(match: re.Match[str]) -> str:
        positional = match.group(3)
        if positional is not None:
            index = int(positional) - 1
            return args[index] if index >= 0 and index < len(args) else ""

        slice_start = match.group(1)
        if slice_start is not None:
            start = int(slice_start) - 1
            if start < 0:
                start = 0
            length = match.group(2)
            if length is not None:
                return " ".join(args[start : start + int(length)])
            return " ".join(args[start:])

        return all_args

    return _PLACEHOLDER_PATTERN.sub(replace, content)


__all__ = [
    "parse_prompt_template_args",
    "prompt_template_has_args",
    "substitute_prompt_template_args",
]

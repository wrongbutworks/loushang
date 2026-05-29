from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str


@dataclass(frozen=True, slots=True)
class MarkdownBlock:
    text: str


@dataclass(frozen=True, slots=True)
class RuleBlock:
    label: str = ""
    char: str = "-"


TerminalBlock: TypeAlias = TextBlock | MarkdownBlock | RuleBlock


def diff_stat(diff: object) -> str | None:
    if not isinstance(diff, str):
        return None
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    if added == 0 and removed == 0:
        return None
    return f"+{added} -{removed}"


def blocks_to_terminal_text(
    blocks: tuple[TerminalBlock, ...],
    *,
    width: int,
    separator: str = "\n\n",
) -> str:
    rendered = [_render_block(block, width=width) for block in blocks]
    return separator.join(text for text in rendered if text)


def _render_block(block: TerminalBlock, *, width: int) -> str:
    if isinstance(block, TextBlock):
        return block.text
    if isinstance(block, MarkdownBlock):
        return _plain_markdown(block.text)
    target_width = autowrap_safe_width(width)
    prefix = f"{block.char} {block.label} " if block.label else block.char
    if len(prefix) >= target_width:
        return truncate_to_width(prefix, max_width=target_width)
    return prefix + (block.char * (target_width - len(prefix)))


def _plain_markdown(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "")

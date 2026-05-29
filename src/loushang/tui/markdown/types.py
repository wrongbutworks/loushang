from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_MarkdownKind = Literal["heading", "paragraph", "list_item", "quote", "code", "hr", "table", "blank"]
_InlineKind = Literal["text", "code", "strong", "emphasis", "strikethrough", "link", "softbreak", "hardbreak"]
_TableAlignment = Literal["left", "center", "right", "default"]


@dataclass(frozen=True, slots=True)
class _InlineToken:
    kind: _InlineKind
    text: str = ""
    children: tuple[_InlineToken, ...] = ()
    href: str = ""


_TableCell = tuple[_InlineToken, ...]
_TableRow = tuple[_TableCell, ...]


@dataclass(frozen=True, slots=True)
class _MarkdownBlock:
    kind: _MarkdownKind
    text: str = ""
    lines: tuple[str, ...] = ()
    level: int = 0
    meta: str = ""
    inline: tuple[_InlineToken, ...] = ()
    children: tuple[_MarkdownBlock, ...] = ()
    table_rows: tuple[_TableRow, ...] = ()
    table_alignments: tuple[_TableAlignment, ...] = ()

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from typing import TypeVar

__all__ = ["cluster_kind", "word_left_index", "word_right_index"]

T = TypeVar("T")


def cluster_kind(cluster: str) -> str:
    if cluster == "\n":
        return "newline"
    if cluster.isspace():
        return "space"
    if cluster.isalnum() or cluster == "_":
        return "word"
    return "punctuation"


def word_left_index(
    items: Sequence[T],
    cursor: int,
    kind_of: Callable[[T], str],
    *,
    atomic_kinds: Collection[str] = (),
) -> int:
    index = max(0, min(cursor, len(items)))
    while index > 0 and kind_of(items[index - 1]) == "space":
        index -= 1
    if index == 0:
        return index
    kind = kind_of(items[index - 1])
    if kind in atomic_kinds:
        return index - 1
    while index > 0 and kind_of(items[index - 1]) == kind:
        index -= 1
    return index


def word_right_index(
    items: Sequence[T],
    cursor: int,
    kind_of: Callable[[T], str],
    *,
    atomic_kinds: Collection[str] = (),
) -> int:
    index = max(0, min(cursor, len(items)))
    while index < len(items) and kind_of(items[index]) == "space":
        index += 1
    if index >= len(items):
        return index
    kind = kind_of(items[index])
    if kind in atomic_kinds:
        return index + 1
    while index < len(items) and kind_of(items[index]) == kind:
        index += 1
    return index

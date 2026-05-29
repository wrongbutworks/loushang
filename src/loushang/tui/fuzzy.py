from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
_WORD_BOUNDARY_RE = re.compile(r"[\s\-_./:]")
_ALPHA_NUMERIC_RE = re.compile(r"^(?P<letters>[a-z]+)(?P<digits>[0-9]+)$")
_NUMERIC_ALPHA_RE = re.compile(r"^(?P<digits>[0-9]+)(?P<letters>[a-z]+)$")


@dataclass(frozen=True, slots=True)
class FuzzyMatch:
    matches: bool
    score: float = 0.0


def fuzzy_match(query: str, text: str) -> FuzzyMatch:
    query_lower = query.lower()
    text_lower = text.lower()

    primary = _match_query(query_lower, text_lower)
    if primary.matches:
        return primary

    swapped = _swapped_alpha_numeric_query(query_lower)
    if not swapped:
        return primary

    swapped_match = _match_query(swapped, text_lower)
    if not swapped_match.matches:
        return primary
    return FuzzyMatch(matches=True, score=swapped_match.score + 5)


def fuzzy_filter(items: Sequence[T], query: str, *, key: Callable[[T], str]) -> list[T]:
    if not query.strip():
        return list(items)

    tokens = tuple(token for token in query.strip().split() if token)
    if not tokens:
        return list(items)

    results: list[tuple[float, int, T]] = []
    for index, item in enumerate(items):
        total_score = 0.0
        text = key(item)
        for token in tokens:
            match = fuzzy_match(token, text)
            if not match.matches:
                break
            total_score += match.score
        else:
            results.append((total_score, index, item))

    results.sort(key=lambda result: (result[0], result[1]))
    return [item for _score, _index, item in results]


def _match_query(query: str, text: str) -> FuzzyMatch:
    if not query:
        return FuzzyMatch(matches=True, score=0.0)
    if len(query) > len(text):
        return FuzzyMatch(matches=False)

    query_index = 0
    score = 0.0
    last_match_index = -1
    consecutive_matches = 0

    for index, char in enumerate(text):
        if query_index >= len(query):
            break
        if char != query[query_index]:
            continue
        is_word_boundary = index == 0 or bool(_WORD_BOUNDARY_RE.match(text[index - 1]))
        if last_match_index == index - 1:
            consecutive_matches += 1
            score -= consecutive_matches * 5
        else:
            consecutive_matches = 0
            if last_match_index >= 0:
                score += (index - last_match_index - 1) * 2
        if is_word_boundary:
            score -= 10
        score += index * 0.1
        last_match_index = index
        query_index += 1

    if query_index < len(query):
        return FuzzyMatch(matches=False)
    if query == text:
        score -= 100
    return FuzzyMatch(matches=True, score=score)


def _swapped_alpha_numeric_query(query: str) -> str:
    alpha_numeric = _ALPHA_NUMERIC_RE.match(query)
    if alpha_numeric is not None:
        return f"{alpha_numeric.group('digits')}{alpha_numeric.group('letters')}"
    numeric_alpha = _NUMERIC_ALPHA_RE.match(query)
    if numeric_alpha is not None:
        return f"{numeric_alpha.group('letters')}{numeric_alpha.group('digits')}"
    return ""


__all__ = ["FuzzyMatch", "fuzzy_filter", "fuzzy_match"]

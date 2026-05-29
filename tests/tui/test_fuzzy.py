from __future__ import annotations

from loushang.tui import fuzzy_filter, fuzzy_match


def test_fuzzy_match_accepts_ordered_subsequences_and_rejects_reordered_text() -> None:
    assert fuzzy_match("ms", "Model Selection").matches is True
    assert fuzzy_match("abc", "acb").matches is False


def test_fuzzy_match_prefers_exact_and_word_boundary_matches() -> None:
    exact = fuzzy_match("model", "model")
    boundary = fuzzy_match("ms", "Model Selection")
    late = fuzzy_match("ms", "custom model selection")

    assert exact.matches is True
    assert boundary.matches is True
    assert late.matches is True
    assert exact.score < boundary.score < late.score


def test_fuzzy_filter_requires_all_space_separated_tokens_and_sorts_by_score() -> None:
    items = ["model", "Model Selection", "Theme", "Memory Status"]

    assert fuzzy_filter(items, "ms", key=lambda item: item) == ["Model Selection", "Memory Status"]
    assert fuzzy_filter(items, "model sel", key=lambda item: item) == ["Model Selection"]
    assert fuzzy_filter(items, "", key=lambda item: item) == items

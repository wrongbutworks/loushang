from __future__ import annotations

from loushang.tui.word_navigation import cluster_kind, word_left_index, word_right_index


def _text_kinds(text: str) -> list[str]:
    return [cluster_kind(cluster) for cluster in text]


def test_cluster_kind_classifies_text_for_editor_navigation() -> None:
    assert cluster_kind("\n") == "newline"
    assert cluster_kind(" ") == "space"
    assert cluster_kind("a") == "word"
    assert cluster_kind("_") == "word"
    assert cluster_kind("中") == "word"
    assert cluster_kind(".") == "punctuation"


def test_word_navigation_skips_spaces_then_consumes_next_kind() -> None:
    kinds = _text_kinds("   hello")

    assert word_right_index(kinds, 0, lambda kind: kind) == 8
    assert word_left_index(kinds, 8, lambda kind: kind) == 3
    assert word_left_index(kinds, 3, lambda kind: kind) == 0


def test_word_navigation_splits_word_and_punctuation_runs() -> None:
    kinds = _text_kinds("foo.bar")

    assert word_right_index(kinds, 0, lambda kind: kind) == 3
    assert word_right_index(kinds, 3, lambda kind: kind) == 4
    assert word_right_index(kinds, 4, lambda kind: kind) == 7

    assert word_left_index(kinds, 7, lambda kind: kind) == 4
    assert word_left_index(kinds, 4, lambda kind: kind) == 3
    assert word_left_index(kinds, 3, lambda kind: kind) == 0


def test_word_navigation_can_treat_atomic_kinds_as_single_steps() -> None:
    kinds = ["word", "paste_marker", "paste_marker", "word"]

    assert word_right_index(kinds, 0, lambda kind: kind, atomic_kinds={"paste_marker"}) == 1
    assert word_right_index(kinds, 1, lambda kind: kind, atomic_kinds={"paste_marker"}) == 2
    assert word_right_index(kinds, 2, lambda kind: kind, atomic_kinds={"paste_marker"}) == 3

    assert word_left_index(kinds, 3, lambda kind: kind, atomic_kinds={"paste_marker"}) == 2
    assert word_left_index(kinds, 2, lambda kind: kind, atomic_kinds={"paste_marker"}) == 1
    assert word_left_index(kinds, 1, lambda kind: kind, atomic_kinds={"paste_marker"}) == 0

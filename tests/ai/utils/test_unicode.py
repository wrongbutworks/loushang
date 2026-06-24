from __future__ import annotations

from loushang.ai.utils.unicode import sanitize_surrogates


def test_sanitize_surrogates_keeps_valid_pair_and_removes_unpaired_codepoints() -> None:
    valid_pair = "\ud83d\ude48"

    assert (
        sanitize_surrogates(f"a\ud83d b \ude48 c {valid_pair}")
        == f"a b  c {valid_pair}"
    )

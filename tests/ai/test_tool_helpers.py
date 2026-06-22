from __future__ import annotations

from types import SimpleNamespace

import pytest

from loushang.ai.tool.helpers import (
    clamp_max_tokens,
    compute_remaining_context,
    estimate_tokens_simple_from_messages,
    normalize_user_content,
)


def test_normalize_user_content_accepts_list_and_dict_without_mutating() -> None:
    parts = [{"type": "text", "text": "hello"}]
    payload = {"type": "text", "text": "hello"}

    assert normalize_user_content(parts) == parts
    assert normalize_user_content(parts) is not parts
    assert normalize_user_content(payload) == [payload]


def test_normalize_user_content_rejects_unsupported_shape() -> None:
    with pytest.raises(TypeError, match="Unsupported user content type"):
        normalize_user_content("hello")


def test_clamp_max_tokens_handles_missing_bounds() -> None:
    assert clamp_max_tokens(None, 4096) == 4096
    assert clamp_max_tokens(2048, None) == 2048
    assert clamp_max_tokens(8192, 4096) == 4096
    assert clamp_max_tokens(1024, 4096) == 1024


def test_compute_remaining_context_clamps_used_tokens_and_margin() -> None:
    assert compute_remaining_context(None, 10) is None
    assert compute_remaining_context(100, -50, safety_margin=-10) == 100
    assert compute_remaining_context(100, 80, safety_margin=10) == 10
    assert compute_remaining_context(100, 150, safety_margin=10) == 0


def test_estimate_tokens_simple_from_messages_counts_visible_text() -> None:
    assert (
        estimate_tokens_simple_from_messages([
            {"content": "abcd"},
            {"content": [{"text": "abcdefgh"}, {"text": 3}]},
            {"content": {"text": "abcd"}},
            SimpleNamespace(
                content=[
                    SimpleNamespace(text="abcdefghijkl"),
                    SimpleNamespace(data="ignored"),
                ]
            ),
        ])
        == 7
    )
    assert estimate_tokens_simple_from_messages([{"content": []}]) == 0

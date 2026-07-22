from __future__ import annotations

import pytest

from loushang.harness.session.bootstrap_utils import (
    append_system_prompt_fragments,
    normalize_no_tools,
    split_model_thinking_pattern,
)


def test_bootstrap_utils_append_non_empty_prompt_fragments() -> None:
    assert append_system_prompt_fragments(" base ", ["", " extra "]) == (
        "base\n\nextra"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "all"), (False, None), (None, None), ("builtin", "builtin")],
)
def test_bootstrap_utils_normalize_no_tools(value, expected) -> None:
    assert normalize_no_tools(value) == expected


def test_bootstrap_utils_rejects_unknown_no_tools_mode() -> None:
    with pytest.raises(ValueError, match="no_tools"):
        normalize_no_tools("custom")


def test_bootstrap_utils_splits_scoped_model_thinking_pattern() -> None:
    assert split_model_thinking_pattern("provider/model:high") == (
        "provider/model",
        "high",
    )
    assert split_model_thinking_pattern("provider/model") == ("provider/model", None)

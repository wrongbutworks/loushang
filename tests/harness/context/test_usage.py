from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_context_usage_estimate_preserves_accounting_values() -> None:
    from loushang.harness.context.usage import ContextUsageEstimate

    estimate = ContextUsageEstimate(
        tokens=125,
        usage_tokens=100,
        trailing_tokens=25,
        last_usage_index=3,
    )

    assert estimate.tokens == 125
    assert estimate.usage_tokens == 100
    assert estimate.trailing_tokens == 25
    assert estimate.last_usage_index == 3

    with pytest.raises(FrozenInstanceError):
        estimate.tokens = 0  # type: ignore[misc]

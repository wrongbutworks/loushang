from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest


def test_compaction_budget_uses_more_conservative_percent_threshold() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    budget = calculate_compaction_budget(
        context_window=128_000,
        compact_percent=80,
        reserve_tokens=8_192,
    )

    assert budget.context_window == 128_000
    assert budget.compact_percent == 80.0
    assert budget.reserve_tokens == 8_192
    assert budget.percent_threshold_tokens == 102_400
    assert budget.reserve_threshold_tokens == 119_808
    assert budget.threshold_tokens == 102_400
    assert budget.threshold_reason == "compact_percent"


def test_compaction_budget_uses_more_conservative_reserve_threshold() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    budget = calculate_compaction_budget(
        context_window=32_000,
        compact_percent=80,
        reserve_tokens=16_384,
    )

    assert budget.percent_threshold_tokens == 25_600
    assert budget.reserve_threshold_tokens == 15_616
    assert budget.threshold_tokens == 15_616
    assert budget.threshold_reason == "reserve_tokens"


def test_compaction_budget_normalizes_ranges() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    above_range = calculate_compaction_budget(
        context_window=-10,
        compact_percent=120,
        reserve_tokens=-50,
    )
    below_range = calculate_compaction_budget(
        context_window=1_000,
        compact_percent=-20,
        reserve_tokens=2_000,
    )

    assert above_range.context_window == 0
    assert above_range.compact_percent == 100.0
    assert above_range.reserve_tokens == 0
    assert above_range.threshold_tokens == 0
    assert below_range.compact_percent == 0.0
    assert below_range.reserve_threshold_tokens == 0
    assert below_range.threshold_tokens == 0
    assert below_range.threshold_reason == "compact_percent"


def test_explicit_budget_values_override_settings() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    settings = SimpleNamespace(compact_percent=25, reserve_tokens=750)
    budget = calculate_compaction_budget(
        context_window=1_000,
        settings=settings,
        compact_percent=80,
        reserve_tokens=100,
    )

    assert budget.compact_percent == 80.0
    assert budget.reserve_tokens == 100
    assert budget.percent_threshold_tokens == 800
    assert budget.reserve_threshold_tokens == 900


def test_compaction_budget_uses_settings_and_defaults() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    settings_budget = calculate_compaction_budget(
        context_window=1_000,
        settings=SimpleNamespace(compact_percent=75, reserve_tokens=100),
    )
    default_budget = calculate_compaction_budget(context_window=1_000)

    assert settings_budget.compact_percent == 75.0
    assert settings_budget.reserve_tokens == 100
    assert settings_budget.threshold_tokens == 750
    assert default_budget.compact_percent == 100.0
    assert default_budget.reserve_tokens == 0
    assert default_budget.threshold_tokens == 1_000


def test_compaction_budget_is_frozen() -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    budget = calculate_compaction_budget(context_window=1_000)

    with pytest.raises(FrozenInstanceError):
        budget.threshold_tokens = 500  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (("context_window", "invalid"), ("compact_percent", "invalid"), ("reserve_tokens", "invalid")),
)
def test_compaction_budget_preserves_invalid_number_errors(field: str, value: str) -> None:
    from loushang.harness.context.budget import calculate_compaction_budget

    arguments: dict[str, object] = {"context_window": 1_000, field: value}

    with pytest.raises(ValueError):
        calculate_compaction_budget(**arguments)  # type: ignore[arg-type]

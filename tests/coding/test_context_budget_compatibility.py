from __future__ import annotations


def test_coding_context_budget_paths_share_harness_identity() -> None:
    import loushang.coding as coding
    import loushang.coding.compaction as compaction
    from loushang.coding.compaction import policy, types
    from loushang.harness.context import budget, usage

    assert compaction.CompactionBudget is budget.CompactionBudget
    assert policy.CompactionBudget is budget.CompactionBudget
    assert compaction.calculate_compaction_budget is budget.calculate_compaction_budget
    assert policy.calculate_compaction_budget is budget.calculate_compaction_budget

    assert coding.ContextUsageEstimate is usage.ContextUsageEstimate
    assert compaction.ContextUsageEstimate is usage.ContextUsageEstimate
    assert types.ContextUsageEstimate is usage.ContextUsageEstimate

    assert budget.CompactionBudget.__module__ == "loushang.harness.context.budget"
    assert budget.calculate_compaction_budget.__module__ == "loushang.harness.context.budget"
    assert usage.ContextUsageEstimate.__module__ == "loushang.harness.context.usage"


def test_coding_context_estimator_returns_harness_record() -> None:
    from loushang.ai.types import UserMessage
    from loushang.coding.compaction import estimate_context_tokens
    from loushang.harness.context.usage import ContextUsageEstimate

    estimate = estimate_context_tokens(
        [UserMessage(role="user", content="follow up", timestamp=1.0)]
    )

    assert isinstance(estimate, ContextUsageEstimate)
    assert estimate.usage_tokens == 0
    assert estimate.trailing_tokens == estimate.tokens
    assert estimate.last_usage_index is None
